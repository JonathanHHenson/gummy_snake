use crate::*;

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
