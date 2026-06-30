use crate::gpu::render::batcher::RenderPassBatcher;
use crate::gpu::types::*;

impl<'resources, 'pass> RenderPassBatcher<'resources, 'pass> {
    pub(super) fn draw_model(
        &mut self,
        mesh: Option<&'resources GpuModelMesh>,
        index_count: u32,
        uniform_index: Option<u32>,
    ) {
        self.flush_primitives();
        let Some(mesh) = mesh else {
            return;
        };
        let Some(uniform_index) = uniform_index else {
            return;
        };
        let count = index_count.min(mesh.index_count);
        if count == 0 {
            return;
        }
        *self.primitive_batches += 1;
        self.pass.set_pipeline(self.model_pipeline);
        self.pass
            .set_bind_group(0, self.model_uniform_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, mesh._vertex_buffer.slice(..));
        self.pass
            .set_index_buffer(mesh._index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        self.pass
            .draw_indexed(0..count, 0, uniform_index..uniform_index + 1);
    }

    pub(super) fn draw_model_instances(
        &mut self,
        mesh: Option<&'resources GpuModelMesh>,
        index_count: u32,
        uniform_index: Option<u32>,
        instance_count: u32,
    ) {
        self.flush_primitives();
        let Some(mesh) = mesh else {
            return;
        };
        let Some(uniform_index) = uniform_index else {
            return;
        };
        let count = index_count.min(mesh.index_count);
        if count == 0 || instance_count == 0 {
            return;
        }
        *self.primitive_batches += 1;
        self.pass.set_pipeline(self.model_pipeline);
        self.pass
            .set_bind_group(0, self.model_uniform_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, mesh._vertex_buffer.slice(..));
        self.pass
            .set_index_buffer(mesh._index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        self.pass.draw_indexed(
            0..count,
            0,
            uniform_index..uniform_index.saturating_add(instance_count),
        );
    }

    pub(super) fn draw_textured_model(
        &mut self,
        mesh: Option<&'resources GpuModelMesh>,
        texture: Option<&'resources TextureAsset>,
        index_count: u32,
        uniform_index: Option<u32>,
        linear: bool,
    ) {
        self.flush_primitives();
        let Some(mesh) = mesh else {
            return;
        };
        let Some(texture) = texture else {
            return;
        };
        let Some(uniform_index) = uniform_index else {
            return;
        };
        let count = index_count.min(mesh.index_count);
        if count == 0 {
            return;
        }
        *self.primitive_batches += 1;
        self.pass.set_pipeline(self.textured_model_pipeline);
        self.pass
            .set_bind_group(0, self.model_uniform_bind_group, &[]);
        let bind_group = if linear {
            &texture.linear_bind_group
        } else {
            &texture.nearest_bind_group
        };
        self.pass.set_bind_group(1, bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, mesh._vertex_buffer.slice(..));
        self.pass
            .set_index_buffer(mesh._index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        self.pass
            .draw_indexed(0..count, 0, uniform_index..uniform_index + 1);
    }
}
