use super::*;
use crate::runtime_style::*;

impl Canvas {
    pub(crate) fn new_impl(
        width: i64,
        height: i64,
        pixel_density: f64,
        mode: &str,
        renderer: &str,
    ) -> PyResult<Self> {
        validate_mode_and_renderer(mode, renderer)?;
        let (physical_width, physical_height) = physical_dimensions(width, height, pixel_density)?;
        let (gpu, gpu_error) = match gpu::GpuRenderer::new(physical_width, physical_height) {
            Ok(renderer) => (Some(renderer), None),
            Err(err) => (None, Some(err)),
        };
        Ok(Self {
            width,
            height,
            physical_width,
            physical_height,
            pixel_density,
            mode: mode.to_string(),
            window_open: mode == INTERACTIVE_MODE,
            closed: false,
            pixels: vec![0; physical_width * physical_height * 4],
            present_pixels: vec![0; physical_width * physical_height],
            image_cache: HashMap::new(),
            text_cache: HashMap::new(),
            text_cache_order: VecDeque::new(),
            font_cache: HashMap::new(),
            next_text_key: 1_u64 << 62,
            texture_cache_versions: HashMap::new(),
            runtime: None,
            gpu,
            gpu_error,
            render_dirty: false,
            offscreen_dirty: false,
            pixels_stale: false,
            texture_stale: false,
            cached_style_key: None,
            cached_style: None,
            performance_counters: PerformanceCounters::default(),
        })
    }

    pub(crate) fn resize_impl(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        renderer: &str,
    ) -> PyResult<()> {
        validate_renderer(renderer)?;
        let (physical_width, physical_height) = physical_dimensions(width, height, pixel_density)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.resize(physical_width, physical_height)
                .map_err(PyValueError::new_err)?;
            gpu.clear_transparent();
            gpu.render();
        }
        self.width = width;
        self.height = height;
        self.pixel_density = pixel_density;
        self.physical_width = physical_width;
        self.physical_height = physical_height;
        self.pixels = vec![0; physical_width * physical_height * 4];
        self.present_pixels = vec![0; physical_width * physical_height];
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = false;
        self.cached_style_key = None;
        self.cached_style = None;
        self.text_cache.clear();
        self.text_cache_order.clear();
        if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .request_resize(width, height, pixel_density)
                .map_err(|err| {
                    PyValueError::new_err(format!("Failed to resize native canvas window: {err}"))
                })?;
        }
        Ok(())
    }

    pub(crate) fn dimensions_impl(&self) -> (i64, i64, usize, usize, f64) {
        (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )
    }

    pub(crate) fn display_density_impl(&self) -> f64 {
        if let Some(runtime) = self.runtime.as_ref() {
            runtime.display_density()
        } else if self.window_open {
            self.pixel_density.max(1.0)
        } else {
            1.0
        }
    }

    pub(crate) fn native_window_available_impl(&self) -> bool {
        runtime_native_window_available()
    }

    pub(crate) fn gpu_available_impl(&self) -> bool {
        self.gpu.is_some()
    }

    pub(crate) fn gpu_status_impl(&self) -> String {
        self.gpu_error
            .clone()
            .unwrap_or_else(|| "available".to_string())
    }

    pub(crate) fn performance_counters_impl<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        self.performance_counters.to_dict(py)
    }

    pub(crate) fn reset_performance_counters_impl(&mut self) {
        self.performance_counters = PerformanceCounters::default();
    }

    pub(crate) fn open_window_impl(&mut self) -> PyResult<()> {
        self.mode = INTERACTIVE_MODE.to_string();
        self.window_open = true;
        self.closed = false;
        self.runtime = Some(
            InteractiveRuntime::open(self.width, self.height).map_err(|err| {
                PyValueError::new_err(format!("Failed to open native canvas window: {err}"))
            })?,
        );
        Ok(())
    }

    pub(crate) fn should_close_impl(&self) -> bool {
        self.closed
            || self
                .runtime
                .as_ref()
                .map(|runtime| runtime.should_close())
                .unwrap_or(false)
    }

    pub(crate) fn poll_events_impl(&mut self) -> PyResult<Vec<Py<PyAny>>> {
        self.performance_counters.event_polls += 1;
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(Vec::new());
        };
        let events = runtime.poll_events().map_err(|err| {
            PyValueError::new_err(format!("Failed to poll native canvas events: {err}"))
        })?;
        if runtime.should_close() {
            self.closed = true;
        }
        Python::with_gil(|py| {
            events
                .into_iter()
                .map(|event| runtime_event_to_pyobject(py, event))
                .collect()
        })
    }

    pub(crate) fn begin_frame_impl(&mut self) {
        self.performance_counters.bridge_calls += 1;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = false;
    }

    pub(crate) fn end_frame_impl(&mut self) {
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
    }

    pub(crate) fn present_impl(&mut self) -> PyResult<()> {
        self.performance_counters.bridge_calls += 1;
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
        if self.runtime.is_some() && self.render_dirty {
            self.upload_stale_texture(false)?;
        }
        if let Some(runtime) = self.runtime.as_mut() {
            let window = runtime.window().ok_or_else(|| {
                PyValueError::new_err("Native canvas window is not available for presentation.")
            })?;
            let (surface_width, surface_height) = runtime.physical_size();
            let gpu = self.gpu.as_mut().ok_or_else(|| {
                PyValueError::new_err(
                    self.gpu_error
                        .clone()
                        .unwrap_or_else(|| "GPU presentation is unavailable.".to_string()),
                )
            })?;
            if self.render_dirty {
                if self.offscreen_dirty {
                    gpu.render();
                    gpu.begin_frame();
                    self.offscreen_dirty = false;
                    self.pixels_stale = true;
                    self.texture_stale = false;
                }
                gpu.present_texture_to_window(window, surface_width, surface_height)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to present native GPU frame: {err}"))
                    })?;
                self.performance_counters.frames_presented += 1;
                self.render_dirty = false;
            }
            if runtime.should_close() {
                self.closed = true;
            }
        }
        Ok(())
    }

    pub(crate) fn close_impl(&mut self) {
        self.closed = true;
        if let Some(runtime) = self.runtime.as_mut() {
            runtime.close();
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.drop_surface();
        }
        self.runtime = None;
    }
}
