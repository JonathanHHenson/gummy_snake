use crate::*;

#[test]
fn gpu_multiply_ellipse_blends_against_destination_texture() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((100, 100, 100, 255));
    canvas
        .draw_gpu_blend_ellipse(
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
    canvas.background((28, 32, 42, 255));
    canvas
        .draw_gpu_blend_ellipse(
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
        .draw_gpu_blend_ellipse(
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
        .draw_gpu_blend_ellipse(
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
