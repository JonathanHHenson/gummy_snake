use crate::prelude::*;

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
    canvas.background((255, 255, 255, 255)).unwrap();
    canvas
        .triangle_with_style(
            1.0,
            1.0,
            6.0,
            1.0,
            1.0,
            6.0,
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
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
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
fn gpu_closed_stroke_path_does_not_double_blend_at_corners() {
    let mut canvas = Canvas::new(24, 24, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 0)).unwrap();
    canvas
        .rect_with_style(
            4.0,
            4.0,
            16.0,
            16.0,
            &Style {
                fill: None,
                stroke: Some(Rgba {
                    r: 255,
                    g: 0,
                    b: 0,
                    a: 128,
                }),
                stroke_weight: 8.0,
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
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let pixel = |x: usize, y: usize| {
        let offset = (y * canvas.physical_width + x) * 4;
        &pixels[offset..offset + 4]
    };
    let corner_alpha = pixel(4, 4)[3];
    let edge_alpha = pixel(12, 4)[3];

    assert!(edge_alpha >= 120);
    assert!(corner_alpha <= edge_alpha.saturating_add(8));
}

#[test]
fn gpu_arc_stroke_command_renders_without_cpu_chord_vertices() {
    let mut canvas = Canvas::new(48, 48, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 0)).unwrap();
    canvas
        .draw_gpu_arc_stroke_with_matrix(
            (24.0, 24.0),
            (16.0, 12.0),
            0.2,
            5.3,
            "pie",
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            1.0,
            5.0,
            Rgba {
                r: 0,
                g: 120,
                b: 255,
                a: 255,
            },
            BlendMode::Blend,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels
        .chunks_exact(4)
        .any(|rgba| rgba[2] > 180 && rgba[3] > 0));
}

#[test]
fn gpu_arc_fill_command_renders_without_cpu_chord_vertices() {
    let mut canvas = Canvas::new(48, 48, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }
    let style = Style {
        fill: Some(Rgba {
            r: 0,
            g: 120,
            b: 255,
            a: 255,
        }),
        stroke: None,
        ..Style::default()
    };

    canvas.begin_frame();
    canvas.background((0, 0, 0, 0)).unwrap();
    canvas
        .arc_with_style(
            4.0,
            4.0,
            40.0,
            40.0,
            0.2,
            5.3,
            "pie",
            &style,
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels
        .chunks_exact(4)
        .any(|rgba| rgba[2] > 180 && rgba[3] > 0));
}

#[test]
fn gpu_filled_curve_segment_path_renders_without_cpu_flattened_vertices() {
    let mut canvas = Canvas::new(48, 48, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 0)).unwrap();
    canvas
        .draw_gpu_path_fill_with_matrix(
            &[
                crate::sketch_state::CapturedPathSegment::Line {
                    from: (8.0, 8.0),
                    to: (34.0, 8.0),
                },
                crate::sketch_state::CapturedPathSegment::Quadratic {
                    from: (34.0, 8.0),
                    control: (42.0, 28.0),
                    to: (22.0, 38.0),
                },
                crate::sketch_state::CapturedPathSegment::Cubic {
                    from: (22.0, 38.0),
                    control1: (16.0, 34.0),
                    control2: (4.0, 28.0),
                    to: (8.0, 8.0),
                },
            ],
            &[(8.0, 8.0), (34.0, 8.0), (22.0, 38.0), (8.0, 8.0)],
            true,
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            1.0,
            Rgba {
                r: 0,
                g: 120,
                b: 255,
                a: 255,
            },
            BlendMode::Blend,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels
        .chunks_exact(4)
        .any(|rgba| rgba[2] > 180 && rgba[3] > 0));
}

#[test]
fn gpu_captured_curve_segment_path_renders_without_cpu_flattened_vertices() {
    let mut canvas = Canvas::new(48, 48, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 0)).unwrap();
    canvas
        .draw_gpu_path_segments_with_matrix(
            &[
                crate::sketch_state::CapturedPathSegment::Quadratic {
                    from: (6.0, 34.0),
                    control: (18.0, 8.0),
                    to: (28.0, 28.0),
                },
                crate::sketch_state::CapturedPathSegment::Cubic {
                    from: (28.0, 28.0),
                    control1: (34.0, 44.0),
                    control2: (42.0, 8.0),
                    to: (44.0, 18.0),
                },
            ],
            &[(6.0, 34.0), (28.0, 28.0), (44.0, 18.0)],
            false,
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            1.0,
            5.0,
            Rgba {
                r: 0,
                g: 120,
                b: 255,
                a: 255,
            },
            BlendMode::Blend,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels
        .chunks_exact(4)
        .any(|rgba| rgba[2] > 180 && rgba[3] > 0));
}

#[test]
fn gpu_primitives_after_image_commands_are_rendered() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((0, 0, 0, 255)).unwrap();
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
        .triangle_with_style(
            4.0,
            4.0,
            7.0,
            4.0,
            4.0,
            7.0,
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
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [0, 0, 255, 255]));
    assert!(pixels.chunks_exact(4).any(|rgba| rgba == [0, 255, 0, 255]));
}

#[test]
fn full_pixel_upload_to_gpu_texture_without_pending_draws() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.background((0, 0, 0, 255)).unwrap();
    canvas.render_gpu_frame(true);
    canvas
        .update_pixels(vec![0, 0, 0, 255, 10, 20, 30, 255])
        .unwrap();

    assert!(canvas.texture_stale);
    assert!(canvas.render_dirty);
    assert!(!canvas.offscreen_dirty);

    canvas.upload_stale_texture(false).unwrap();
    canvas.pixels_stale = true;
    let pixels = canvas.load_pixels();

    assert_eq!(pixels, vec![0, 0, 0, 255, 10, 20, 30, 255]);
}
