use std::time::Instant;

use crate::gpu::pipeline::align_to;
use crate::gpu::types::*;

impl GpuRenderer {
    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn read_pixels(&mut self) -> Result<Vec<u8>, String> {
        self.read_pixels_after_encoding(false)
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn render_and_read_pixels(&mut self) -> Result<Vec<u8>, String> {
        self.read_pixels_after_encoding(true)
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    fn read_pixels_after_encoding(&mut self, encode_render: bool) -> Result<Vec<u8>, String> {
        let bytes_per_pixel = 4usize;
        let unpadded_bytes_per_row = self.texture_size.width as usize * bytes_per_pixel;
        let padded_bytes_per_row = align_to(
            unpadded_bytes_per_row,
            wgpu::COPY_BYTES_PER_ROW_ALIGNMENT as usize,
        );
        let output_size = padded_bytes_per_row * self.texture_size.height as usize;
        self.ensure_readback_buffer(output_size);
        let mut encoder =
            self.device_context
                .device()
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("gummy_canvas readback encoder"),
                });
        let commands = if encode_render {
            self.write_viewport(self.texture_size.width, self.texture_size.height);
            let commands = std::mem::take(&mut self.commands);
            self.ensure_render_vertex_buffers(&commands);
            let encode_start = Instant::now();
            self.encode_commands(&mut encoder, &commands);
            self.encode_time_ms += encode_start.elapsed().as_secs_f64() * 1000.0;
            Some(commands)
        } else {
            None
        };
        let output = self
            .readback_buffer
            .as_ref()
            .expect("readback buffer is allocated before encoding the copy");
        encoder.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &output,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(padded_bytes_per_row as u32),
                    rows_per_image: Some(self.texture_size.height),
                },
            },
            self.texture_size,
        );
        self.device_context.queue().submit([encoder.finish()]);
        if let Some(commands) = commands {
            self.commands = commands;
        }
        let slice = output.slice(..output_size as u64);
        let (sender, receiver) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |result| {
            let _ = sender.send(result);
        });
        let _ = self.device_context.device().poll(wgpu::PollType::Wait);
        receiver
            .recv()
            .map_err(|err| format!("Failed to receive GPU readback status: {err}"))?
            .map_err(|err| format!("Failed to map GPU readback buffer: {err}"))?;
        let mapped = slice.get_mapped_range();
        let mut pixels = vec![0; unpadded_bytes_per_row * self.texture_size.height as usize];
        for y in 0..self.texture_size.height as usize {
            let src_start = y * padded_bytes_per_row;
            let dst_start = y * unpadded_bytes_per_row;
            pixels[dst_start..dst_start + unpadded_bytes_per_row]
                .copy_from_slice(&mapped[src_start..src_start + unpadded_bytes_per_row]);
        }
        drop(mapped);
        output.unmap();
        Ok(pixels)
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    fn ensure_readback_buffer(&mut self, required_size: usize) {
        if self.readback_buffer_capacity >= required_size {
            return;
        }
        let capacity = required_size
            .checked_next_power_of_two()
            .unwrap_or(required_size);
        self.readback_buffer = Some(self.device_context.device().create_buffer(
            &wgpu::BufferDescriptor {
                label: Some("gummy_canvas reusable readback buffer"),
                size: capacity as u64,
                usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
                mapped_at_creation: false,
            },
        ));
        self.readback_buffer_capacity = capacity;
        self.readback_buffer_allocations += 1;
    }
}
