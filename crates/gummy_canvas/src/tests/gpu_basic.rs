use crate::*;

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
fn gpu_reuse_invalidates_when_clip_mask_changes() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((255, 255, 255, 255));
    canvas
        .begin_clip(
            vec![(0.0, 0.0), (4.0, 0.0), (4.0, 8.0), (0.0, 8.0)],
            vec![],
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.background((0, 0, 255, 255));
    canvas.end_clip().unwrap();
    canvas.end_frame();

    let first_frame = canvas.load_pixels();
    let physical_width = canvas.physical_width;
    let pixel = |pixels: &[u8], x: usize, y: usize| -> [u8; 4] {
        let offset = (y * physical_width + x) * 4;
        pixels[offset..offset + 4].try_into().unwrap()
    };
    assert_eq!(pixel(&first_frame, 1, 4), [0, 0, 255, 255]);
    assert_eq!(pixel(&first_frame, 6, 4), [255, 255, 255, 255]);

    canvas.begin_frame();
    canvas.background((255, 255, 255, 255));
    canvas
        .begin_clip(
            vec![(4.0, 0.0), (8.0, 0.0), (8.0, 8.0), (4.0, 8.0)],
            vec![],
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.background((0, 0, 255, 255));
    canvas.end_clip().unwrap();
    canvas.end_frame();

    let second_frame = canvas.load_pixels();
    assert_eq!(pixel(&second_frame, 1, 4), [255, 255, 255, 255]);
    assert_eq!(pixel(&second_frame, 6, 4), [0, 0, 255, 255]);
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
            BlendMode::Blend,
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
fn stale_cpu_pixels_upload_to_gpu_texture_without_pending_draws() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.background((0, 0, 0, 255));
    canvas.render_gpu_frame(true);
    canvas.set_pixel_rgba(1, 0, (10, 20, 30, 255)).unwrap();

    assert!(canvas.texture_stale);
    assert!(canvas.render_dirty);
    assert!(!canvas.offscreen_dirty);

    canvas.upload_stale_texture(false).unwrap();
    canvas.pixels_stale = true;
    let pixels = canvas.load_pixels();

    assert_eq!(pixels, vec![0, 0, 0, 255, 10, 20, 30, 255]);
}
