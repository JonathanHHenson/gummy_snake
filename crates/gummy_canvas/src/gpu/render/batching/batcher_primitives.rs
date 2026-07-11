use super::{RenderPassBatcher, RenderPassBatcherResult};
use crate::gpu::types::*;
use crate::types::BlendMode;

impl<'resources, 'pass> RenderPassBatcher<'resources, 'pass> {
    pub(in crate::gpu::render) fn push_triangle_vertices(
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

    pub(in crate::gpu::render) fn draw_procedural_instances(
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

    pub(in crate::gpu::render) fn draw_erase_procedural_instances(
        &mut self,
        instances: &[PrimitiveInstance],
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
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(self.procedural_erase_pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
        self.pass.draw(0..6, 0..instances.len() as u32);
    }

    pub(in crate::gpu::render) fn draw_stroke_path(
        &mut self,
        records: &[StrokePathRecord],
        bind_group: &'resources wgpu::BindGroup,
        record_offset: usize,
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        self.flush_primitives();
        if records.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .stroke_path_buffer
            .expect("stroke path storage buffer is prepared");
        let offset_bytes = (record_offset * std::mem::size_of::<StrokePathRecord>()) as u64;
        let size_bytes = std::mem::size_of_val(records) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue
            .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(records));
        let pipeline = self
            .stroke_path_pipelines
            .get(&blend_mode)
            .expect("stroke path GPU pipeline must exist for fixed-function blend mode");
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass.set_bind_group(2, bind_group, &[]);
        self.pass.draw(0..6, 0..1);
    }

    pub(in crate::gpu::render) fn draw_erase_stroke_path(
        &mut self,
        records: &[StrokePathRecord],
        bind_group: &'resources wgpu::BindGroup,
        record_offset: usize,
        clip_id: usize,
    ) {
        self.flush_primitives();
        if records.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .stroke_path_buffer
            .expect("stroke path storage buffer is prepared");
        let offset_bytes = (record_offset * std::mem::size_of::<StrokePathRecord>()) as u64;
        let size_bytes = std::mem::size_of_val(records) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue
            .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(records));
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(self.stroke_path_erase_pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass.set_bind_group(2, bind_group, &[]);
        self.pass.draw(0..6, 0..1);
    }

    pub(in crate::gpu::render) fn draw_fill_path(
        &mut self,
        records: &[StrokePathRecord],
        bind_group: &'resources wgpu::BindGroup,
        record_offset: usize,
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        self.flush_primitives();
        if records.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .stroke_path_buffer
            .expect("path fill storage buffer is prepared");
        let offset_bytes = (record_offset * std::mem::size_of::<StrokePathRecord>()) as u64;
        let size_bytes = std::mem::size_of_val(records) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue
            .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(records));
        let pipeline = self
            .path_fill_pipelines
            .get(&blend_mode)
            .expect("path fill GPU pipeline must exist for fixed-function blend mode");
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass.set_bind_group(2, bind_group, &[]);
        self.pass.draw(0..6, 0..1);
    }

    pub(in crate::gpu::render) fn draw_erase_fill_path(
        &mut self,
        records: &[StrokePathRecord],
        bind_group: &'resources wgpu::BindGroup,
        record_offset: usize,
        clip_id: usize,
    ) {
        self.flush_primitives();
        if records.is_empty() {
            return;
        }
        *self.vertex_uploads += 1;
        *self.primitive_batches += 1;
        let buffer = self
            .stroke_path_buffer
            .expect("path fill storage buffer is prepared");
        let offset_bytes = (record_offset * std::mem::size_of::<StrokePathRecord>()) as u64;
        let size_bytes = std::mem::size_of_val(records) as u64;
        *self.uploaded_vertex_bytes += size_bytes;
        self.queue
            .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(records));
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(self.path_fill_erase_pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, clip_bind_group, &[]);
        self.pass.set_bind_group(2, bind_group, &[]);
        self.pass.draw(0..6, 0..1);
    }

    pub(in crate::gpu::render) fn flush_primitives(&mut self) {
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

    pub(in crate::gpu::render) fn prepare_primitive_batch(
        &mut self,
        blend_mode: BlendMode,
        clip_id: usize,
    ) {
        if !self.pending_primitive_vertices.is_empty()
            && (self.pending_primitive_clip_id != clip_id
                || self.pending_primitive_blend_mode != blend_mode)
        {
            self.flush_primitives();
        }
        self.pending_primitive_clip_id = clip_id;
        self.pending_primitive_blend_mode = blend_mode;
    }

    pub(in crate::gpu::render) fn extend_primitive_vertices<I>(
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

    pub(in crate::gpu::render) fn finish(mut self) -> RenderPassBatcherResult {
        self.flush_primitives();
        self.pending_primitive_vertices.clear();
        RenderPassBatcherResult {
            pending_primitive_vertices: self.pending_primitive_vertices,
            primitive_vertex_offset: self.primitive_vertex_offset,
            procedural_primitive_offset: self.procedural_primitive_offset,
        }
    }
}
