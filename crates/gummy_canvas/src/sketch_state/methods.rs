use super::SketchContextState;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyList};

#[pymethods]
impl SketchContextState {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    fn begin_frame_timing(&mut self) {
        self.begin_frame_timing_impl();
    }

    fn increment_frame_count(&mut self) {
        self.increment_frame_count_impl();
    }

    fn millis(&self) -> f64 {
        self.millis_impl()
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
        self.sync_canvas_impl(
            width,
            height,
            physical_width,
            physical_height,
            pixel_density,
            renderer,
            created,
        );
    }

    #[pyo3(signature = (x, y, dx=None, dy=None))]
    fn update_mouse(&mut self, x: f64, y: f64, dx: Option<f64>, dy: Option<f64>) {
        self.update_mouse_impl(x, y, dx, dy);
    }

    fn key_is_down(&self, key_code: i64) -> bool {
        self.key_is_down_impl(key_code)
    }

    fn code_is_down(&self, code: &str) -> bool {
        self.code_is_down_impl(code)
    }

    fn set_key_down(&mut self, key_code: i64, pressed: bool) {
        self.set_key_down_impl(key_code, pressed);
    }

    fn set_code_down(&mut self, code: String, pressed: bool) {
        self.set_code_down_impl(code, pressed);
    }

    fn update_touches(&mut self, touches: &Bound<'_, PyAny>) -> PyResult<()> {
        self.update_touches_impl(touches)
    }

    fn touch_payload<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        self.touch_payload_impl(py)
    }

    #[pyo3(signature = (kind=None))]
    fn begin_shape_capture(&mut self, kind: Option<String>) -> PyResult<()> {
        self.begin_shape_capture_impl(kind)
    }

    fn reset_shape_capture(&mut self) {
        self.reset_shape_capture_impl();
    }

    fn add_vertex(&mut self, x: f64, y: f64) -> PyResult<()> {
        self.add_vertex_impl(x, y)
    }

    fn add_quadratic_vertex(&mut self, cx: f64, cy: f64, x: f64, y: f64) -> PyResult<()> {
        self.add_quadratic_vertex_impl(cx, cy, x, y)
    }

    fn add_cubic_vertex(
        &mut self,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
    ) -> PyResult<()> {
        self.add_cubic_vertex_impl(x2, y2, x3, y3, x4, y4)
    }

    fn extend_vertices(&mut self, vertices: Vec<(f64, f64)>) -> PyResult<()> {
        self.extend_vertices_impl(vertices)
    }

    fn active_vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        self.active_vertices_impl(py)
    }

    fn shape_vertices<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        self.shape_vertices_impl(py)
    }

    fn shape_contours<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        self.shape_contours_impl(py)
    }

    fn shape_vertex_count(&self) -> usize {
        self.shape_vertex_count_impl()
    }

    fn contour_vertex_count(&self) -> usize {
        self.contour_vertex_count_impl()
    }

    fn begin_contour_capture(&mut self) -> PyResult<()> {
        self.begin_contour_capture_impl()
    }

    fn end_contour_capture(&mut self) -> PyResult<()> {
        self.end_contour_capture_impl()
    }

    fn reset_contour_capture(&mut self) {
        self.reset_contour_capture_impl();
    }
}
