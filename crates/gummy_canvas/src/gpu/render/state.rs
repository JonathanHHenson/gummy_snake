use std::time::Instant;

use crate::gpu::renderer_state::GpuRenderLoopCounters;
use crate::gpu::types::*;

impl GpuRenderer {
    pub fn render(&mut self) {
        if self.can_reuse_previous_render() {
            self.retained_batch_cache_hits += 1;
            self.retained_batch_reused_bytes += self.retained_render_bytes();
            return;
        }
        if !self.commands.is_empty() {
            self.retained_batch_cache_misses += 1;
        }
        self.write_viewport(self.texture_size.width, self.texture_size.height);
        let mut commands = std::mem::take(&mut self.commands);
        self.ensure_render_vertex_buffers(&commands);
        let mut encoder =
            self.device_context
                .device()
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("gummy_canvas render encoder"),
                });
        let encode_start = Instant::now();
        self.encode_commands(&mut encoder, &commands);
        self.device_context.queue().submit([encoder.finish()]);
        self.encode_time_ms += encode_start.elapsed().as_secs_f64() * 1000.0;
        // Retain the encoded stream for replay comparison while recycling the
        // previous stream's allocation for the next frame.
        std::mem::swap(&mut commands, &mut self.previous_render_commands);
        commands.clear();
        self.commands = commands;
        self.previous_render_clip_generation = self.clip_generation;
    }

    fn can_reuse_previous_render(&self) -> bool {
        if self.commands.is_empty()
            || self.commands != self.previous_render_commands
            || self.clip_generation != self.previous_render_clip_generation
        {
            return false;
        }
        matches!(self.commands.first(), Some(DrawCommand::Clear(_)))
    }

    fn retained_render_bytes(&self) -> u64 {
        ((self.primitive_vertex_capacity * std::mem::size_of::<Vertex>())
            + (self.procedural_primitive_capacity * std::mem::size_of::<PrimitiveInstance>())
            + (self.stroke_path_record_capacity * std::mem::size_of::<StrokePathRecord>())
            + (self.image_vertex_capacity * std::mem::size_of::<ImageVertex>())) as u64
    }

    pub fn invalidate_retained_render_cache(&mut self) {
        if !self.previous_render_commands.is_empty() {
            self.previous_render_commands.clear();
            self.retained_batch_cache_evictions += 1;
        }
    }

    pub fn only_pending_clear(&self) -> Option<GpuColor> {
        let mut clear = None;
        for command in &self.commands {
            match command {
                DrawCommand::Clear(color) => clear = Some(*color),
                DrawCommand::Triangles { vertices, .. } => {
                    if !vertices.is_empty() {
                        return None;
                    }
                }
                DrawCommand::RetainedTriangles {
                    retained: RetainedTriangleVertices { vertices, .. },
                    ..
                } => {
                    if !vertices.is_empty() {
                        return None;
                    }
                }
                DrawCommand::PrimitiveInstances { instances, .. }
                | DrawCommand::ErasePrimitiveInstances { instances, .. } => {
                    if !instances.is_empty() {
                        return None;
                    }
                }
                DrawCommand::StrokePath { records, .. }
                | DrawCommand::FillPath { records, .. }
                | DrawCommand::EraseStrokePath { records, .. }
                | DrawCommand::EraseFillPath { records, .. } => {
                    if !records.is_empty() {
                        return None;
                    }
                }
                DrawCommand::RetainedPrimitiveInstances {
                    retained: RetainedPrimitiveInstances { instances, .. },
                    ..
                } => {
                    if !instances.is_empty() {
                        return None;
                    }
                }
                DrawCommand::BlendEllipse { .. }
                | DrawCommand::PixelPrefix { .. }
                | DrawCommand::PixelFilter { .. }
                | DrawCommand::Model { .. }
                | DrawCommand::ModelWireframe { .. }
                | DrawCommand::ModelInstances { .. }
                | DrawCommand::TexturedModel { .. }
                | DrawCommand::Text { .. } => return None,
                DrawCommand::Image { .. } | DrawCommand::ImageBatch { .. } => return None,
            }
        }
        clear
    }

    pub fn can_append_glyphon_text_command(&self) -> bool {
        let Some(last_text_index) = self
            .commands
            .iter()
            .rposition(|command| matches!(command, DrawCommand::Text { .. }))
        else {
            return true;
        };
        self.commands[last_text_index + 1..]
            .iter()
            .all(|command| matches!(command, DrawCommand::Text { .. }))
    }

    pub(crate) fn render_loop_counters(&self) -> GpuRenderLoopCounters {
        GpuRenderLoopCounters {
            vertex_buffer_allocations: self.vertex_buffer_allocations,
            vertex_uploads: self.vertex_uploads,
            uploaded_vertex_bytes: self.uploaded_vertex_bytes,
            primitive_batches: self.primitive_batches,
            image_batches: self.image_batches,
            encode_time_ms: self.encode_time_ms,
            retained_batch_cache_hits: self.retained_batch_cache_hits,
            retained_batch_cache_misses: self.retained_batch_cache_misses,
            retained_batch_reused_bytes: self.retained_batch_reused_bytes,
            retained_batch_cache_evictions: self.retained_batch_cache_evictions,
            command_clone_count: self.command_clone_count,
            command_clone_bytes: self.command_clone_bytes,
            command_segment_allocation_count: self.command_segment_allocation_count,
        }
    }

    pub fn reset_render_loop_counters(&mut self) {
        self.vertex_buffer_allocations = 0;
        self.vertex_uploads = 0;
        self.uploaded_vertex_bytes = 0;
        self.primitive_batches = 0;
        self.image_batches = 0;
        self.encode_time_ms = 0.0;
        self.retained_batch_cache_hits = 0;
        self.retained_batch_cache_misses = 0;
        self.retained_batch_reused_bytes = 0;
        self.retained_batch_cache_evictions = 0;
        self.command_clone_count = 0;
        self.command_clone_bytes = 0;
        self.command_segment_allocation_count = 0;
    }
}
