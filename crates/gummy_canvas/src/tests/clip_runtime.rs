use crate::prelude::*;

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
