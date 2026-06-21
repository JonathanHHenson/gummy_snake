use crate::*;
#[pymethods]
impl Canvas {
    #[new]
    pub(crate) fn new(
        width: i64,
        height: i64,
        pixel_density: f64,
        mode: &str,
        renderer: &str,
    ) -> PyResult<Self> {
        Self::new_impl(width, height, pixel_density, mode, renderer)
    }
    pub(crate) fn resize(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        renderer: &str,
    ) -> PyResult<()> {
        self.resize_impl(width, height, pixel_density, renderer)
    }
    pub(crate) fn resize_canvas(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        renderer: &str,
    ) -> PyResult<()> {
        self.resize_canvas_impl(width, height, pixel_density, renderer)
    }
    pub(crate) fn dimensions(&self) -> (i64, i64, usize, usize, f64) {
        self.dimensions_impl()
    }
    pub(crate) fn display_density(&self) -> f64 {
        self.display_density_impl()
    }
    pub(crate) fn native_window_available(&self) -> bool {
        self.native_window_available_impl()
    }
    pub(crate) fn gpu_available(&self) -> bool {
        self.gpu_available_impl()
    }
    pub(crate) fn gpu_status(&self) -> String {
        self.gpu_status_impl()
    }
    pub(crate) fn performance_counters<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        self.performance_counters_impl(py)
    }
    pub(crate) fn reset_performance_counters(&mut self) {
        self.reset_performance_counters_impl()
    }
    pub(crate) fn open_window(&mut self) -> PyResult<()> {
        self.open_window_impl()
    }
    pub(crate) fn should_close(&self) -> bool {
        self.should_close_impl()
    }
    pub(crate) fn poll_events(&mut self) -> PyResult<Vec<Py<PyAny>>> {
        self.poll_events_impl()
    }
    pub(crate) fn pump_native_events(&mut self) -> PyResult<bool> {
        self.pump_native_events_impl()
    }
    pub(crate) fn request_pointer_lock(&mut self) -> PyResult<bool> {
        self.request_pointer_lock_impl()
    }
    pub(crate) fn exit_pointer_lock(&mut self) -> PyResult<bool> {
        self.exit_pointer_lock_impl()
    }
    pub(crate) fn pointer_locked(&self) -> bool {
        self.pointer_locked_impl()
    }
    pub(crate) fn set_pointer_lock_mode(&mut self, mode: &str) -> PyResult<()> {
        self.set_pointer_lock_mode_impl(mode)
    }
    pub(crate) fn pointer_lock_mode(&self) -> String {
        self.pointer_lock_mode_impl()
    }
    pub(crate) fn start_text_input(&mut self) -> PyResult<bool> {
        self.start_text_input_impl()
    }
    pub(crate) fn stop_text_input(&mut self) -> PyResult<bool> {
        self.stop_text_input_impl()
    }
    pub(crate) fn text_input_active(&self) -> bool {
        self.text_input_active_impl()
    }
    pub(crate) fn begin_frame(&mut self) {
        self.begin_frame_impl()
    }
    pub(crate) fn end_frame(&mut self) {
        self.end_frame_impl()
    }
    pub(crate) fn present(&mut self) -> PyResult<()> {
        self.present_impl()
    }
    pub(crate) fn close(&mut self) {
        self.close_impl()
    }
    pub(crate) fn background(&mut self, rgba: (u8, u8, u8, u8)) {
        self.background_impl(rgba)
    }
    pub(crate) fn clear(&mut self) {
        self.clear_impl()
    }
    pub(crate) fn point(
        &mut self,
        x: f64,
        y: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.point_impl(x, y, style, matrix)
    }
    pub(crate) fn line(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.line_impl(x1, y1, x2, y2, style, matrix)
    }
    pub(crate) fn batch_lines(
        &mut self,
        lines: Vec<(f64, f64, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_lines_impl(lines, style, matrix)
    }
    #[pyo3(signature = (points, style, matrix, close=true))]
    pub(crate) fn polygon(
        &mut self,
        points: Vec<(f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        self.polygon_impl(points, style, matrix, close)
    }
    #[pyo3(signature = (outer, contours, style, matrix, close=true))]
    pub(crate) fn complex_polygon(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        self.complex_polygon_impl(outer, contours, style, matrix, close)
    }
    pub(crate) fn begin_clip(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.begin_clip_impl(outer, contours, matrix)
    }
    pub(crate) fn end_clip(&mut self) -> PyResult<()> {
        self.end_clip_impl()
    }
    pub(crate) fn rect(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.rect_impl(x, y, width, height, style, matrix)
    }
    pub(crate) fn triangle(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.triangle_impl(x1, y1, x2, y2, x3, y3, style, matrix)
    }
    pub(crate) fn quad(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.quad_impl(x1, y1, x2, y2, x3, y3, x4, y4, style, matrix)
    }
    pub(crate) fn ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.ellipse_impl(x, y, width, height, style, matrix)
    }
    pub(crate) fn arc(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        stop: f64,
        mode: &str,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.arc_impl(x, y, width, height, start, stop, mode, style, matrix)
    }
    #[pyo3(signature = (image_pixels, image_width, image_height, dx, dy, dw, dh, style, matrix, source=None))]
    pub(crate) fn draw_image(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_image_impl(
            image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }
    #[pyo3(signature = (image_key, image_version, image_pixels, image_width, image_height, dx, dy, dw, dh, style, matrix, source=None))]
    pub(crate) fn draw_cached_image(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_cached_image_impl(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }
    #[pyo3(signature = (image, dx, dy, dw, dh, style, matrix, source=None))]
    pub(crate) fn draw_canvas_image(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_canvas_image_impl(image, dx, dy, dw, dh, style, matrix, source)
    }
    pub(crate) fn text(
        &mut self,
        value: &str,
        x: f64,
        y: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.text_impl(value, x, y, style, matrix)
    }
    pub(crate) fn text_width(&mut self, value: &str, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_width_impl(value, style)
    }
    pub(crate) fn text_ascent(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_ascent_impl(style)
    }
    pub(crate) fn text_descent(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_descent_impl(style)
    }
    #[pyo3(signature = (source_pixels, source_width, source_height, source, destination, mode))]
    pub(crate) fn blend_region(
        &mut self,
        source_pixels: Option<Vec<u8>>,
        source_width: Option<usize>,
        source_height: Option<usize>,
        source: (i64, i64, i64, i64),
        destination: (i64, i64, i64, i64),
        mode: &str,
    ) -> PyResult<()> {
        self.blend_region_impl(
            source_pixels,
            source_width,
            source_height,
            source,
            destination,
            mode,
        )
    }
    pub(crate) fn load_pixels(&mut self) -> Vec<u8> {
        self.load_pixels_impl()
    }
    pub(crate) fn load_pixel_bytes<'py>(&mut self, py: Python<'py>) -> Bound<'py, PyBytes> {
        self.load_pixel_bytes_impl(py)
    }
    pub(crate) fn load_pixel_region<'py>(
        &mut self,
        py: Python<'py>,
        x: i64,
        y: i64,
        width: i64,
        height: i64,
    ) -> PyResult<Bound<'py, PyBytes>> {
        self.load_pixel_region_impl(py, x, y, width, height)
    }
    pub(crate) fn update_pixels(&mut self, pixels: Vec<u8>) -> PyResult<()> {
        self.update_pixels_impl(pixels)
    }
    pub(crate) fn set_pixel_rgba(
        &mut self,
        x: i64,
        y: i64,
        rgba: (u8, u8, u8, u8),
    ) -> PyResult<()> {
        self.set_pixel_rgba_impl(x, y, rgba)
    }
    #[pyo3(signature = (pixels, width, height, x, y, alpha_composite = true))]
    pub(crate) fn update_pixel_region(
        &mut self,
        pixels: Vec<u8>,
        width: usize,
        height: usize,
        x: i64,
        y: i64,
        alpha_composite: bool,
    ) -> PyResult<()> {
        self.update_pixel_region_impl(pixels, width, height, x, y, alpha_composite)
    }
    #[pyo3(signature = (mode, value=None))]
    pub(crate) fn filter_pixels(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        self.filter_pixels_impl(mode, value)
    }
    pub(crate) fn save(&mut self, path: &str) -> PyResult<()> {
        self.save_impl(path)
    }
}
