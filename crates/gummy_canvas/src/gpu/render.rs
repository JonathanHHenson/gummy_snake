use super::pipeline::{align_to, to_wgpu_color};
use super::types::*;

impl GpuRenderer {
    pub fn begin_frame(&mut self) {
        self.commands.clear();
    }

    pub fn set_clear_color(&mut self, color: GpuColor) {
        self.clear_color = color;
        self.commands.push(DrawCommand::Clear(color));
    }

    pub fn clear_transparent(&mut self) {
        self.set_clear_color(GpuColor {
            r: 0,
            g: 0,
            b: 0,
            a: 0,
        });
    }

    pub fn draw_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::Triangles(vertices));
        }
    }

    pub fn render(&mut self) {
        self.write_viewport(self.texture_size.width, self.texture_size.height);
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas render encoder"),
            });
        self.encode_commands(&mut encoder, &self.texture_view, &self.pipeline);
        self.queue.submit([encoder.finish()]);
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn read_pixels(&self) -> Result<Vec<u8>, String> {
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

    fn encode_commands(
        &self,
        encoder: &mut wgpu::CommandEncoder,
        view: &wgpu::TextureView,
        pipeline: &wgpu::RenderPipeline,
    ) {
        let clear = self
            .commands
            .iter()
            .rev()
            .find_map(|command| match command {
                DrawCommand::Clear(color) => Some(*color),
                DrawCommand::Triangles(_) => None,
                DrawCommand::Image { .. } => None,
            });
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas primitive render pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: clear
                        .map(to_wgpu_color)
                        .map(wgpu::LoadOp::Clear)
                        .unwrap_or(wgpu::LoadOp::Load),
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(pipeline);
        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
        let mut skip_until_last_clear = clear.is_some();
        let mut batched_vertices = Vec::new();
        for command in &self.commands {
            match command {
                DrawCommand::Clear(color) => {
                    if skip_until_last_clear && Some(*color) == clear {
                        skip_until_last_clear = false;
                    }
                }
                DrawCommand::Triangles(vertices) => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batched_vertices.extend(vertices.iter().map(|(position, color)| Vertex {
                        position: *position,
                        color: color.as_float(),
                    }));
                }
                DrawCommand::Image {
                    key,
                    vertices,
                    linear,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() {
                        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                            label: Some("gummy_canvas primitive vertices"),
                            size: (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64,
                            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                            mapped_at_creation: false,
                        });
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(texture) = self.textures.get(key) else {
                        continue;
                    };
                    let image_vertices: Vec<ImageVertex> = vertices
                        .iter()
                        .map(|(position, uv)| ImageVertex {
                            position: *position,
                            uv: *uv,
                        })
                        .collect();
                    let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                        label: Some("gummy_canvas image vertices"),
                        size: (image_vertices.len() * std::mem::size_of::<ImageVertex>()) as u64,
                        usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                        mapped_at_creation: false,
                    });
                    self.queue
                        .write_buffer(&buffer, 0, bytemuck::cast_slice(&image_vertices));
                    pass.set_pipeline(&self.image_pipeline);
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    let bind_group = if *linear {
                        &texture.linear_bind_group
                    } else {
                        &texture.nearest_bind_group
                    };
                    pass.set_bind_group(1, bind_group, &[]);
                    pass.set_vertex_buffer(0, buffer.slice(..));
                    pass.draw(0..image_vertices.len() as u32, 0..1);
                }
            }
        }
        if !batched_vertices.is_empty() {
            let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas primitive vertices"),
                size: (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            self.queue
                .write_buffer(&buffer, 0, bytemuck::cast_slice(&batched_vertices));
            pass.set_vertex_buffer(0, buffer.slice(..));
            pass.draw(0..batched_vertices.len() as u32, 0..1);
        }
    }
}
