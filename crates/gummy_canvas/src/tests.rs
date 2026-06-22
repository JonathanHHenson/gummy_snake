use crate::*;

#[test]
fn health_check_reports_canvas_backend() {
    assert_eq!(health_check(), "rust-canvas");
    assert_eq!(native_window_available(), runtime_native_window_available());
}

#[test]
fn canvas_tracks_logical_and_physical_dimensions() {
    let canvas = Canvas::new(10, 8, 2.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    assert_eq!(canvas.dimensions(), (10, 8, 20, 16, 2.0));
    assert_eq!(canvas.pixels.len(), 20 * 16 * 4);
}

#[test]
fn canvas_rejects_invalid_dimensions_and_density() {
    assert!(Canvas::new(0, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
    assert!(Canvas::new(10, 8, 0.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
}

#[test]
fn canvas_resize_noop_preserves_pixels() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    canvas.background((10, 20, 30, 255));

    canvas
        .resize_canvas(2, 1, 1.0, SUPPORTED_RENDERER)
        .expect("same-size backing resize should succeed");

    assert_eq!(canvas.load_pixels(), vec![10, 20, 30, 255, 10, 20, 30, 255]);
}

#[test]
fn background_clear_and_pixel_update_round_trip() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    canvas.background((10, 20, 30, 255));
    assert_eq!(canvas.load_pixels(), vec![10, 20, 30, 255, 10, 20, 30, 255]);

    canvas
        .update_pixels(vec![255, 0, 0, 255, 0, 0, 255, 255])
        .unwrap();
    assert_eq!(canvas.load_pixels(), vec![255, 0, 0, 255, 0, 0, 255, 255]);

    canvas.clear();
    assert_eq!(canvas.load_pixels(), vec![0; 8]);
}

#[test]
fn set_pixel_rgba_updates_one_pixel_and_ignores_out_of_bounds() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    canvas.set_pixel_rgba(1, 0, (10, 20, 30, 255)).unwrap();
    canvas.set_pixel_rgba(-1, 0, (255, 0, 0, 255)).unwrap();
    canvas.set_pixel_rgba(2, 0, (255, 0, 0, 255)).unwrap();

    assert_eq!(canvas.load_pixels(), vec![0, 0, 0, 0, 10, 20, 30, 255]);
    assert!(canvas.render_dirty);
    assert!(!canvas.pixels_stale);
    assert!(canvas.texture_stale);
}

#[test]
fn performance_counters_track_and_reset_runtime_paths() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    canvas
        .update_pixels(vec![255, 0, 0, 255, 0, 0, 255, 255])
        .unwrap();
    let _pixels = canvas.load_pixels();

    assert!(canvas.performance_counters.pixel_uploads >= 1);
    assert!(canvas.performance_counters.pixel_readbacks >= 1);

    canvas.reset_performance_counters();
    assert_eq!(canvas.performance_counters.pixel_uploads, 0);
    assert_eq!(canvas.performance_counters.pixel_readbacks, 0);
}

#[test]
fn cached_images_are_bounded() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for key in 0..(IMAGE_CACHE_LIMIT as u64 + 3) {
        canvas.evict_image_cache_if_needed(key);
        canvas.image_cache.insert(
            key,
            CachedImage {
                version: 0,
                width: 1,
                height: 1,
                pixels: vec![key as u8, 0, 0, 255],
            },
        );
    }

    assert!(canvas.image_cache.len() <= IMAGE_CACHE_LIMIT);
}

#[test]
fn cached_text_entries_are_bounded_and_report_evictions() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for index in 0..(TEXT_CACHE_LIMIT + 3) {
        canvas.evict_text_cache_if_needed();
        let texture_key = 1_000 + index as u64;
        let cache_key = format!("text-{index}");
        canvas.texture_cache_versions.insert(texture_key, 0);
        canvas.text_cache_order.push_back(cache_key.clone());
        canvas.text_cache.insert(
            cache_key,
            CachedText {
                texture_key,
                image: CachedImage {
                    version: 0,
                    width: 1,
                    height: 1,
                    pixels: vec![255, 255, 255, 255],
                },
                bbox_left: 0,
                bbox_top: 0,
                ascent: 1.0,
            },
        );
    }

    assert_eq!(canvas.text_cache.len(), TEXT_CACHE_LIMIT);
    assert_eq!(canvas.text_cache_order.len(), TEXT_CACHE_LIMIT);
    assert_eq!(canvas.performance_counters.text_cache_evictions, 3);
    assert!(!canvas.texture_cache_versions.contains_key(&1_000));
}

