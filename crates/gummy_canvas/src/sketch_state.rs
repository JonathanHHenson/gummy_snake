use crate::*;
use pyo3::exceptions::PyRuntimeError;
use std::time::Instant;

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
    width: i64,
    height: i64,
    physical_width: i64,
    physical_height: i64,
    pixel_density: f64,
    renderer: String,
    created: bool,
    start_time: Instant,
    last_frame_time: Instant,
    delta_time: f64,
    frame_count: i64,
    target_frame_rate: f64,
    looping: bool,
    redraw_requested: bool,
    mouse_x: f64,
    mouse_y: f64,
    previous_mouse_x: f64,
    previous_mouse_y: f64,
    moved_x: f64,
    moved_y: f64,
    mouse_is_pressed: bool,
    mouse_inside_window: bool,
    mouse_button: Option<String>,
    key: Option<String>,
    key_code: Option<i64>,
    code: Option<String>,
    text: Option<String>,
    text_input_active: bool,
    key_is_pressed: bool,
    pressed_keys: Vec<i64>,
    pressed_codes: Vec<String>,
    touch_supported: bool,
    pointer_locked: bool,
    pointer_lock_mode: String,
    touches: Vec<TouchSnapshot>,
    shape_active: bool,
    shape_vertices: Vec<(f64, f64)>,
    shape_contours: Vec<Vec<(f64, f64)>>,
    contour_active: bool,
    contour_vertices: Vec<(f64, f64)>,
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

#[pymethods]
impl SketchContextState {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    #[getter]
    fn width(&self) -> i64 {
        self.width
    }

    #[setter]
    fn set_width(&mut self, value: i64) {
        self.width = value;
    }

    #[getter]
    fn height(&self) -> i64 {
        self.height
    }

    #[setter]
    fn set_height(&mut self, value: i64) {
        self.height = value;
    }

    #[getter]
    fn physical_width(&self) -> i64 {
        self.physical_width
    }

    #[setter]
    fn set_physical_width(&mut self, value: i64) {
        self.physical_width = value;
    }

    #[getter]
    fn physical_height(&self) -> i64 {
        self.physical_height
    }

    #[setter]
    fn set_physical_height(&mut self, value: i64) {
        self.physical_height = value;
    }

    #[getter]
    fn pixel_density(&self) -> f64 {
        self.pixel_density
    }

    #[setter]
    fn set_pixel_density(&mut self, value: f64) {
        self.pixel_density = value;
    }

    #[getter]
    fn renderer(&self) -> String {
        self.renderer.clone()
    }

    #[setter]
    fn set_renderer(&mut self, value: String) {
        self.renderer = value;
    }

    #[getter]
    fn created(&self) -> bool {
        self.created
    }

    #[setter]
    fn set_created(&mut self, value: bool) {
        self.created = value;
    }

    #[getter]
    fn delta_time(&self) -> f64 {
        self.delta_time
    }

    #[getter]
    fn frame_count(&self) -> i64 {
        self.frame_count
    }

    #[setter]
    fn set_frame_count(&mut self, value: i64) {
        self.frame_count = value;
    }

    #[getter]
    fn target_frame_rate(&self) -> f64 {
        self.target_frame_rate
    }

    #[setter]
    fn set_target_frame_rate(&mut self, value: f64) {
        self.target_frame_rate = value;
    }

    #[getter]
    fn looping(&self) -> bool {
        self.looping
    }

    #[setter]
    fn set_looping(&mut self, value: bool) {
        self.looping = value;
    }

    #[getter]
    fn redraw_requested(&self) -> bool {
        self.redraw_requested
    }

    #[setter]
    fn set_redraw_requested(&mut self, value: bool) {
        self.redraw_requested = value;
    }

    fn begin_frame_timing(&mut self) {
        let now = Instant::now();
        self.delta_time = (now - self.last_frame_time).as_secs_f64() * 1000.0;
        self.last_frame_time = now;
    }

    fn increment_frame_count(&mut self) {
        self.frame_count += 1;
    }

    fn millis(&self) -> f64 {
        (Instant::now() - self.start_time).as_secs_f64() * 1000.0
    }

    fn sync_canvas(
        &mut self,
        width: i64,
        height: i64,
        physical_width: i64,
        physical_height: i64,
        pixel_density: f64,
        renderer: String,
        created: bool,
    ) {
        self.width = width;
        self.height = height;
        self.physical_width = physical_width;
        self.physical_height = physical_height;
        self.pixel_density = pixel_density;
        self.renderer = renderer;
        self.created = created;
    }

    #[getter]
    fn mouse_x(&self) -> f64 {
        self.mouse_x
    }

    #[getter]
    fn mouse_y(&self) -> f64 {
        self.mouse_y
    }

    #[getter]
    fn previous_mouse_x(&self) -> f64 {
        self.previous_mouse_x
    }

