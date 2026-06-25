use std::collections::HashMap;
use std::sync::Arc;

use bytemuck::{Pod, Zeroable};

use crate::BlendMode;

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct Vertex {
    pub(super) position: [f32; 2],
    pub(super) color: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub(crate) struct ImageVertex {
    pub(crate) position: [f32; 2],
    pub(crate) uv: [f32; 2],
    pub(crate) tint: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub struct PrimitiveInstance {
    pub p0: [f32; 2],
    pub p1: [f32; 2],
    pub p2: [f32; 2],
    pub bounds: [f32; 4],
    pub color: [f32; 4],
    pub params: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod, Zeroable)]
pub struct ModelVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub struct ModelUniform {
    pub model: [[f32; 4]; 4],
    pub view_projection: [[f32; 4]; 4],
    pub base_color: [f32; 4],
    pub emissive_color: [f32; 4],
    pub specular_shininess: [f32; 4],
    pub ambient_color: [f32; 4],
    pub directional_color: [f32; 4],
    pub directional_direction: [f32; 4],
    pub point_color: [f32; 4],
    pub point_position: [f32; 4],
    pub flags: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ViewportUniform {
    pub(super) size: [f32; 2],
    pub(super) _padding: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ClipUniform {
    pub(super) rect: [f32; 4],
    pub(super) flags: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct PixelPrefixUniform {
    pub(super) byte_limit: u32,
    pub(super) stride: u32,
    pub(super) red_delta: i32,
    pub(super) green_delta: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct BlendEllipseUniform {
    pub(super) center_radius: [f32; 4],
    pub(super) color: [f32; 4],
    pub(super) mode: u32,
    pub(super) _padding: [u32; 7],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GpuColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl GpuColor {
    pub(crate) fn as_float(self) -> [f32; 4] {
        [
            self.r as f32 / 255.0,
            self.g as f32 / 255.0,
            self.b as f32 / 255.0,
            self.a as f32 / 255.0,
        ]
    }
}

#[derive(Clone, Debug)]
pub struct RetainedTriangleVertices {
    pub key: u64,
    pub vertices: Arc<Vec<([f32; 2], GpuColor)>>,
}

impl PartialEq for RetainedTriangleVertices {
    fn eq(&self, other: &Self) -> bool {
        self.key == other.key
    }
}

#[derive(Clone, Debug)]
pub struct RetainedPrimitiveInstances {
    pub key: u64,
    pub instances: Arc<Vec<PrimitiveInstance>>,
}

impl PartialEq for RetainedPrimitiveInstances {
    fn eq(&self, other: &Self) -> bool {
        self.key == other.key
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum DrawCommand {
    Clear(GpuColor),
    Triangles {
        vertices: Vec<([f32; 2], GpuColor)>,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    RetainedTriangles {
        retained: RetainedTriangleVertices,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    PrimitiveInstances {
        instances: Vec<PrimitiveInstance>,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    RetainedPrimitiveInstances {
        retained: RetainedPrimitiveInstances,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    Ellipse {
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    BlendEllipse {
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    },
    PixelPrefix {
        byte_limit: u32,
        stride: u32,
        red_delta: i32,
        green_delta: i32,
    },
    EraseTriangles {
        vertices: Vec<([f32; 2], GpuColor)>,
        clip_id: usize,
    },
    Image {
        key: u64,
        vertices: [([f32; 2], [f32; 2], GpuColor); 6],
        linear: bool,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    ImageBatch {
        key: u64,
        vertices: Vec<ImageVertex>,
        linear: bool,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    Model {
        key: u64,
        index_count: u32,
        uniform: ModelUniform,
    },
    TexturedModel {
        model_key: u64,
        texture_key: u64,
        index_count: u32,
        uniform: ModelUniform,
        linear: bool,
    },
    Text {
        text: String,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        font_size: f32,
        line_height: f32,
        color: GpuColor,
    },
}

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
    pub(super) index_count: u32,
}

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
    pub(super) erase_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) model_pipeline: wgpu::RenderPipeline,
    pub(super) textured_model_pipeline: wgpu::RenderPipeline,
    pub(super) pixel_prefix_pipeline: wgpu::RenderPipeline,
    pub(super) blend_ellipse_pipeline: wgpu::RenderPipeline,
    pub(super) model_bind_group_layout: wgpu::BindGroupLayout,
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
    pub(super) clip_generation: u64,
    pub(super) previous_render_clip_generation: u64,
    pub(super) clear_color: GpuColor,
    pub(super) commands: Vec<DrawCommand>,
    pub(super) previous_render_commands: Vec<DrawCommand>,
    pub(super) textures: HashMap<u64, TextureAsset>,
    pub(super) model_meshes: HashMap<u64, GpuModelMesh>,
    pub(super) primitive_staging: Vec<Vertex>,
    pub(super) erase_staging: Vec<Vertex>,
    pub(super) image_staging: Vec<ImageVertex>,
    pub(super) primitive_vertex_buffer: Option<wgpu::Buffer>,
    pub(super) primitive_vertex_capacity: usize,
    pub(super) procedural_primitive_buffer: Option<wgpu::Buffer>,
    pub(super) procedural_primitive_capacity: usize,
    pub(super) erase_vertex_buffer: Option<wgpu::Buffer>,
    pub(super) erase_vertex_capacity: usize,
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