#[test]
fn gpu_status_reports_available_or_clear_error() {
    let canvas = Canvas::new(4, 4, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    if canvas.gpu_available() {
        assert_eq!(canvas.gpu_status(), "available");
    } else {
        assert_ne!(canvas.gpu_status(), "available");
    }
}

#[test]
fn gpu_path_renders_background_and_triangle_when_available() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((255, 255, 255, 255));
    canvas
        .draw_gpu_polygon(
            &[(1.0, 1.0), (6.0, 1.0), (1.0, 6.0)],
            &Style {
                fill: Some(Rgba {
                    r: 255,
                    g: 0,
                    b: 0,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_BLEND.to_string(),
                blend_mode_kind: BlendMode::Blend,
                erasing: false,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
            true,
            1.0,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [255, 0, 0, 255]));
    assert!(pixels
        .chunks_exact(4)
        .any(|rgba| rgba == [255, 255, 255, 255]));
}

#[test]
fn shaded_faces_cpu_fallback_preserves_face_color() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    canvas.gpu = None;
    let red = crate::gpu::GpuColor {
        r: 255,
        g: 0,
        b: 0,
        a: 255,
    };

    canvas.background((0, 0, 0, 255));
    canvas
        .draw_shaded_face_vertices_cpu(&[([1.0, 1.0], red), ([6.0, 1.0], red), ([1.0, 6.0], red)])
        .unwrap();

    let pixels = canvas.load_pixels();
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [255, 0, 0, 255]));
    assert!(!pixels
        .chunks_exact(4)
        .any(|rgba| rgba == [255, 255, 255, 255]));
}

#[test]
fn gpu_primitives_after_image_commands_are_rendered() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 255));
    if let Some(gpu) = canvas.gpu.as_mut() {
        let white = crate::gpu::GpuColor {
            r: 255,
            g: 255,
            b: 255,
            a: 255,
        };
        gpu.upload_texture(
            42,
            2,
            2,
            &[
                0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255,
            ],
        )
        .unwrap();
        gpu.draw_image(
            42,
            [
                ([0.0, 0.0], [0.0, 0.0], white),
                ([2.0, 0.0], [1.0, 0.0], white),
                ([2.0, 2.0], [1.0, 1.0], white),
                ([0.0, 0.0], [0.0, 0.0], white),
                ([2.0, 2.0], [1.0, 1.0], white),
                ([0.0, 2.0], [0.0, 1.0], white),
            ],
            true,
        );
    }
    canvas
        .draw_gpu_polygon(
            &[(4.0, 4.0), (7.0, 4.0), (4.0, 7.0)],
            &Style {
                fill: Some(Rgba {
                    r: 0,
                    g: 255,
                    b: 0,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_BLEND.to_string(),
                blend_mode_kind: BlendMode::Blend,
                erasing: false,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
            true,
            1.0,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [0, 0, 255, 255]));
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [0, 255, 0, 255]));
}

#[test]
fn gpu_overlay_after_cpu_upload_does_not_replay_previous_clear() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((255, 255, 255, 255));
    canvas.render_gpu_frame(true);

    let preserved_pixel_offset = (7 * canvas.physical_width + 7) * 4;
    canvas.pixels[preserved_pixel_offset..preserved_pixel_offset + 4]
        .copy_from_slice(&[255, 0, 0, 255]);
    canvas.upload_cpu_pixels().unwrap();
    canvas
        .draw_gpu_polygon(
            &[(1.0, 1.0), (3.0, 1.0), (1.0, 3.0)],
            &Style {
                fill: Some(Rgba {
                    r: 0,
                    g: 0,
                    b: 255,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_BLEND.to_string(),
                blend_mode_kind: BlendMode::Blend,
                erasing: false,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
            true,
            1.0,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert_eq!(
        &pixels[preserved_pixel_offset..preserved_pixel_offset + 4],
        &[255, 0, 0, 255]
    );
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [0, 0, 255, 255]));
}

#[test]
fn clip_mask_limits_background_updates() {
    let mut canvas = Canvas::new(4, 4, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    canvas.background((255, 0, 0, 255));
    canvas
        .begin_clip(
            vec![(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)],
            vec![],
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.background((0, 0, 255, 255));
    canvas.end_clip().unwrap();

    let pixels = canvas.load_pixels();
    let pixel = |x: usize, y: usize| {
        let offset = (y * canvas.physical_width + x) * 4;
        &pixels[offset..offset + 4]
    };
    assert_eq!(pixel(0, 0), &[255, 0, 0, 255]);
    assert_eq!(pixel(1, 1), &[0, 0, 255, 255]);
    assert_eq!(pixel(2, 2), &[0, 0, 255, 255]);
    assert_eq!(pixel(3, 3), &[255, 0, 0, 255]);
}

#[test]
fn interactive_runtime_primitives_track_open_and_close_state() {
    let mut canvas = Canvas::new(10, 8, 2.0, INTERACTIVE_MODE, SUPPORTED_RENDERER).unwrap();

    assert_eq!(canvas.display_density(), 2.0);
    assert!(!canvas.should_close());
    assert!(canvas.poll_events().unwrap().is_empty());
    assert_eq!(
        canvas.native_window_available(),
        runtime_native_window_available()
    );

    canvas.close();
    assert!(canvas.should_close());
}