    #[setter]
    fn set_previous_mouse_x(&mut self, value: f64) {
        self.previous_mouse_x = value;
    }

    #[getter]
    fn previous_mouse_y(&self) -> f64 {
        self.previous_mouse_y
    }

    #[setter]
    fn set_previous_mouse_y(&mut self, value: f64) {
        self.previous_mouse_y = value;
    }

    #[getter]
    fn moved_x(&self) -> f64 {
        self.moved_x
    }

    #[getter]
    fn moved_y(&self) -> f64 {
        self.moved_y
    }

    #[getter]
    fn mouse_is_pressed(&self) -> bool {
        self.mouse_is_pressed
    }

    #[setter]
    fn set_mouse_is_pressed(&mut self, value: bool) {
        self.mouse_is_pressed = value;
    }

    #[getter]
    fn mouse_inside_window(&self) -> bool {
        self.mouse_inside_window
    }

    #[setter]
    fn set_mouse_inside_window(&mut self, value: bool) {
        self.mouse_inside_window = value;
    }

    #[getter]
    fn mouse_button(&self) -> Option<String> {
        self.mouse_button.clone()
    }

    #[setter]
    fn set_mouse_button(&mut self, value: Option<String>) {
        self.mouse_button = value;
    }

    #[getter]
    fn key(&self) -> Option<String> {
        self.key.clone()
    }

    #[setter]
    fn set_key(&mut self, value: Option<String>) {
        self.key = value;
    }

    #[getter]
    fn key_code(&self) -> Option<i64> {
        self.key_code
    }

    #[setter]
    fn set_key_code(&mut self, value: Option<i64>) {
        self.key_code = value;
    }

    #[getter]
    fn code(&self) -> Option<String> {
        self.code.clone()
    }

    #[setter]
    fn set_code(&mut self, value: Option<String>) {
        self.code = value;
    }

    #[getter]
    fn text(&self) -> Option<String> {
        self.text.clone()
    }

    #[setter]
    fn set_text(&mut self, value: Option<String>) {
        self.text = value;
    }

    #[getter]
    fn text_input_active(&self) -> bool {
        self.text_input_active
    }

    #[setter]
    fn set_text_input_active(&mut self, value: bool) {
        self.text_input_active = value;
    }

    #[getter]
    fn key_is_pressed(&self) -> bool {
        self.key_is_pressed
    }

    #[setter]
    fn set_key_is_pressed(&mut self, value: bool) {
        self.key_is_pressed = value;
    }

    #[getter]
    fn touch_supported(&self) -> bool {
        self.touch_supported
    }

    #[setter]
    fn set_touch_supported(&mut self, value: bool) {
        self.touch_supported = value;
    }

    #[getter]
    fn pointer_locked(&self) -> bool {
        self.pointer_locked
    }

    #[setter]
    fn set_pointer_locked(&mut self, value: bool) {
        self.pointer_locked = value;
    }

    #[getter]
    fn pointer_lock_mode(&self) -> String {
        self.pointer_lock_mode.clone()
    }

    #[setter]
    fn set_pointer_lock_mode(&mut self, value: String) {
        self.pointer_lock_mode = value;
    }

    #[pyo3(signature = (x, y, dx=None, dy=None))]
    fn update_mouse(&mut self, x: f64, y: f64, dx: Option<f64>, dy: Option<f64>) {
        self.previous_mouse_x = self.mouse_x;
        self.previous_mouse_y = self.mouse_y;
        self.mouse_x = x;
        self.mouse_y = y;
        self.moved_x = dx.unwrap_or(self.mouse_x - self.previous_mouse_x);
        self.moved_y = dy.unwrap_or(self.mouse_y - self.previous_mouse_y);
    }

    fn key_is_down(&self, key_code: i64) -> bool {
        self.pressed_keys.contains(&key_code)
    }

    fn code_is_down(&self, code: &str) -> bool {
        self.pressed_codes.iter().any(|value| value == code)
    }

    fn set_key_down(&mut self, key_code: i64, pressed: bool) {
        if pressed {
            add_unique(&mut self.pressed_keys, key_code);
        } else {
            self.pressed_keys.retain(|value| *value != key_code);
        }
    }

    fn set_code_down(&mut self, code: String, pressed: bool) {
        if pressed {
            add_unique(&mut self.pressed_codes, code);
        } else {
            self.pressed_codes.retain(|value| value != &code);
        }
    }

