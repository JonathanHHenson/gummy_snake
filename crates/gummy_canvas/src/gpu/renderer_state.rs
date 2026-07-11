//! GPU renderer-owned resources and mutable command-encoding state.
//!
//! POD records, uniforms, commands, and vertex layouts stay in `gpu::types`.
//! This module owns the resource graph whose field order and ownership must remain
//! stable for renderer setup, encoding, retained caches, and presentation.

use std::collections::HashMap;
use std::sync::Arc;

use crate::gpu::types::{DrawCommand, GpuColor, ImageVertex, Vertex};
use crate::types::BlendMode;

pub(super) struct TextureAsset {
    pub(super) _texture: wgpu::Texture,
    pub(super) _view: wgpu::TextureView,
    pub(super) nearest_bind_group: wgpu::BindGroup,
    pub(super) linear_bind_group: wgpu::BindGroup,
}

pub(super) struct ClipTextureAsset {
    pub(super) _texture: wgpu::Texture,
    pub(super) _view: wgpu::TextureView,
    pub(super) _uniform_buffer: wgpu::Buffer,
    pub(super) bind_group: wgpu::BindGroup,
}

pub(super) struct GpuModelMesh {
    pub(super) _vertex_buffer: wgpu::Buffer,
    pub(super) _index_buffer: wgpu::Buffer,
    pub(super) _wire_index_buffer: wgpu::Buffer,
    pub(super) index_count: u32,
    pub(super) wire_index_count: u32,
}

/// Owns the GPU device resources, retained assets, and ordered draw command stream.
///
/// The `gpu` module re-exports this type to preserve the stable internal renderer
/// path. Field order is intentionally unchanged from the original declaration.
pub struct GpuRenderer {
    pub(super) instance: wgpu::Instance,
    pub(super) adapter: wgpu::Adapter,
    pub(super) device: Arc<wgpu::Device>,
    pub(super) queue: Arc<wgpu::Queue>,
    pub(super) texture: wgpu::Texture,
    pub(super) texture_view: wgpu::TextureView,
    pub(super) depth_texture: wgpu::Texture,
    pub(super) depth_texture_view: wgpu::TextureView,
    pub(super) texture_size: wgpu::Extent3d,
    pub(super) pipeline: wgpu::RenderPipeline,
    pub(super) primitive_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) procedural_primitive_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) procedural_erase_pipeline: wgpu::RenderPipeline,
    pub(super) stroke_path_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) stroke_path_erase_pipeline: wgpu::RenderPipeline,
    pub(super) path_fill_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) path_fill_erase_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) model_pipeline: wgpu::RenderPipeline,
    pub(super) model_wireframe_pipeline: wgpu::RenderPipeline,
    pub(super) textured_model_pipeline: wgpu::RenderPipeline,
    pub(super) pixel_prefix_pipeline: wgpu::RenderPipeline,
    pub(super) pixel_filter_pipeline: wgpu::RenderPipeline,
    pub(super) blend_ellipse_pipeline: wgpu::RenderPipeline,
    pub(super) model_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) stroke_path_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) model_uniform_buffer: wgpu::Buffer,
    pub(super) model_uniform_bind_group: wgpu::BindGroup,
    pub(super) model_uniform_capacity: usize,
    pub(super) pixel_prefix_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) pixel_prefix_uniform_buffer: wgpu::Buffer,
    pub(super) pixel_prefix_texture: wgpu::Texture,
    pub(super) pixel_prefix_texture_view: wgpu::TextureView,
    pub(super) pixel_prefix_bind_group: wgpu::BindGroup,
    pub(super) image_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) clip_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) texture_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) texture_surface_pipeline: Option<(wgpu::TextureFormat, wgpu::RenderPipeline)>,
    pub(super) texture_sampler: wgpu::Sampler,
    pub(super) linear_texture_sampler: wgpu::Sampler,
    pub(super) text_font_system: glyphon::FontSystem,
    pub(super) text_swash_cache: glyphon::SwashCache,
    pub(super) text_viewport: glyphon::Viewport,
    pub(super) text_atlas: glyphon::TextAtlas,
    pub(super) text_renderer: glyphon::TextRenderer,
    pub(super) text_buffers: HashMap<String, glyphon::Buffer>,
    pub(super) viewport_buffer: wgpu::Buffer,
    pub(super) viewport_bind_group: wgpu::BindGroup,
    pub(super) clip_textures: Vec<ClipTextureAsset>,
    pub(super) current_clip_id: usize,
    pub(super) clip_stack: Vec<usize>,
    pub(super) clip_generation: u64,
    pub(super) previous_render_clip_generation: u64,
    pub(super) clear_color: GpuColor,
    pub(super) commands: Vec<DrawCommand>,
    pub(super) previous_render_commands: Vec<DrawCommand>,
    pub(super) textures: HashMap<u64, TextureAsset>,
    pub(super) model_meshes: HashMap<u64, GpuModelMesh>,
    pub(super) primitive_staging: Vec<Vertex>,
    pub(super) image_staging: Vec<ImageVertex>,
    pub(super) primitive_vertex_buffer: Option<wgpu::Buffer>,
    pub(super) primitive_vertex_capacity: usize,
    pub(super) procedural_primitive_buffer: Option<wgpu::Buffer>,
    pub(super) procedural_primitive_capacity: usize,
    pub(super) stroke_path_buffer: Option<wgpu::Buffer>,
    pub(super) stroke_path_record_capacity: usize,
    pub(super) image_vertex_buffer: Option<wgpu::Buffer>,
    pub(super) image_vertex_capacity: usize,
    pub(super) vertex_buffer_allocations: u64,
    pub(super) vertex_uploads: u64,
    pub(super) uploaded_vertex_bytes: u64,
    pub(super) primitive_batches: u64,
    pub(super) image_batches: u64,
    pub(super) encode_time_ms: f64,
    pub(super) retained_batch_cache_hits: u64,
    pub(super) retained_batch_cache_misses: u64,
    pub(super) retained_batch_reused_bytes: u64,
    pub(super) retained_batch_cache_evictions: u64,
    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub(super) surface: Option<GpuSurface>,
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub(super) struct GpuSurface {
    pub(super) window_id: u32,
    pub(super) surface: wgpu::Surface<'static>,
    pub(super) config: wgpu::SurfaceConfiguration,
}
