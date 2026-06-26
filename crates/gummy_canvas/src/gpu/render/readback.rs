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
        let output = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas readback buffer"),
            size: output_size as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas readback encoder"),
            });
        if encode_render {
            self.write_viewport(self.texture_size.width, self.texture_size.height);
            self.ensure_render_vertex_buffers();
            let encode_start = Instant::now();
            self.encode_commands(&mut encoder);
            self.encode_time_ms += encode_start.elapsed().as_secs_f64() * 1000.0;
        }
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
        self.queue.submit([encoder.finish()]);
        let slice = output.slice(..);
        let (sender, receiver) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |result| {
            let _ = sender.send(result);
        });
        let _ = self.device.poll(wgpu::PollType::Wait);
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
}
