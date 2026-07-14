use crate::gpu::render::batching::RenderBufferOffsets;
use crate::gpu::render::plain::{plain_command_requires_depth, plain_commands_require_depth};
use crate::gpu::types::*;

impl GpuRenderer {
    pub(super) fn encode_commands(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        commands: &[DrawCommand],
    ) {
        let mut render_offsets = RenderBufferOffsets::default();
        if !commands.iter().any(is_special_command) {
            let mut depth_initialized = false;
            self.encode_plain_segment(
                encoder,
                commands,
                &mut render_offsets,
                &mut depth_initialized,
            );
            return;
        }

        let mut segment_start = 0usize;
        let mut index = 0usize;
        let mut depth_initialized = false;
        while index < commands.len() {
            match &commands[index] {
                DrawCommand::DestinationBlend {
                    shape,
                    cx,
                    cy,
                    rx,
                    ry,
                    color,
                    blend_mode,
                } => {
                    self.encode_plain_segment(
                        encoder,
                        &commands[segment_start..index],
                        &mut render_offsets,
                        &mut depth_initialized,
                    );
                    self.encode_destination_blend_pass(
                        encoder,
                        *shape,
                        *cx,
                        *cy,
                        *rx,
                        *ry,
                        *color,
                        *blend_mode,
                    );
                    index += 1;
                    segment_start = index;
                }
                DrawCommand::PixelPrefix {
                    byte_limit,
                    stride,
                    red_delta,
                    green_delta,
                } => {
                    self.encode_plain_segment(
                        encoder,
                        &commands[segment_start..index],
                        &mut render_offsets,
                        &mut depth_initialized,
                    );
                    self.encode_pixel_prefix_pass(
                        encoder,
                        *byte_limit,
                        *stride,
                        *red_delta,
                        *green_delta,
                    );
                    index += 1;
                    segment_start = index;
                }
                DrawCommand::PixelFilter { mode, value } => {
                    self.encode_plain_segment(
                        encoder,
                        &commands[segment_start..index],
                        &mut render_offsets,
                        &mut depth_initialized,
                    );
                    self.encode_pixel_filter_pass(encoder, *mode, *value);
                    index += 1;
                    segment_start = index;
                }
                DrawCommand::Text { .. } => {
                    self.encode_plain_segment(
                        encoder,
                        &commands[segment_start..index],
                        &mut render_offsets,
                        &mut depth_initialized,
                    );
                    let mut batch_end = index + 1;
                    while batch_end < commands.len()
                        && matches!(commands[batch_end], DrawCommand::Text { .. })
                    {
                        batch_end += 1;
                    }
                    self.encode_text_pass(encoder, &commands[index..batch_end]);
                    index = batch_end;
                    segment_start = batch_end;
                }
                _ => index += 1,
            }
        }
        self.encode_plain_segment(
            encoder,
            &commands[segment_start..],
            &mut render_offsets,
            &mut depth_initialized,
        );
    }

    fn encode_plain_segment(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        commands: &[DrawCommand],
        render_offsets: &mut RenderBufferOffsets,
        depth_initialized: &mut bool,
    ) {
        if commands.is_empty() {
            return;
        }

        let mut compatible_segment_start = 0;
        let mut requires_depth = plain_command_requires_depth(&commands[0]);
        for index in 1..=commands.len() {
            let next_requires_depth = commands.get(index).map(plain_command_requires_depth);
            if next_requires_depth == Some(requires_depth) {
                continue;
            }

            self.encode_depth_compatible_plain_segment(
                encoder,
                &commands[compatible_segment_start..index],
                render_offsets,
                depth_initialized,
            );
            compatible_segment_start = index;
            if let Some(next_requires_depth) = next_requires_depth {
                requires_depth = next_requires_depth;
            }
        }
    }

    fn encode_depth_compatible_plain_segment(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        commands: &[DrawCommand],
        render_offsets: &mut RenderBufferOffsets,
        depth_initialized: &mut bool,
    ) {
        let requires_depth = plain_commands_require_depth(commands);
        let clear_depth =
            requires_depth && plain_segment_clears_depth(commands, *depth_initialized);
        self.encode_plain_commands(encoder, commands, render_offsets, clear_depth);
        if requires_depth {
            *depth_initialized = true;
        } else if commands
            .iter()
            .any(|command| matches!(command, DrawCommand::Clear(_)))
        {
            *depth_initialized = false;
        }
    }
}

fn is_special_command(command: &DrawCommand) -> bool {
    matches!(
        command,
        DrawCommand::DestinationBlend { .. }
            | DrawCommand::PixelPrefix { .. }
            | DrawCommand::PixelFilter { .. }
            | DrawCommand::Text { .. }
    )
}

fn plain_segment_clears_depth(commands: &[DrawCommand], depth_initialized: bool) -> bool {
    !depth_initialized
        || commands
            .iter()
            .any(|command| matches!(command, DrawCommand::Clear(_)))
}

#[cfg(test)]
mod tests {
    use super::plain_segment_clears_depth;
    use crate::gpu::{DrawCommand, GpuColor};

    #[test]
    fn depth_is_cleared_once_and_at_explicit_clear_boundaries() {
        let draw = DrawCommand::Triangles {
            vertices: Vec::new(),
            blend_mode: crate::types::BlendMode::Blend,
            clip_id: 0,
        };
        let clear = DrawCommand::Clear(GpuColor {
            r: 0,
            g: 0,
            b: 0,
            a: 255,
        });

        assert!(plain_segment_clears_depth(
            std::slice::from_ref(&draw),
            false
        ));
        assert!(!plain_segment_clears_depth(&[draw], true));
        assert!(plain_segment_clears_depth(&[clear], true));
    }
}
