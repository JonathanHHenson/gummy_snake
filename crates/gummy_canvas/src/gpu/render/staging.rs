use crate::gpu::render::batcher::RenderBufferOffsets;
use crate::gpu::types::*;

impl GpuRenderer {
    pub(super) fn stage_image_vertices(
        &mut self,
        last_clear_index: Option<usize>,
        render_offsets: &mut RenderBufferOffsets,
    ) -> (Vec<Option<(usize, usize)>>, Vec<ImageVertex>) {
        let has_image_commands = self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::Image { .. } | DrawCommand::ImageBatch { .. }
            )
        });
        let mut image_offsets = if has_image_commands {
            vec![None; self.commands.len()]
        } else {
            Vec::new()
        };
        let mut image_staging = std::mem::take(&mut self.image_staging);
        image_staging.clear();
        if has_image_commands {
            for (command_index, command) in self.commands.iter().enumerate() {
                if last_clear_index.is_some_and(|index| command_index <= index) {
                    continue;
                }
                match command {
                    DrawCommand::Image { key, vertices, .. } => {
                        if !self.textures.contains_key(key) {
                            continue;
                        }
                        let offset = render_offsets.image_vertex + image_staging.len();
                        image_staging.extend(vertices.iter().map(|(position, uv, tint)| {
                            ImageVertex {
                                position: *position,
                                uv: *uv,
                                tint: tint.as_float(),
                            }
                        }));
                        image_offsets[command_index] = Some((offset, vertices.len()));
                    }
                    DrawCommand::ImageBatch { key, vertices, .. } => {
                        if !self.textures.contains_key(key) || vertices.is_empty() {
                            continue;
                        }
                        let offset = render_offsets.image_vertex + image_staging.len();
                        image_staging.extend(vertices.iter().copied());
                        image_offsets[command_index] = Some((offset, vertices.len()));
                    }
                    _ => continue,
                }
            }
            if !image_staging.is_empty() {
                self.vertex_uploads += 1;
                self.uploaded_vertex_bytes +=
                    (image_staging.len() * std::mem::size_of::<ImageVertex>()) as u64;
                let buffer = self
                    .image_vertex_buffer
                    .as_ref()
                    .expect("image vertex buffer is prepared");
                let offset_bytes =
                    (render_offsets.image_vertex * std::mem::size_of::<ImageVertex>()) as u64;
                self.queue
                    .write_buffer(buffer, offset_bytes, bytemuck::cast_slice(&image_staging));
                render_offsets.image_vertex += image_staging.len();
            }
        }
        (image_offsets, image_staging)
    }

    pub(super) fn stage_model_uniforms(
        &mut self,
        last_clear_index: Option<usize>,
        render_offsets: &mut RenderBufferOffsets,
    ) -> Vec<Option<u32>> {
        let mut model_uniforms = Vec::new();
        let mut model_uniform_indices = if self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::Model { .. }
                    | DrawCommand::ModelInstances { .. }
                    | DrawCommand::TexturedModel { .. }
            )
        }) {
            vec![None; self.commands.len()]
        } else {
            Vec::new()
        };
        for (command_index, command) in self.commands.iter().enumerate() {
            if last_clear_index.is_some_and(|index| command_index <= index) {
                continue;
            }
            let uniform_index = render_offsets.model_uniform + model_uniforms.len() as u32;
            match command {
                DrawCommand::Model { uniform, .. } | DrawCommand::TexturedModel { uniform, .. } => {
                    model_uniforms.push(*uniform);
                    model_uniform_indices[command_index] = Some(uniform_index);
                }
                DrawCommand::ModelInstances { uniforms, .. } => {
                    if uniforms.is_empty() {
                        continue;
                    }
                    model_uniforms.extend(uniforms.iter().copied());
                    model_uniform_indices[command_index] = Some(uniform_index);
                }
                _ => continue,
            }
        }
        if !model_uniforms.is_empty() {
            self.uploaded_vertex_bytes +=
                (model_uniforms.len() * std::mem::size_of::<ModelUniform>()) as u64;
            let offset_bytes = u64::from(render_offsets.model_uniform)
                * std::mem::size_of::<ModelUniform>() as u64;
            self.queue.write_buffer(
                &self.model_uniform_buffer,
                offset_bytes,
                bytemuck::cast_slice(&model_uniforms),
            );
            render_offsets.model_uniform += model_uniforms.len() as u32;
            self.vertex_uploads += 1;
        }
        model_uniform_indices
    }
}
