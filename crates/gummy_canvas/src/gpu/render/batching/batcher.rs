use crate::gpu::types::*;
use crate::types::BlendMode;

#[derive(Clone, Copy, Default)]
pub(in crate::gpu::render) struct RenderBufferOffsets {
    pub(in crate::gpu::render) primitive_vertex: usize,
    pub(in crate::gpu::render) procedural_primitive: usize,
    pub(in crate::gpu::render) stroke_path_record: usize,
    pub(in crate::gpu::render) image_vertex: usize,
    pub(in crate::gpu::render) model_uniform: u32,
}

pub(in crate::gpu::render) struct RenderPassBatcher<'resources, 'pass> {
    pub(in crate::gpu::render) pass: &'pass mut wgpu::RenderPass<'resources>,
    pub(in crate::gpu::render) queue: &'resources wgpu::Queue,
    pub(in crate::gpu::render) viewport_bind_group: &'resources wgpu::BindGroup,
    pub(in crate::gpu::render) clip_textures: &'resources [ClipTextureAsset],
    pub(in crate::gpu::render) primitive_vertex_buffer: Option<&'resources wgpu::Buffer>,
    pub(in crate::gpu::render) procedural_primitive_buffer: Option<&'resources wgpu::Buffer>,
    pub(in crate::gpu::render) stroke_path_buffer: Option<&'resources wgpu::Buffer>,
    pub(in crate::gpu::render) image_vertex_buffer: Option<&'resources wgpu::Buffer>,
    pub(in crate::gpu::render) pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) primitive_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(in crate::gpu::render) procedural_primitive_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(in crate::gpu::render) procedural_erase_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) stroke_path_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(in crate::gpu::render) stroke_path_erase_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) path_fill_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(in crate::gpu::render) path_fill_erase_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) image_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) image_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(in crate::gpu::render) model_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) model_wireframe_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) textured_model_pipeline: &'resources wgpu::RenderPipeline,
    pub(in crate::gpu::render) model_uniform_bind_group: &'resources wgpu::BindGroup,
    pub(in crate::gpu::render) vertex_uploads: &'pass mut u64,
    pub(in crate::gpu::render) uploaded_vertex_bytes: &'pass mut u64,
    pub(in crate::gpu::render) primitive_batches: &'pass mut u64,
    pub(in crate::gpu::render) image_batches: &'pass mut u64,
    pub(in crate::gpu::render) pending_primitive_vertices: Vec<Vertex>,
    pub(in crate::gpu::render) pending_primitive_clip_id: usize,
    pub(in crate::gpu::render) pending_primitive_blend_mode: BlendMode,
    pub(in crate::gpu::render) primitive_vertex_offset: usize,
    pub(in crate::gpu::render) procedural_primitive_offset: usize,
}

pub(in crate::gpu::render) struct RenderPassBatcherResult {
    pub(in crate::gpu::render) pending_primitive_vertices: Vec<Vertex>,
    pub(in crate::gpu::render) primitive_vertex_offset: usize,
    pub(in crate::gpu::render) procedural_primitive_offset: usize,
}
