use crate::gpu::render::batcher::{
    push_ellipse_vertices, RenderPassBatcher, RenderPassBatcherResult,
};
use crate::gpu::types::*;
use crate::BlendMode;

impl<'resources, 'pass> RenderPassBatcher<'resources, 'pass> {
    pub(super) fn push_triangle_vertices(
        &mut self,
        vertices: &[([f32; 2], GpuColor)],
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        self.extend_primitive_vertices(
            vertices.iter().map(|(position, color)| Vertex {
                position: *position,
                color: color.as_float(),
            }),
            blend_mode,
            clip_id,
        );
    }

    pub(super) fn push_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        self.prepare_primitive_batch(blend_mode, clip_id);
        push_ellipse_vertices(
            &mut self.pending_primitive_vertices,
            cx as f64,
            cy as f64,
            rx as f64,
            ry as f64,
            color,
        );
    }

    pub(super) fn draw_procedural_instances(
        &mut self,
        instances: &[PrimitiveInstance],
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        self.flush_primitives();
        if instances.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .procedural_primitive_buffer
            .expect("procedural primitive instance buffer is prepared");
        let offset_bytes =
            (self.procedural_primitive_offset * std::mem::size_of::<PrimitiveInstance>()) as u64;
        let size_bytes = std::mem::size_of_val(instances) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue
            .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(instances));
        self.procedural_primitive_offset += instances.len();
        let pipeline = self
            .procedural_primitive_pipelines
            .get(&blend_mode)
            .unwrap_or(self.pipeline);
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
        self.pass.draw(0..6, 0..instances.len() as u32);
    }

    pub(super) fn draw_erase_triangles(
        &mut self,
        vertices: &[([f32; 2], GpuColor)],
        clip_id: usize,
    ) {
        self.flush_primitives();
        self.erase_staging.clear();
        self.erase_staging
            .extend(vertices.iter().map(|(position, color)| Vertex {
                position: *position,
                color: color.as_float(),
            }));
        if self.erase_staging.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .erase_vertex_buffer
            .expect("erase vertex buffer is prepared");
        let offset_bytes = (self.erase_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
        let size_bytes = (self.erase_staging.len() * std::mem::size_of::<Vertex>()) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue.write_buffer(
            buffer,
            offset_bytes,
            bytemuck::cast_slice(self.erase_staging.as_slice()),
        );
        self.erase_vertex_offset += self.erase_staging.len();
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(self.erase_pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
        self.pass.draw(0..self.erase_staging.len() as u32, 0..1);
    }

    pub(super) fn flush_primitives(&mut self) {
        if self.pending_primitive_vertices.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .primitive_vertex_buffer
            .expect("primitive vertex buffer is prepared");
        let offset_bytes = (self.primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
        let size_bytes =
            (self.pending_primitive_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue.write_buffer(
            buffer,
            offset_bytes,
            bytemuck::cast_slice(&self.pending_primitive_vertices),
        );
        let vertex_count = self.pending_primitive_vertices.len();
        self.primitive_vertex_offset += vertex_count;
        let pipeline = self
            .primitive_pipelines
            .get(&self.pending_primitive_blend_mode)
            .unwrap_or(self.pipeline);
        let clip_bind_group = &self.clip_textures[self.pending_primitive_clip_id].bind_group;
        self.pass.set_pipeline(pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
        self.pass.draw(0..vertex_count as u32, 0..1);
        self.pending_primitive_vertices.clear();
    }

    pub(super) fn prepare_primitive_batch(&mut self, blend_mode: BlendMode, clip_id: usize) {
        if !self.pending_primitive_vertices.is_empty()
            && (self.pending_primitive_clip_id != clip_id
                || self.pending_primitive_blend_mode != blend_mode)
        {
            self.flush_primitives();
        }
        self.pending_primitive_clip_id = clip_id;
        self.pending_primitive_blend_mode = blend_mode;
    }

    pub(super) fn extend_primitive_vertices<I>(
        &mut self,
        vertices: I,
        blend_mode: BlendMode,
        clip_id: usize,
    ) where
        I: IntoIterator<Item = Vertex>,
    {
        self.prepare_primitive_batch(blend_mode, clip_id);
        self.pending_primitive_vertices.extend(vertices);
    }

    pub(super) fn finish(mut self) -> RenderPassBatcherResult {
        self.flush_primitives();
        self.pending_primitive_vertices.clear();
        RenderPassBatcherResult {
            pending_primitive_vertices: self.pending_primitive_vertices,
            primitive_vertex_offset: self.primitive_vertex_offset,
            procedural_primitive_offset: self.procedural_primitive_offset,
            erase_vertex_offset: self.erase_vertex_offset,
        }
    }
}
