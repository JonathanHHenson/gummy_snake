use crate::runtime::style::*;
use crate::*;

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
            erase_color: Rgba {
                r: 0,
                g: 0,
                b: 0,
                a: 0,
            },
            image_cache: ImageCache::default(),
            text_cache: TextCache::default(),
            text_cache_order: VecDeque::new(),
            texture_cache_versions: TextureCache::default(),
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
            primitive_batch_cache_key: None,
            primitive_batch_cache_record_count: 0,
            primitive_batch_cache_vertices: std::sync::Arc::new(Vec::new()),
            primitive_batch_cache_instances: std::sync::Arc::new(Vec::new()),
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
        if self.resize_unchanged(
            width,
            height,
            pixel_density,
            physical_width,
            physical_height,
        ) {
            return Ok(());
        }
        self.apply_resize_reset(
            width,
            height,
            pixel_density,
            physical_width,
            physical_height,
            true,
        )?;
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
        if self.resize_unchanged(
            width,
            height,
            pixel_density,
            physical_width,
            physical_height,
        ) {
            return Ok(());
        }
        self.apply_resize_reset(
            width,
            height,
            pixel_density,
            physical_width,
            physical_height,
            false,
        )?;
        Ok(())
    }

    fn resize_unchanged(
        &self,
        width: i64,
        height: i64,
        pixel_density: f64,
        physical_width: usize,
        physical_height: usize,
    ) -> bool {
        width == self.width
            && height == self.height
            && physical_width == self.physical_width
            && physical_height == self.physical_height
            && (pixel_density - self.pixel_density).abs() <= f64::EPSILON
    }

    fn apply_resize_reset(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        physical_width: usize,
        physical_height: usize,
        reset_image_text_active: bool,
    ) -> PyResult<()> {
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
        self.reset_render_sync_state();
        if reset_image_text_active {
            self.image_text_active_this_frame = false;
        }
        self.cached_style_key = None;
        self.cached_style = None;
        self.clip_masks.clear();
        self.clip_bounds.clear();
        self.text_cache.clear_layout_entries();
        self.text_cache_order.clear();
        Ok(())
    }
}
