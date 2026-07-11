mod canvas;
mod input;
mod methods;
mod shape;

use crate::runtime::DEFAULT_POINTER_LOCK_MODE;
use pyo3::prelude::*;
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum CapturedPathSegment {
    Line {
        from: (f64, f64),
        to: (f64, f64),
    },
    Quadratic {
        from: (f64, f64),
        control: (f64, f64),
        to: (f64, f64),
    },
    Cubic {
        from: (f64, f64),
        control1: (f64, f64),
        control2: (f64, f64),
        to: (f64, f64),
    },
}

#[derive(Clone, Debug)]
struct TouchSnapshot {
    id: i64,
    x: f64,
    y: f64,
    previous_x: Option<f64>,
    previous_y: Option<f64>,
    pressure: Option<f64>,
    phase: Option<String>,
    timestamp: Option<f64>,
    device: Option<String>,
}

#[pyclass(name = "SketchContextState", unsendable)]
pub(crate) struct SketchContextState {
    #[pyo3(get, set)]
    width: i64,
    #[pyo3(get, set)]
    height: i64,
    #[pyo3(get, set)]
    physical_width: i64,
    #[pyo3(get, set)]
    physical_height: i64,
    #[pyo3(get, set)]
    pixel_density: f64,
    #[pyo3(get, set)]
    renderer: String,
    #[pyo3(get, set)]
    created: bool,
    start_time: Instant,
    last_frame_time: Instant,
    #[pyo3(get)]
    delta_time: f64,
    #[pyo3(get, set)]
    frame_count: i64,
    #[pyo3(get, set)]
    target_frame_rate: f64,
    #[pyo3(get, set)]
    looping: bool,
    #[pyo3(get, set)]
    redraw_requested: bool,
    #[pyo3(get)]
    mouse_x: f64,
    #[pyo3(get)]
    mouse_y: f64,
    #[pyo3(get, set)]
    previous_mouse_x: f64,
    #[pyo3(get, set)]
    previous_mouse_y: f64,
    #[pyo3(get)]
    moved_x: f64,
    #[pyo3(get)]
    moved_y: f64,
    #[pyo3(get, set)]
    mouse_is_pressed: bool,
    #[pyo3(get, set)]
    mouse_inside_window: bool,
    #[pyo3(get, set)]
    mouse_button: Option<String>,
    #[pyo3(get, set)]
    key: Option<String>,
    #[pyo3(get, set)]
    key_code: Option<i64>,
    #[pyo3(get, set)]
    code: Option<String>,
    #[pyo3(get, set)]
    text: Option<String>,
    #[pyo3(get, set)]
    text_input_active: bool,
    #[pyo3(get, set)]
    key_is_pressed: bool,
    pressed_keys: Vec<i64>,
    pressed_codes: Vec<String>,
    #[pyo3(get, set)]
    touch_supported: bool,
    #[pyo3(get, set)]
    pointer_locked: bool,
    #[pyo3(get, set)]
    pointer_lock_mode: String,
    touches: Vec<TouchSnapshot>,
    #[pyo3(get)]
    shape_active: bool,
    shape_vertices: Vec<(f64, f64)>,
    shape_contours: Vec<Vec<(f64, f64)>>,
    shape_path_segments: Vec<CapturedPathSegment>,
    #[pyo3(get)]
    contour_active: bool,
    contour_vertices: Vec<(f64, f64)>,
    #[pyo3(get)]
    shape_kind: Option<String>,
}

impl Default for SketchContextState {
    fn default() -> Self {
        let now = Instant::now();
        Self {
            width: 100,
            height: 100,
            physical_width: 100,
            physical_height: 100,
            pixel_density: 1.0,
            renderer: "p2d".to_string(),
            created: false,
            start_time: now,
            last_frame_time: now,
            delta_time: 0.0,
            frame_count: 0,
            target_frame_rate: 60.0,
            looping: true,
            redraw_requested: false,
            mouse_x: 0.0,
            mouse_y: 0.0,
            previous_mouse_x: 0.0,
            previous_mouse_y: 0.0,
            moved_x: 0.0,
            moved_y: 0.0,
            mouse_is_pressed: false,
            mouse_inside_window: false,
            mouse_button: None,
            key: None,
            key_code: None,
            code: None,
            text: None,
            text_input_active: false,
            key_is_pressed: false,
            pressed_keys: Vec::new(),
            pressed_codes: Vec::new(),
            touch_supported: false,
            pointer_locked: false,
            pointer_lock_mode: DEFAULT_POINTER_LOCK_MODE.to_string(),
            touches: Vec::new(),
            shape_active: false,
            shape_vertices: Vec::new(),
            shape_contours: Vec::new(),
            shape_path_segments: Vec::new(),
            contour_active: false,
            contour_vertices: Vec::new(),
            shape_kind: None,
        }
    }
}

fn add_unique<T: PartialEq>(values: &mut Vec<T>, value: T) {
    if !values.contains(&value) {
        values.push(value);
    }
}
