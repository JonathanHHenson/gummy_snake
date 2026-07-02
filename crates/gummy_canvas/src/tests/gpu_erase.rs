use crate::*;

#[test]
fn gpu_erase_preserves_destination_rgb_and_clears_alpha() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((100, 120, 140, 255)).unwrap();
    canvas
        .draw_gpu_axis_aligned_ellipse(
            4.0,
            4.0,
            3.0,
            3.0,
            &Style {
                fill: Some(Rgba {
                    r: 255,
                    g: 255,
                    b: 255,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_BLEND.to_string(),
                blend_mode_kind: BlendMode::Blend,
                erasing: true,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
            1.0,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let center = (4 * canvas.physical_width + 4) * 4;
    assert_eq!(&pixels[center..center + 4], &[100, 120, 140, 0]);
}

#[test]
fn gpu_erase_after_overlay_reveals_background_rgb() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((28, 32, 42, 255)).unwrap();
    canvas
        .rect_with_style(
            1.0,
            1.0,
            6.0,
            6.0,
            &Style {
                fill: Some(Rgba {
                    r: 255,
                    g: 255,
                    b: 255,
                    a: 235,
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
    canvas
        .draw_gpu_axis_aligned_ellipse(
            4.0,
            4.0,
            2.0,
            2.0,
            &Style {
                fill: Some(Rgba {
                    r: 255,
                    g: 255,
                    b: 255,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                image_tint: None,
                blend_mode: BLEND_MODE_BLEND.to_string(),
                blend_mode_kind: BlendMode::Blend,
                erasing: true,
                image_sampling: "linear".to_string(),
                text_font_path: None,
                text_font_name: "default".to_string(),
                text_size: 12.0,
                text_align_x: "left".to_string(),
                text_align_y: "baseline".to_string(),
                text_leading: 14.0,
            },
            1.0,
        )
        .unwrap();
    canvas.end_frame();

    let pixels = canvas.load_pixels();
    let center = (4 * canvas.physical_width + 4) * 4;
    assert_eq!(&pixels[center..center + 4], &[28, 32, 42, 0]);
}

#[test]
fn gpu_overlay_after_cpu_upload_does_not_replay_previous_clear() {
    let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }

    canvas.begin_frame();
    canvas.background((255, 255, 255, 255)).unwrap();
    canvas.render_gpu_frame(true);

    let preserved_pixel_offset = (7 * canvas.physical_width + 7) * 4;
    let mut pixels = canvas.pixels.clone();
    pixels[preserved_pixel_offset..preserved_pixel_offset + 4].copy_from_slice(&[255, 0, 0, 255]);
    canvas.update_pixels(pixels).unwrap();
    canvas
        .triangle_with_style(
            1.0,
            1.0,
            3.0,
            1.0,
            1.0,
            3.0,
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
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
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
