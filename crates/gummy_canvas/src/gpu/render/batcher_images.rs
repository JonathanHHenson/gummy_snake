use crate::gpu::render::batcher::RenderPassBatcher;
use crate::gpu::types::*;
use crate::BlendMode;

fn image_command_signature(command: &DrawCommand) -> Option<(u64, bool, BlendMode, usize)> {
    match command {
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
        } => Some((*key, *linear, *blend_mode, *clip_id)),
        _ => None,
    }
}

impl<'resources, 'pass> RenderPassBatcher<'resources, 'pass> {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn draw_image_commands(
        &mut self,
        command_index: usize,
        commands: &[DrawCommand],
        image_offsets: &[Option<(usize, usize)>],
        texture: Option<&'resources TextureAsset>,
        key: u64,
        linear: bool,
        blend_mode: BlendMode,
        clip_id: usize,
    ) -> usize {
        self.flush_primitives();
        let Some(texture) = texture else {
            return command_index + 1;
        };
        let Some((image_vertex_offset, image_vertex_len)) = image_offsets[command_index] else {
            return command_index + 1;
        };
        let mut batched_image_vertex_len = image_vertex_len;
        let mut next_command_index = command_index + 1;
        while next_command_index < commands.len() {
            let Some((next_key, next_linear, next_blend_mode, next_clip_id)) =
                image_command_signature(&commands[next_command_index])
            else {
                break;
            };
            if next_key != key
                || next_linear != linear
                || next_blend_mode != blend_mode
                || next_clip_id != clip_id
            {
                break;
            }
            let Some((next_offset, next_len)) = image_offsets[next_command_index] else {
                break;
            };
            if next_offset != image_vertex_offset + batched_image_vertex_len {
                break;
            }
            batched_image_vertex_len += next_len;
            next_command_index += 1;
        }
        *self.image_batches += 1;
        let buffer = self
            .image_vertex_buffer
            .expect("image vertex buffer is prepared");
        let offset_bytes = (image_vertex_offset * std::mem::size_of::<ImageVertex>()) as u64;
        let size_bytes = (batched_image_vertex_len * std::mem::size_of::<ImageVertex>()) as u64;
        let pipeline = self
            .image_pipelines
            .get(&blend_mode)
            .unwrap_or(self.image_pipeline);
        let bind_group = if linear {
            &texture.linear_bind_group
        } else {
            &texture.nearest_bind_group
        };
        let clip_bind_group = &self.clip_textures[clip_id].bind_group;
        self.pass.set_pipeline(pipeline);
        self.pass.set_bind_group(0, self.viewport_bind_group, &[]);
        self.pass.set_bind_group(1, bind_group, &[]);
        self.pass.set_bind_group(2, clip_bind_group, &[]);
        self.pass
            .set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
        self.pass.draw(0..batched_image_vertex_len as u32, 0..1);
        next_command_index
    }
}
