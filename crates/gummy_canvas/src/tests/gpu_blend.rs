use crate::prelude::*;

fn multiply_style(fill: Rgba) -> Style {
    Style {
        fill: Some(fill),
        stroke: None,
        stroke_weight: 1.0,
        image_tint: None,
        blend_mode: BLEND_MODE_MULTIPLY.to_string(),
        blend_mode_kind: BlendMode::Multiply,
        erasing: false,
        image_sampling: "linear".to_string(),
        text_font_path: None,
        text_font_name: "default".to_string(),
        text_size: 12.0,
        text_align_x: "left".to_string(),
        text_align_y: "baseline".to_string(),
        text_leading: 14.0,
    }
}

#[test]
fn gpu_multiply_ellipse_blends_against_destination_texture() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((100, 100, 100, 255)).unwrap();
    canvas
        .draw_gpu_destination_blend_ellipse(
            4.0,
            4.0,
            3.0,
            3.0,
            &Style {
                fill: Some(Rgba {
                    r: 128,
                    g: 255,
                    b: 255,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_MULTIPLY.to_string(),
                blend_mode_kind: BlendMode::Multiply,
                erasing: false,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let center = (4 * canvas.physical_width + 4) * 4;
    assert_eq!(&pixels[center..center + 4], &[50, 100, 100, 255]);
}

#[test]
fn gpu_destination_blend_rect_preserves_order_hidpi_locality_and_counters() {
    let mut canvas = Canvas::new(8, 4, 2.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    let multiply = multiply_style(Rgba {
        r: 128,
        g: 255,
        b: 255,
        a: 255,
    });
    let mut overlay = multiply.clone();
    overlay.fill = Some(Rgba {
        r: 255,
        g: 0,
        b: 0,
        a: 255,
    });
    overlay.blend_mode = BLEND_MODE_BLEND.to_string();
    overlay.blend_mode_kind = BlendMode::Blend;

    canvas.begin_frame();
    canvas.background((100, 100, 100, 255)).unwrap();
    canvas
        .rect_with_style(
            1.0,
            1.0,
            2.0,
            1.0,
            &multiply,
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    canvas
        .rect_with_style(2.0, 1.0, 1.0, 1.0, &overlay, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let pixel = |x: usize, y: usize| {
        let offset = (y * canvas.physical_width + x) * 4;
        &pixels[offset..offset + 4]
    };
    assert_eq!(pixel(1, 2), &[100, 100, 100, 255]);
    assert_eq!(pixel(2, 2), &[50, 100, 100, 255]);
    assert_eq!(pixel(4, 2), &[255, 0, 0, 255]);
    assert_eq!(canvas.performance_counters.gpu_blend_commands, 1);
    assert_eq!(canvas.performance_counters.gpu_region_effect_passes, 1);
    assert_eq!(canvas.performance_counters.cpu_fallbacks, 0);
}

#[test]
fn gpu_destination_blend_rect_supports_all_destination_sampling_modes() {
    let cases = [
        (BlendMode::Darkest, BLEND_MODE_DARKEST, [64, 64, 192, 255]),
        (
            BlendMode::Lightest,
            BLEND_MODE_LIGHTEST,
            [128, 128, 255, 255],
        ),
        (
            BlendMode::Difference,
            BLEND_MODE_DIFFERENCE,
            [64, 64, 63, 255],
        ),
        (
            BlendMode::Exclusion,
            BLEND_MODE_EXCLUSION,
            [128, 128, 63, 255],
        ),
        (BlendMode::Multiply, BLEND_MODE_MULTIPLY, [32, 32, 192, 255]),
        (BlendMode::Screen, BLEND_MODE_SCREEN, [160, 160, 255, 255]),
    ];

    for (mode, mode_name, expected) in cases {
        let mut canvas = Canvas::new(4, 4, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
        if !canvas.gpu_available() {
            return;
        }
        let mut style = multiply_style(Rgba {
            r: 128,
            g: 64,
            b: 255,
            a: 255,
        });
        style.blend_mode = mode_name.to_string();
        style.blend_mode_kind = mode;

        canvas.begin_frame();
        canvas.background((64, 128, 192, 255)).unwrap();
        canvas
            .rect_with_style(1.0, 1.0, 2.0, 2.0, &style, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
            .unwrap();
        canvas.end_frame();

        let pixels = canvas.load_pixels();
        let center = (2 * canvas.physical_width + 2) * 4;
        assert_eq!(&pixels[center..center + 4], &expected, "mode {mode:?}");
        assert_eq!(canvas.performance_counters.cpu_fallbacks, 0);
    }
}

#[test]
fn gpu_destination_blend_rect_rejects_stroke_shear_and_clip() {
    let style = multiply_style(Rgba {
        r: 128,
        g: 255,
        b: 255,
        a: 255,
    });

    let mut stroked_canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !stroked_canvas.gpu_available() {
        return;
    }
    let mut stroked = style.clone();
    stroked.stroke = Some(Rgba {
        r: 255,
        g: 255,
        b: 255,
        a: 255,
    });
    assert!(stroked_canvas
        .rect_with_style(1.0, 1.0, 4.0, 4.0, &stroked, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),)
        .is_err());

    let mut sheared_canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    assert!(sheared_canvas
        .rect_with_style(1.0, 1.0, 4.0, 4.0, &style, (1.0, 0.1, 0.0, 1.0, 0.0, 0.0),)
        .is_err());

    let mut clipped_canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    clipped_canvas
        .begin_clip_impl(
            vec![(0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0)],
            Vec::new(),
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        )
        .unwrap();
    assert!(clipped_canvas
        .rect_with_style(1.0, 1.0, 4.0, 4.0, &style, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),)
        .is_err());
}

#[test]
fn gpu_multiple_blend_ellipses_keep_distinct_uniforms() {
    let mut canvas = Canvas::new(160, 120, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    let style = |color: Rgba| Style {
        fill: Some(color),
        stroke: None,
        stroke_weight: 1.0,
        image_tint: None,
        blend_mode: BLEND_MODE_MULTIPLY.to_string(),
        blend_mode_kind: BlendMode::Multiply,
        erasing: false,
        image_sampling: "linear".to_string(),
        text_font_path: None,
        text_font_name: "default".to_string(),
        text_size: 12.0,
        text_align_x: "left".to_string(),
        text_align_y: "baseline".to_string(),
        text_leading: 14.0,
    };

    canvas.begin_frame();
    canvas.background((28, 32, 42, 255)).unwrap();
    canvas
        .draw_gpu_destination_blend_ellipse(
            40.0,
            40.0,
            20.0,
            20.0,
            &style(Rgba {
                r: 250,
                g: 90,
                b: 90,
                a: 220,
            }),
        )
        .unwrap();
    canvas
        .draw_gpu_destination_blend_ellipse(
            90.0,
            40.0,
            20.0,
            20.0,
            &style(Rgba {
                r: 70,
                g: 220,
                b: 170,
                a: 220,
            }),
        )
        .unwrap();
    canvas
        .draw_gpu_destination_blend_ellipse(
            65.0,
            80.0,
            20.0,
            20.0,
            &style(Rgba {
                r: 90,
                g: 130,
                b: 250,
                a: 220,
            }),
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let pixel = |x: usize, y: usize| {
        let offset = (y * canvas.physical_width + x) * 4;
        &pixels[offset..offset + 4]
    };
    let background = &[28, 32, 42, 255];
    assert_ne!(pixel(40, 40), background);
    assert_ne!(pixel(90, 40), background);
    assert_ne!(pixel(65, 80), background);
}