    fn update_touches(&mut self, touches: &Bound<'_, PyAny>) -> PyResult<()> {
        let old = self.touches.clone();
        let mut updated = Vec::new();
        for item in touches.iter()? {
            let touch = item?;
            let id: i64 = touch.getattr("id")?.extract()?;
            let x: f64 = touch.getattr("x")?.extract()?;
            let y: f64 = touch.getattr("y")?.extract()?;
            let previous = old.iter().find(|existing| existing.id == id);
            let previous_x = touch
                .getattr("previous_x")?
                .extract::<Option<f64>>()?
                .or_else(|| previous.map(|existing| existing.x));
            let previous_y = touch
                .getattr("previous_y")?
                .extract::<Option<f64>>()?
                .or_else(|| previous.map(|existing| existing.y));
            updated.push(TouchSnapshot {
                id,
                x,
                y,
                previous_x,
                previous_y,
                pressure: touch.getattr("pressure")?.extract()?,
                phase: touch.getattr("phase")?.extract()?,
                timestamp: touch.getattr("timestamp")?.extract()?,
                device: touch.getattr("device")?.extract()?,
            });
        }
        self.touches = updated;
        Ok(())
    }

    fn touch_payload<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let result = PyList::empty_bound(py);
        for touch in &self.touches {
            let item = PyDict::new_bound(py);
            item.set_item("id", touch.id)?;
            item.set_item("x", touch.x)?;
            item.set_item("y", touch.y)?;
            item.set_item("previous_x", touch.previous_x)?;
            item.set_item("previous_y", touch.previous_y)?;
            item.set_item("pressure", touch.pressure)?;
            item.set_item("phase", touch.phase.clone())?;
            item.set_item("timestamp", touch.timestamp)?;
            item.set_item("device", touch.device.clone())?;
            result.append(item)?;
        }
        Ok(result)
    }

    #[getter]
    fn shape_active(&self) -> bool {
        self.shape_active
    }

    #[getter]
    fn contour_active(&self) -> bool {
        self.contour_active
    }

    #[getter]
    fn shape_kind(&self) -> Option<String> {
        self.shape_kind.clone()
    }

    #[pyo3(signature = (kind=None))]
    fn begin_shape_capture(&mut self, kind: Option<String>) -> PyResult<()> {
        if self.shape_active {
            return Err(PyRuntimeError::new_err("begin_shape() cannot be nested."));
        }
        self.shape_active = true;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = kind;
        Ok(())
    }

    fn reset_shape_capture(&mut self) {
        self.shape_active = false;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = None;
    }

    fn add_vertex(&mut self, x: f64, y: f64) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            self.contour_vertices.push((x, y));
        } else {
            self.shape_vertices.push((x, y));
        }
        Ok(())
    }

    fn extend_vertices(&mut self, vertices: Vec<(f64, f64)>) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            self.contour_vertices.extend(vertices);
        } else {
            self.shape_vertices.extend(vertices);
        }
        Ok(())
    }

    fn active_vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let source = if self.contour_active {
            &self.contour_vertices
        } else {
            &self.shape_vertices
        };
        Ok(PyList::new_bound(py, source.iter().copied()))
    }

    fn shape_vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        Ok(PyList::new_bound(py, self.shape_vertices.iter().copied()))
    }

    fn shape_contours<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let result = PyList::empty_bound(py);
        for contour in &self.shape_contours {
            result.append(PyList::new_bound(py, contour.iter().copied()))?;
        }
        Ok(result)
    }

    fn shape_vertex_count(&self) -> usize {
        self.shape_vertices.len()
    }

    fn contour_vertex_count(&self) -> usize {
        self.contour_vertices.len()
    }

    fn begin_contour_capture(&mut self) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err("begin_contour() requires begin_shape()."));
        }
        if self.contour_active {
            return Err(PyRuntimeError::new_err("begin_contour() cannot be nested."));
        }
        if self.shape_kind.is_some() {
            return Err(PyRuntimeError::new_err(
                "begin_contour() is supported only for freeform begin_shape() paths.",
            ));
        }
        if self.shape_vertices.len() < 3 {
            return Err(PyRuntimeError::new_err(
                "begin_contour() requires at least three outer shape vertices first.",
            ));
        }
        self.contour_active = true;
        self.contour_vertices.clear();
        Ok(())
    }

    fn end_contour_capture(&mut self) -> PyResult<()> {
        if !self.shape_active || !self.contour_active {
            return Err(PyRuntimeError::new_err("end_contour() requires begin_contour()."));
        }
        if self.contour_vertices.len() < 3 {
            return Err(PyRuntimeError::new_err(
                "end_contour() requires at least three vertices.",
            ));
        }
        self.shape_contours.push(self.contour_vertices.clone());
        self.contour_vertices.clear();
        self.contour_active = false;
        Ok(())
    }

    fn reset_contour_capture(&mut self) {
        self.contour_vertices.clear();
        self.contour_active = false;
    }
}

impl SketchContextState {
    pub(crate) fn captured_shape_vertices(&self) -> &[(f64, f64)] {
        &self.shape_vertices
    }

    pub(crate) fn captured_shape_contours(&self) -> &[Vec<(f64, f64)>] {
        &self.shape_contours
    }

    pub(crate) fn reset_captured_shape(&mut self) {
        self.shape_active = false;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = None;
    }
}
