use crate::gpu::pipeline::to_wgpu_color;
use crate::gpu::render::batcher::{RenderBufferOffsets, RenderPassBatcher};
use crate::gpu::render::buffers::aligned_stroke_path_record_offset;
use crate::gpu::types::*;
use crate::BlendMode;

struct StrokePathBinding {
    record_offset: usize,
    bind_group: wgpu::BindGroup,
}

impl GpuRenderer {
    pub(super) fn encode_plain_commands(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        render_offsets: &mut RenderBufferOffsets,
    ) {
        let clear = self
            .commands
            .iter()
            .rev()
            .find_map(|command| match command {
                DrawCommand::Clear(color) => Some(*color),
                DrawCommand::Triangles { .. } => None,
                DrawCommand::RetainedTriangles { .. } => None,
                DrawCommand::PrimitiveInstances { .. } => None,
                DrawCommand::RetainedPrimitiveInstances { .. } => None,
                DrawCommand::StrokePath { .. } => None,
                DrawCommand::FillPath { .. } => None,
                DrawCommand::BlendEllipse { .. } => None,
                DrawCommand::PixelPrefix { .. } => None,
                DrawCommand::Model { .. } => None,
                DrawCommand::ModelInstances { .. } => None,
                DrawCommand::TexturedModel { .. } => None,
                DrawCommand::Text { .. } => None,
                DrawCommand::ErasePrimitiveInstances { .. } => None,
                DrawCommand::EraseStrokePath { .. } => None,
                DrawCommand::EraseFillPath { .. } => None,
                DrawCommand::Image { .. } | DrawCommand::ImageBatch { .. } => None,
            });
        let last_clear_index = self
            .commands
            .iter()
            .rposition(|command| matches!(command, DrawCommand::Clear(_)));
        let (image_offsets, mut image_staging) =
            self.stage_image_vertices(last_clear_index, render_offsets);
        let model_uniform_indices = self.stage_model_uniforms(last_clear_index, render_offsets);
        let (stroke_path_bindings, next_stroke_path_record) =
            self.prepare_stroke_path_bindings(render_offsets.stroke_path_record);
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas primitive render pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &self.texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: clear
                        .map(to_wgpu_color)
                        .map(wgpu::LoadOp::Clear)
                        .unwrap_or(wgpu::LoadOp::Load),
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                view: &self.depth_texture_view,
                depth_ops: Some(wgpu::Operations {
                    load: wgpu::LoadOp::Clear(1.0),
                    store: wgpu::StoreOp::Discard,
                }),
                stencil_ops: None,
            }),
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(&self.pipeline);
        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
        pass.set_bind_group(1, &self.clip_textures[0].bind_group, &[]);

        let mut pending_primitive_vertices = std::mem::take(&mut self.primitive_staging);
        pending_primitive_vertices.clear();
        let mut batcher = RenderPassBatcher {
            pass: &mut pass,
            queue: self.queue.as_ref(),
            viewport_bind_group: &self.viewport_bind_group,
            clip_textures: &self.clip_textures,
            primitive_vertex_buffer: self.primitive_vertex_buffer.as_ref(),
            procedural_primitive_buffer: self.procedural_primitive_buffer.as_ref(),
            stroke_path_buffer: self.stroke_path_buffer.as_ref(),
            image_vertex_buffer: self.image_vertex_buffer.as_ref(),
            pipeline: &self.pipeline,
            primitive_pipelines: &self.primitive_pipelines,
            procedural_primitive_pipelines: &self.procedural_primitive_pipelines,
            procedural_erase_pipeline: &self.procedural_erase_pipeline,
            stroke_path_pipelines: &self.stroke_path_pipelines,
            stroke_path_erase_pipeline: &self.stroke_path_erase_pipeline,
            path_fill_pipelines: &self.path_fill_pipelines,
            path_fill_erase_pipeline: &self.path_fill_erase_pipeline,
            image_pipeline: &self.image_pipeline,
            image_pipelines: &self.image_pipelines,
            model_pipeline: &self.model_pipeline,
            textured_model_pipeline: &self.textured_model_pipeline,
            model_uniform_bind_group: &self.model_uniform_bind_group,
            vertex_uploads: &mut self.vertex_uploads,
            uploaded_vertex_bytes: &mut self.uploaded_vertex_bytes,
            primitive_batches: &mut self.primitive_batches,
            image_batches: &mut self.image_batches,
            pending_primitive_vertices,
            pending_primitive_clip_id: 0,
            pending_primitive_blend_mode: BlendMode::Blend,
            primitive_vertex_offset: render_offsets.primitive_vertex,
            procedural_primitive_offset: render_offsets.procedural_primitive,
        };

        let mut skip_until_last_clear = clear.is_some();
        let mut skip_image_commands_until = 0usize;
        for (command_index, command) in self.commands.iter().enumerate() {
            match command {
                DrawCommand::Clear(color) => {
                    if skip_until_last_clear && Some(*color) == clear {
                        skip_until_last_clear = false;
                    }
                }
                DrawCommand::Triangles {
                    vertices,
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.push_triangle_vertices(vertices.as_slice(), *blend_mode, *clip_id);
                }
                DrawCommand::RetainedTriangles {
                    retained: RetainedTriangleVertices { vertices, .. },
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.push_triangle_vertices(vertices.as_slice(), *blend_mode, *clip_id);
                }
                DrawCommand::PrimitiveInstances {
                    instances,
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.draw_procedural_instances(instances, *blend_mode, *clip_id);
                }
                DrawCommand::RetainedPrimitiveInstances {
                    retained: RetainedPrimitiveInstances { instances, .. },
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.draw_procedural_instances(instances, *blend_mode, *clip_id);
                }
                DrawCommand::StrokePath {
                    records,
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    let binding = stroke_path_bindings[command_index]
                        .as_ref()
                        .expect("stroke path bind group is prepared");
                    batcher.draw_stroke_path(
                        records,
                        &binding.bind_group,
                        binding.record_offset,
                        *blend_mode,
                        *clip_id,
                    );
                }
                DrawCommand::FillPath {
                    records,
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    let binding = stroke_path_bindings[command_index]
                        .as_ref()
                        .expect("path fill bind group is prepared");
                    batcher.draw_fill_path(
                        records,
                        &binding.bind_group,
                        binding.record_offset,
                        *blend_mode,
                        *clip_id,
                    );
                }
                DrawCommand::BlendEllipse { .. } => {}
                DrawCommand::PixelPrefix { .. } => {}
                DrawCommand::Text { .. } => {}
                DrawCommand::Model {
                    key,
                    index_count,
                    uniform: _,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.draw_model(
                        self.model_meshes.get(key),
                        *index_count,
                        model_uniform_indices[command_index],
                    );
                }
                DrawCommand::ModelInstances {
                    key,
                    index_count,
                    uniforms,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    let instance_count = u32::try_from(uniforms.len()).unwrap_or(u32::MAX);
                    batcher.draw_model_instances(
                        self.model_meshes.get(key),
                        *index_count,
                        model_uniform_indices[command_index],
                        instance_count,
                    );
                }
                DrawCommand::TexturedModel {
                    model_key,
                    texture_key,
                    index_count,
                    uniform: _,
                    linear,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.draw_textured_model(
                        self.model_meshes.get(model_key),
                        self.textures.get(texture_key),
                        *index_count,
                        model_uniform_indices[command_index],
                        *linear,
                    );
                }

                DrawCommand::ErasePrimitiveInstances { instances, clip_id } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batcher.draw_erase_procedural_instances(instances, *clip_id);
                }
                DrawCommand::EraseStrokePath { records, clip_id } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    let binding = stroke_path_bindings[command_index]
                        .as_ref()
                        .expect("stroke path bind group is prepared");
                    batcher.draw_erase_stroke_path(
                        records,
                        &binding.bind_group,
                        binding.record_offset,
                        *clip_id,
                    );
                }
                DrawCommand::EraseFillPath { records, clip_id } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    let binding = stroke_path_bindings[command_index]
                        .as_ref()
                        .expect("path fill bind group is prepared");
                    batcher.draw_erase_fill_path(
                        records,
                        &binding.bind_group,
                        binding.record_offset,
                        *clip_id,
                    );
                }
                DrawCommand::Image {
                    key,
                    linear,
                    blend_mode,
                    clip_id,
                    ..
                }
                | DrawCommand::ImageBatch {
                    key,
                    linear,
                    blend_mode,
                    clip_id,
                    ..
                } => {
                    if command_index < skip_image_commands_until {
                        continue;
                    }
                    if skip_until_last_clear {
                        continue;
                    }
                    skip_image_commands_until = batcher.draw_image_commands(
                        command_index,
                        &self.commands,
                        &image_offsets,
                        self.textures.get(key),
                        *key,
                        *linear,
                        *blend_mode,
                        *clip_id,
                    );
                }
            }
        }
        let batcher_result = batcher.finish();
        drop(pass);
        render_offsets.primitive_vertex = batcher_result.primitive_vertex_offset;
        render_offsets.procedural_primitive = batcher_result.procedural_primitive_offset;
        render_offsets.stroke_path_record = next_stroke_path_record;
        self.primitive_staging = batcher_result.pending_primitive_vertices;
        image_staging.clear();
        self.image_staging = image_staging;
    }

    fn prepare_stroke_path_bindings(
        &self,
        start_record_offset: usize,
    ) -> (Vec<Option<StrokePathBinding>>, usize) {
        let has_stroke_paths = self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::StrokePath { .. }
                    | DrawCommand::FillPath { .. }
                    | DrawCommand::EraseStrokePath { .. }
                    | DrawCommand::EraseFillPath { .. }
            )
        });
        if !has_stroke_paths {
            return (Vec::new(), start_record_offset);
        }
        let buffer = self
            .stroke_path_buffer
            .as_ref()
            .expect("stroke path storage buffer is prepared");
        let mut bindings = Vec::with_capacity(self.commands.len());
        let mut record_offset = start_record_offset;
        for command in &self.commands {
            let records = match command {
                DrawCommand::StrokePath { records, .. }
                | DrawCommand::FillPath { records, .. }
                | DrawCommand::EraseStrokePath { records, .. }
                | DrawCommand::EraseFillPath { records, .. } => records,
                _ => {
                    bindings.push(None);
                    continue;
                }
            };
            record_offset = aligned_stroke_path_record_offset(record_offset);
            let offset_bytes = (record_offset * std::mem::size_of::<StrokePathRecord>()) as u64;
            let size_bytes = (records.len() * std::mem::size_of::<StrokePathRecord>()) as u64;
            let size = wgpu::BufferSize::new(size_bytes)
                .expect("stroke path storage binding must not be empty");
            let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("gummy_canvas stroke path bind group"),
                layout: &self.stroke_path_bind_group_layout,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::Buffer(wgpu::BufferBinding {
                        buffer,
                        offset: offset_bytes,
                        size: Some(size),
                    }),
                }],
            });
            bindings.push(Some(StrokePathBinding {
                record_offset,
                bind_group,
            }));
            record_offset += records.len();
        }
        (bindings, record_offset)
    }
}
