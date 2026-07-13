use crate::bindings::{health_check, native_window_available};
use crate::prelude::*;

#[test]
fn health_check_reports_canvas_backend() {
    assert_eq!(health_check(), "rust-canvas");
    assert_eq!(native_window_available(), runtime_native_window_available());
}

#[test]
fn canvas_tracks_logical_and_physical_dimensions_without_eager_cpu_buffers() {
    let canvas = Canvas::new(10, 8, 2.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    assert_eq!(canvas.dimensions(), (10, 8, 20, 16, 2.0));
    assert!(canvas.pixels.is_empty());
    assert!(canvas.present_pixels.is_empty());
}

#[test]
fn explicit_pixel_paths_allocate_cpu_buffers_lazily() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    assert_eq!(canvas.load_pixels(), vec![0; 8]);
    assert_eq!(canvas.pixels.len(), 8);
    assert!(canvas.present_pixels.is_empty());

    canvas.set_pixel_rgba(1, 0, (10, 20, 30, 255)).unwrap();
    assert_eq!(canvas.present_pixels.len(), 2);
    assert_eq!(canvas.load_pixels(), vec![0, 0, 0, 0, 10, 20, 30, 255]);

    canvas.resize_canvas(3, 1, 1.0, SUPPORTED_RENDERER).unwrap();
    assert!(canvas.pixels.is_empty());
    assert!(canvas.present_pixels.is_empty());
}

#[test]
fn canvas_rejects_invalid_dimensions_and_density() {
    assert!(Canvas::new(0, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
    assert!(Canvas::new(10, 8, 0.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
}

#[test]
fn canvas_resize_noop_preserves_pixels() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }
    canvas.background((10, 20, 30, 255)).unwrap();

    canvas
        .resize_canvas(2, 1, 1.0, SUPPORTED_RENDERER)
        .expect("same-size backing resize should succeed");

    assert_eq!(canvas.load_pixels(), vec![10, 20, 30, 255, 10, 20, 30, 255]);
}

#[test]
fn background_clear_and_pixel_update_round_trip() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    if !canvas.gpu_available() {
        return;
    }
    canvas.background((10, 20, 30, 255)).unwrap();
    assert_eq!(canvas.load_pixels(), vec![10, 20, 30, 255, 10, 20, 30, 255]);

    canvas
        .update_pixels(vec![255, 0, 0, 255, 0, 0, 255, 255])
        .unwrap();
    assert_eq!(canvas.load_pixels(), vec![255, 0, 0, 255, 0, 0, 255, 255]);

    canvas.clear().unwrap();
    assert_eq!(canvas.load_pixels(), vec![0; 8]);
}

#[test]
fn set_pixel_rgba_ignores_out_of_bounds_without_cpu_compositing() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

    canvas.set_pixel_rgba(-1, 0, (255, 0, 0, 255)).unwrap();
    canvas.set_pixel_rgba(2, 0, (255, 0, 0, 255)).unwrap();

    assert_eq!(canvas.load_pixels(), vec![0; 8]);
}

#[test]
fn canvas_save_gif_writes_gif_file() {
    let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    canvas
        .update_pixels(vec![10, 20, 30, 255, 10, 20, 30, 255])
        .unwrap();
    let path =
        std::env::temp_dir().join(format!("gummy_canvas_test_{}_save.gif", std::process::id()));
    let path_string = path.to_string_lossy().to_string();

    canvas.save_gif(&path_string, 2, 50).unwrap();

    let bytes = std::fs::read(&path).unwrap();
    assert!(bytes.starts_with(b"GIF"));
    let _ = std::fs::remove_file(path);
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
