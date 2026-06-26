use crate::gpu::types::*;
use crate::BlendMode;

#[derive(Clone, Copy, Default)]
pub(super) struct RenderBufferOffsets {
    pub(super) primitive_vertex: usize,
    pub(super) procedural_primitive: usize,
    pub(super) erase_vertex: usize,
    pub(super) image_vertex: usize,
    pub(super) model_uniform: u32,
}

pub(super) struct RenderPassBatcher<'resources, 'pass> {
    pub(super) pass: &'pass mut wgpu::RenderPass<'resources>,
    pub(super) queue: &'resources wgpu::Queue,
    pub(super) viewport_bind_group: &'resources wgpu::BindGroup,
    pub(super) clip_textures: &'resources [ClipTextureAsset],
    pub(super) primitive_vertex_buffer: Option<&'resources wgpu::Buffer>,
    pub(super) procedural_primitive_buffer: Option<&'resources wgpu::Buffer>,
    pub(super) erase_vertex_buffer: Option<&'resources wgpu::Buffer>,
    pub(super) image_vertex_buffer: Option<&'resources wgpu::Buffer>,
    pub(super) pipeline: &'resources wgpu::RenderPipeline,
    pub(super) primitive_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) procedural_primitive_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) erase_pipeline: &'resources wgpu::RenderPipeline,
    pub(super) image_pipeline: &'resources wgpu::RenderPipeline,
    pub(super) image_pipelines:
        &'resources std::collections::HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) model_pipeline: &'resources wgpu::RenderPipeline,
    pub(super) textured_model_pipeline: &'resources wgpu::RenderPipeline,
    pub(super) model_uniform_bind_group: &'resources wgpu::BindGroup,
    pub(super) vertex_uploads: &'pass mut u64,
    pub(super) uploaded_vertex_bytes: &'pass mut u64,
    pub(super) primitive_batches: &'pass mut u64,
    pub(super) image_batches: &'pass mut u64,
    pub(super) pending_primitive_vertices: Vec<Vertex>,
    pub(super) pending_primitive_clip_id: usize,
    pub(super) pending_primitive_blend_mode: BlendMode,
    pub(super) primitive_vertex_offset: usize,
    pub(super) procedural_primitive_offset: usize,
    pub(super) erase_vertex_offset: usize,
    pub(super) erase_staging: &'pass mut Vec<Vertex>,
}

pub(super) struct RenderPassBatcherResult {
    pub(super) pending_primitive_vertices: Vec<Vertex>,
    pub(super) primitive_vertex_offset: usize,
    pub(super) procedural_primitive_offset: usize,
    pub(super) erase_vertex_offset: usize,
}

pub(super) fn push_ellipse_vertices(
    vertices: &mut Vec<Vertex>,
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    color: GpuColor,
) {
    let steps = 64usize;
    let color = color.as_float();
    for index in 0..steps {
        let a = 2.0 * std::f64::consts::PI * index as f64 / steps as f64;
        let b = 2.0 * std::f64::consts::PI * (index + 1) as f64 / steps as f64;
        vertices.push(Vertex {
            position: [cx as f32, cy as f32],
            color,
        });
        vertices.push(Vertex {
            position: [(cx + a.cos() * rx) as f32, (cy + a.sin() * ry) as f32],
            color,
        });
        vertices.push(Vertex {
            position: [(cx + b.cos() * rx) as f32, (cy + b.sin() * ry) as f32],
            color,
        });
    }
}
