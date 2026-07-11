use crate::canvas::cache::{ImageCache, TextCache, TextureCache};
use crate::gpu;
use crate::performance::PerformanceCounters;
use crate::raster::Matrix;
use crate::runtime::InteractiveRuntime;
use crate::types::{Rgba, Style};
use pyo3::prelude::*;
use std::collections::VecDeque;
use std::sync::Arc;

#[pyclass(unsendable)]
pub(crate) struct Canvas {
    pub(crate) width: i64,
    pub(crate) height: i64,
    pub(crate) physical_width: usize,
    pub(crate) physical_height: usize,
    pub(crate) pixel_density: f64,
    pub(crate) mode: String,
    pub(crate) window_open: bool,
    pub(crate) closed: bool,
    pub(crate) pixels: Vec<u8>,
    pub(crate) present_pixels: Vec<u32>,
    pub(crate) erase_color: Rgba,
    pub(crate) image_cache: ImageCache,
    pub(crate) text_cache: TextCache,
    pub(crate) text_cache_order: VecDeque<String>,
    pub(crate) texture_cache_versions: TextureCache,
    pub(crate) clip_masks: Vec<Vec<bool>>,
    pub(crate) clip_bounds: Vec<(usize, usize, usize, usize)>,
    pub(crate) runtime: Option<InteractiveRuntime>,
    pub(crate) pointer_lock_mode: String,
    pub(crate) gpu: Option<gpu::GpuRenderer>,
    pub(crate) gpu_error: Option<String>,
    pub(crate) render_dirty: bool,
    pub(crate) offscreen_dirty: bool,
    pub(crate) pixels_stale: bool,
    pub(crate) texture_stale: bool,
    pub(crate) last_reusable_text_frame_signature: Option<String>,
    pub(crate) pending_reusable_text_frame_signature: Option<String>,
    pub(crate) cpu_compositing_active: bool,
    pub(crate) image_text_active_this_frame: bool,
    pub(crate) cached_style_key: Option<(usize, i64)>,
    pub(crate) cached_style: Option<Style>,
    pub(crate) current_style: Style,
    pub(crate) style_stack: Vec<Style>,
    pub(crate) current_matrix: Matrix,
    pub(crate) matrix_stack: Vec<Matrix>,
    pub(crate) performance_counters: PerformanceCounters,
    pub(crate) pending_3d_triangles: Vec<Pending3dTriangle>,
    pub(crate) primitive_batch_cache_key: Option<u64>,
    pub(crate) primitive_batch_cache_record_count: usize,
    pub(crate) primitive_batch_cache_vertices: Arc<Vec<([f32; 2], gpu::GpuColor)>>,
    pub(crate) primitive_batch_cache_instances: Arc<Vec<gpu::PrimitiveInstance>>,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct Pending3dTriangle {
    pub(crate) depth: f64,
    pub(crate) vertices: [([f32; 2], gpu::GpuColor); 3],
}
