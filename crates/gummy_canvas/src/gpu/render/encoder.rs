use crate::gpu::render::batching::RenderBufferOffsets;
use crate::gpu::types::*;

impl GpuRenderer {
    pub(super) fn encode_commands(&mut self, encoder: &mut wgpu::CommandEncoder) {
        if !self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::BlendEllipse { .. }
                    | DrawCommand::PixelPrefix { .. }
                    | DrawCommand::PixelFilter { .. }
                    | DrawCommand::Text { .. }
            )
        }) {
            let mut render_offsets = RenderBufferOffsets::default();
            self.encode_plain_commands(encoder, &mut render_offsets);
            return;
        }

        let commands = self.commands.clone();
        let mut render_offsets = RenderBufferOffsets::default();
        let mut segment_start = 0usize;
        let mut skip_special_until = 0usize;
        for (index, command) in commands.iter().enumerate() {
            if index < skip_special_until {
                continue;
            }
            match command {
                DrawCommand::BlendEllipse {
                    cx,
                    cy,
                    rx,
                    ry,
                    color,
                    blend_mode,
                } => {
                    self.commands = commands[segment_start..index].to_vec();
                    if !self.commands.is_empty() {
                        self.encode_plain_commands(encoder, &mut render_offsets);
                    }
                    self.encode_blend_ellipse_pass(
                        encoder,
                        *cx,
                        *cy,
                        *rx,
                        *ry,
                        *color,
                        *blend_mode,
                    );
                    segment_start = index + 1;
                }
                DrawCommand::PixelPrefix {
                    byte_limit,
                    stride,
                    red_delta,
                    green_delta,
                } => {
                    self.commands = commands[segment_start..index].to_vec();
                    if !self.commands.is_empty() {
                        self.encode_plain_commands(encoder, &mut render_offsets);
                    }
                    self.encode_pixel_prefix_pass(
                        encoder,
                        *byte_limit,
                        *stride,
                        *red_delta,
                        *green_delta,
                    );
                    segment_start = index + 1;
                }
                DrawCommand::PixelFilter { mode, value } => {
                    self.commands = commands[segment_start..index].to_vec();
                    if !self.commands.is_empty() {
                        self.encode_plain_commands(encoder, &mut render_offsets);
                    }
                    self.encode_pixel_filter_pass(encoder, *mode, *value);
                    segment_start = index + 1;
                }
                DrawCommand::Text { .. } => {
                    self.commands = commands[segment_start..index].to_vec();
                    if !self.commands.is_empty() {
                        self.encode_plain_commands(encoder, &mut render_offsets);
                    }
                    let mut batch_end = index + 1;
                    while batch_end < commands.len()
                        && matches!(commands[batch_end], DrawCommand::Text { .. })
                    {
                        batch_end += 1;
                    }
                    self.encode_text_pass(encoder, &commands[index..batch_end]);
                    segment_start = batch_end;
                    skip_special_until = batch_end;
                }
                _ => {}
            }
        }
        self.commands = commands[segment_start..].to_vec();
        if !self.commands.is_empty() {
            self.encode_plain_commands(encoder, &mut render_offsets);
        }
        self.commands = commands;
    }
}
