use std::time::Duration;

use crate::runtime::style::*;
use crate::*;

const LIVE_RESIZE_PRESENT_COOLDOWN: Duration = Duration::from_millis(80);

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
        let (gpu, gpu_error) = match crate::gpu::GpuRenderer::new(physical_width, physical_height) {
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
            text_metric_cache: HashMap::new(),
            text_glyph_advance_cache: HashMap::new(),
            text_kern_cache: HashMap::new(),
            font_cache: HashMap::new(),
            next_text_key: 1_u64 << 62,
            texture_cache_versions: HashMap::new(),
            clip_masks: Vec::new(),
            clip_bounds: Vec::new(),
            runtime: None,
            pointer_lock_mode: DEFAULT_POINTER_LOCK_MODE.to_string(),
            gpu,
            gpu_error,
            render_dirty: false,
            offscreen_dirty: false,
            pixels_stale: false,
            texture_stale: false,
            last_reusable_text_frame_signature: None,
            pending_reusable_text_frame_signature: None,
            cpu_compositing_active: false,
            image_text_active_this_frame: false,
            cached_style_key: None,
            cached_style: None,
            current_style: Style::default(),
            style_stack: Vec::new(),
            current_matrix: (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            matrix_stack: Vec::new(),
            performance_counters: PerformanceCounters::default(),
            pending_3d_triangles: Vec::new(),
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
        let unchanged = width == self.width
            && height == self.height
            && physical_width == self.physical_width
            && physical_height == self.physical_height
            && (pixel_density - self.pixel_density).abs() <= f64::EPSILON;
        if unchanged {
            return Ok(());
        }
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
        self.last_reusable_text_frame_signature = None;
        self.pending_reusable_text_frame_signature = None;
        self.cpu_compositing_active = false;
        self.image_text_active_this_frame = false;
        self.cached_style_key = None;
        self.cached_style = None;
        self.clip_masks.clear();
        self.clip_bounds.clear();
        self.text_cache.clear();
        self.text_cache_order.clear();
        self.text_metric_cache.clear();
        self.text_glyph_advance_cache.clear();
        self.text_kern_cache.clear();
        if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .request_resize(width, height, pixel_density)
                .map_err(|err| {
                    PyValueError::new_err(format!("Failed to resize native canvas window: {err}"))
                })?;
        }
        Ok(())
    }

    pub(crate) fn resize_canvas_impl(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        renderer: &str,
    ) -> PyResult<()> {
        validate_renderer(renderer)?;
        let (physical_width, physical_height) = physical_dimensions(width, height, pixel_density)?;
        let unchanged = width == self.width
            && height == self.height
            && physical_width == self.physical_width
            && physical_height == self.physical_height
            && (pixel_density - self.pixel_density).abs() <= f64::EPSILON;
        if unchanged {
            return Ok(());
        }
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
        self.last_reusable_text_frame_signature = None;
        self.pending_reusable_text_frame_signature = None;
        self.cpu_compositing_active = false;
        self.cached_style_key = None;
        self.cached_style = None;
        self.clip_masks.clear();
        self.clip_bounds.clear();
        self.text_cache.clear();
        self.text_cache_order.clear();
        self.text_metric_cache.clear();
        self.text_glyph_advance_cache.clear();
        self.text_kern_cache.clear();
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

    pub(crate) fn performance_counters_impl<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let dict = self.performance_counters.to_dict(py)?;
        if let Some(gpu) = self.gpu.as_ref() {
            let (allocations, uploads, primitive_batches, image_batches) =
                gpu.render_loop_counters();
            dict.set_item("gpu_vertex_buffer_allocations", allocations)?;
            dict.set_item("gpu_vertex_uploads", uploads)?;
            dict.set_item("gpu_primitive_batches", primitive_batches)?;
            dict.set_item("gpu_image_batches", image_batches)?;
        }
        Ok(dict)
    }

    pub(crate) fn reset_performance_counters_impl(&mut self) {
        self.performance_counters = PerformanceCounters::default();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.reset_render_loop_counters();
        }
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
        if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .set_pointer_lock_mode(&self.pointer_lock_mode)
                .map_err(PyValueError::new_err)?;
        }
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

    pub(crate) fn pump_native_events_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(self.closed);
        };
        runtime.pump_events().map_err(|err| {
            PyValueError::new_err(format!("Failed to pump native canvas events: {err}"))
        })?;

        let should_close = runtime.should_close();
        let (logical_width, logical_height) = runtime.logical_size();
        let pixel_density = self.pixel_density;

        if should_close {
            self.closed = true;
            return Ok(true);
        }

        if runtime.resize_recently(LIVE_RESIZE_PRESENT_COOLDOWN) {
            return Ok(self.closed);
        }

        if logical_width != self.width
            || logical_height != self.height
            || (pixel_density - self.pixel_density).abs() > f64::EPSILON
        {
            self.resize_canvas_impl(
                logical_width,
                logical_height,
                pixel_density,
                SUPPORTED_RENDERER,
            )?;
        }

        Ok(self.closed)
    }

    pub(crate) fn request_pointer_lock_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Err(PyValueError::new_err(
                "Native canvas window is not available for pointer lock.",
            ));
        };
        runtime.request_pointer_lock().map_err(|err| {
            PyValueError::new_err(format!("Failed to request native pointer lock: {err}"))
        })
    }

    pub(crate) fn exit_pointer_lock_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(false);
        };
        runtime.exit_pointer_lock().map_err(|err| {
            PyValueError::new_err(format!("Failed to exit native pointer lock: {err}"))
        })
    }

    pub(crate) fn pointer_locked_impl(&self) -> bool {
        self.runtime
            .as_ref()
            .map(|runtime| runtime.pointer_locked())
            .unwrap_or(false)
    }

    pub(crate) fn set_pointer_lock_mode_impl(&mut self, mode: &str) -> PyResult<()> {
        let validated = if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .set_pointer_lock_mode(mode)
                .map_err(PyValueError::new_err)?;
            runtime.pointer_lock_mode().to_string()
        } else {
            match mode {
                "unclamped" | "clamped" | "fixed" => mode.to_string(),
                _ => {
                    return Err(PyValueError::new_err(format!(
                        "Pointer lock mode must be 'unclamped', 'clamped', or 'fixed', got {mode:?}."
                    )));
                }
            }
        };
        self.pointer_lock_mode = validated;
        Ok(())
    }

    pub(crate) fn pointer_lock_mode_impl(&self) -> String {
        self.pointer_lock_mode.clone()
    }

    pub(crate) fn start_text_input_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Err(PyValueError::new_err(
                "Native canvas window is not available for text input.",
            ));
        };
        runtime.start_text_input().map_err(|err| {
            PyValueError::new_err(format!("Failed to start native text input: {err}"))
        })
    }

    pub(crate) fn stop_text_input_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(false);
        };
        runtime.stop_text_input().map_err(|err| {
            PyValueError::new_err(format!("Failed to stop native text input: {err}"))
        })
    }

    pub(crate) fn text_input_active_impl(&self) -> bool {
        self.runtime
            .as_ref()
            .map(|runtime| runtime.text_input_active())
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
        self.cpu_compositing_active = false;
        self.image_text_active_this_frame = false;
        self.pending_reusable_text_frame_signature = None;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = false;
        self.pending_3d_triangles.clear();
    }

    pub(crate) fn end_frame_impl(&mut self) {
        self.flush_pending_3d_triangles();
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
    }

    pub(crate) fn present_impl(&mut self) -> PyResult<()> {
        self.performance_counters.bridge_calls += 1;
        self.flush_pending_3d_triangles();
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
        if let Some(runtime) = self.runtime.as_mut() {
            runtime.pump_events().map_err(|err| {
                PyValueError::new_err(format!(
                    "Failed to pump native canvas events before present: {err}"
                ))
            })?;
            if runtime.should_close() {
                self.closed = true;
                return Ok(());
            }
            if runtime.resize_recently(LIVE_RESIZE_PRESENT_COOLDOWN) {
                return Ok(());
            }
        }
        if self.runtime.is_some() {
            let should_present = self.render_dirty;
            if should_present && self.offscreen_dirty {
                self.render_gpu_frame(false);
            }
            if should_present {
                let runtime = self.runtime.as_mut().expect("runtime checked above");
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
                gpu.present_texture_to_window(window, surface_width, surface_height)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to present native GPU frame: {err}"))
                    })?;
                self.performance_counters.frames_presented += 1;
                self.render_dirty = false;
            }
            if self
                .runtime
                .as_ref()
                .is_some_and(InteractiveRuntime::should_close)
            {
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
