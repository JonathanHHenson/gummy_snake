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
    pub(crate) fn set_current_style(&mut self, style: &Bound<'_, PyAny>) -> PyResult<()> {
        self.set_current_style_impl(style)
    }
    pub(crate) fn current_style<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        self.current_style_impl(py)
    }
    pub(crate) fn set_current_matrix(&mut self, matrix: Matrix) {
        self.set_current_matrix_impl(matrix)
    }
    pub(crate) fn current_matrix(&self) -> Matrix {
        self.current_matrix_impl()
    }
    pub(crate) fn push_canvas_state(&mut self) {
        self.push_canvas_state_impl()
    }
    pub(crate) fn pop_canvas_state(&mut self) -> PyResult<()> {
        self.pop_canvas_state_impl()
    }
    pub(crate) fn translate(&mut self, x: f64, y: f64) {
        self.translate_impl(x, y)
    }
    pub(crate) fn rotate(&mut self, angle: f64) {
        self.rotate_impl(angle)
    }
    #[pyo3(signature = (x, y=None))]
    pub(crate) fn scale(&mut self, x: f64, y: Option<f64>) {
        self.scale_impl(x, y)
    }
    pub(crate) fn shear_x(&mut self, angle: f64) {
        self.shear_x_impl(angle)
    }
    pub(crate) fn shear_y(&mut self, angle: f64) {
        self.shear_y_impl(angle)
    }
    pub(crate) fn apply_matrix(&mut self, matrix: Matrix) {
        self.apply_matrix_impl(matrix)
    }
    pub(crate) fn reset_matrix(&mut self) {
        self.reset_matrix_impl()
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
    pub(crate) fn point_current(&mut self, py: Python<'_>, x: f64, y: f64) -> PyResult<()> {
        let _ = py;
        self.point_current_impl(x, y)
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
    pub(crate) fn line_current(
        &mut self,
        py: Python<'_>,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.line_current_impl(x1, y1, x2, y2)
    }
    pub(crate) fn batch_lines(
        &mut self,
        lines: Vec<(f64, f64, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_lines_impl(lines, style, matrix)
    }
    pub(crate) fn batch_lines_current(
        &mut self,
        py: Python<'_>,
        lines: Vec<(f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.batch_lines_current_impl(lines)
    }
    pub(crate) fn batch_primitives(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_primitives_impl(records, style, matrix)
    }
    pub(crate) fn batch_primitives_current(
        &mut self,
        py: Python<'_>,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.batch_primitives_current_impl(records)
    }
    pub(crate) fn batch_fill_primitives(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8)>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_fill_primitives_impl(records, matrix)
    }
    pub(crate) fn replay_fill_primitive_batch(&mut self) -> PyResult<bool> {
        self.replay_fill_primitive_batch_impl()
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
    #[pyo3(signature = (points, close=true))]
    pub(crate) fn polygon_current(
        &mut self,
        py: Python<'_>,
        points: Vec<(f64, f64)>,
        close: bool,
    ) -> PyResult<()> {
        let _ = py;
        self.polygon_current_impl(points, close)
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
    #[pyo3(signature = (outer, contours, close=true))]
    pub(crate) fn complex_polygon_current(
        &mut self,
        py: Python<'_>,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        close: bool,
    ) -> PyResult<()> {
        let _ = py;
        self.complex_polygon_current_impl(outer, contours, close)
    }
    pub(crate) fn begin_clip(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.begin_clip_impl(outer, contours, matrix)
    }
    pub(crate) fn begin_clip_current(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
    ) -> PyResult<()> {
        self.begin_clip_impl(outer, contours, self.current_matrix)
    }
    #[pyo3(signature = (state, close=true))]
    pub(crate) fn draw_captured_shape_current(
        &mut self,
        mut state: PyRefMut<'_, crate::sketch_state::SketchContextState>,
        close: bool,
    ) -> PyResult<()> {
        self.draw_captured_shape_current_impl(&mut state, close)
    }
    #[pyo3(signature = (state, style, matrix, close=true))]
    pub(crate) fn draw_captured_shape(
        &mut self,
        mut state: PyRefMut<'_, crate::sketch_state::SketchContextState>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        self.draw_captured_shape_impl(&mut state, style, matrix, close)
    }
    pub(crate) fn begin_clip_captured_current(
        &mut self,
        mut state: PyRefMut<'_, crate::sketch_state::SketchContextState>,
    ) -> PyResult<()> {
        self.begin_clip_captured_current_impl(&mut state)
    }
    pub(crate) fn begin_clip_captured(
        &mut self,
        mut state: PyRefMut<'_, crate::sketch_state::SketchContextState>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.begin_clip_captured_impl(&mut state, matrix)
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
    pub(crate) fn rect_current(
        &mut self,
        py: Python<'_>,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.rect_current_impl(x, y, width, height)
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
    pub(crate) fn triangle_current(
        &mut self,
        py: Python<'_>,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.triangle_current_impl(x1, y1, x2, y2, x3, y3)
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
    pub(crate) fn quad_current(
        &mut self,
        py: Python<'_>,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.quad_current_impl(x1, y1, x2, y2, x3, y3, x4, y4)
    }
    pub(crate) fn shaded_faces(&mut self, faces: &Bound<'_, PyAny>) -> PyResult<()> {
        self.shaded_faces_impl(faces)
    }
    #[pyo3(signature = (model, camera, projection, viewport_width, viewport_height, material, lights, normal_material, cull_backfaces, transform=None))]
    pub(crate) fn draw_model_shaded(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<(f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        self.draw_model_shaded_impl(
            model,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
        )
    }
    #[pyo3(signature = (model, image, camera, projection, viewport_width, viewport_height, material, lights, normal_material, cull_backfaces, transform=None))]
    pub(crate) fn draw_model_textured(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        image: PyRef<'_, CanvasImage>,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<(f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<bool> {
        self.draw_model_textured_impl(
            model,
            image,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
        )
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
    pub(crate) fn ellipse_current(
        &mut self,
        py: Python<'_>,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.ellipse_current_impl(x, y, width, height)
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
    pub(crate) fn arc_current(
        &mut self,
        py: Python<'_>,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        stop: f64,
        mode: &str,
    ) -> PyResult<()> {
        let style = self.current_style_payload_impl(py)?;
        self.arc_impl(
            x,
            y,
            width,
            height,
            start,
            stop,
            mode,
            style.as_any(),
            self.current_matrix,
        )
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
    #[pyo3(signature = (image_pixels, image_width, image_height, dx, dy, dw, dh, source=None))]
    pub(crate) fn draw_image_current(
        &mut self,
        py: Python<'_>,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.draw_image_current_impl(
            image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
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
    #[pyo3(signature = (image_key, image_version, image_pixels, image_width, image_height, dx, dy, dw, dh, source=None))]
    pub(crate) fn draw_cached_image_current(
        &mut self,
        py: Python<'_>,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.draw_cached_image_current_impl(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
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
    #[pyo3(signature = (image, dx, dy, dw, dh, source=None))]
    pub(crate) fn draw_canvas_image_current(
        &mut self,
        py: Python<'_>,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.draw_canvas_image_current_impl(image, dx, dy, dw, dh, source)
    }
    pub(crate) fn batch_canvas_images(
        &mut self,
        records: &Bound<'_, PyAny>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_canvas_images_impl(records, style, matrix)
    }
    pub(crate) fn batch_canvas_image_motion_terms(
        &mut self,
        records: Vec<u8>,
        images: Vec<PyRef<'_, CanvasImage>>,
        frame: u64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.batch_canvas_image_motion_terms_impl(&records, images, frame, style, matrix)
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
    pub(crate) fn text_current(
        &mut self,
        py: Python<'_>,
        value: &str,
        x: f64,
        y: f64,
    ) -> PyResult<()> {
        let _ = py;
        self.text_current_impl(value, x, y)
    }
    pub(crate) fn text_batch(
        &mut self,
        items: Vec<(String, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        self.text_batch_impl(items, style, matrix)
    }
    pub(crate) fn text_batch_current(
        &mut self,
        py: Python<'_>,
        items: Vec<(String, f64, f64)>,
    ) -> PyResult<()> {
        let _ = py;
        self.text_batch_current_impl(items)
    }
    pub(crate) fn text_batch_frame(
        &mut self,
        items: Vec<(String, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<bool> {
        self.text_batch_frame_impl(items, style, matrix)
    }
    pub(crate) fn text_batch_frame_current(
        &mut self,
        py: Python<'_>,
        items: Vec<(String, f64, f64)>,
    ) -> PyResult<bool> {
        let _ = py;
        self.text_batch_frame_current_impl(items)
    }
    pub(crate) fn text_width(&mut self, value: &str, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_width_impl(value, style)
    }
    pub(crate) fn text_width_current(&mut self, py: Python<'_>, value: &str) -> PyResult<f64> {
        let _ = py;
        self.text_width_current_impl(value)
    }
    pub(crate) fn text_ascent(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_ascent_impl(style)
    }
    pub(crate) fn text_ascent_current(&mut self, py: Python<'_>) -> PyResult<f64> {
        let style = self.current_style_payload_impl(py)?;
        self.text_ascent_impl(style.as_any())
    }
    pub(crate) fn text_descent(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.text_descent_impl(style)
    }
    pub(crate) fn text_descent_current(&mut self, py: Python<'_>) -> PyResult<f64> {
        let style = self.current_style_payload_impl(py)?;
        self.text_descent_impl(style.as_any())
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
    pub(crate) fn update_pixel_buffer(
        &mut self,
        py: Python<'_>,
        pixels: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.update_pixel_buffer_impl(py, pixels)
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
    pub(crate) fn update_pixel_region_buffer(
        &mut self,
        py: Python<'_>,
        pixels: &Bound<'_, PyAny>,
        width: usize,
        height: usize,
        x: i64,
        y: i64,
        alpha_composite: bool,
    ) -> PyResult<()> {
        self.update_pixel_region_buffer_impl(py, pixels, width, height, x, y, alpha_composite)
    }
    pub(crate) fn adjust_pixel_prefix(
        &mut self,
        byte_limit: usize,
        stride: usize,
        red_delta: i16,
        green_delta: i16,
    ) -> PyResult<()> {
        self.adjust_pixel_prefix_impl(byte_limit, stride, red_delta, green_delta)
    }
    #[pyo3(signature = (mode, value=None))]
    pub(crate) fn filter_pixels(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        self.filter_pixels_impl(mode, value)
    }
    pub(crate) fn save(&mut self, path: &str) -> PyResult<()> {
        self.save_impl(path)
    }
}
