use crate::gpu::pipeline::{align_to, to_wgpu_color};
use crate::gpu::types::*;

impl GpuRenderer {
    pub fn begin_frame(&mut self) {
        self.commands.clear();
        self.clip_textures.truncate(1);
        self.current_clip_id = 0;
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
            self.commands.push(DrawCommand::Triangles {
                vertices,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_filled_ellipse(&mut self, cx: f32, cy: f32, rx: f32, ry: f32, color: GpuColor) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::Ellipse {
                cx,
                cy,
                rx,
                ry,
                color,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_erase_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::EraseTriangles {
                vertices,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn render(&mut self) {
        self.write_viewport(self.texture_size.width, self.texture_size.height);
        self.ensure_render_vertex_buffers();
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas render encoder"),
            });
        self.encode_commands(&mut encoder);
        self.queue.submit([encoder.finish()]);
    }

    pub fn only_pending_clear(&self) -> Option<GpuColor> {
        let mut clear = None;
        for command in &self.commands {
            match command {
                DrawCommand::Clear(color) => clear = Some(*color),
                DrawCommand::Triangles { vertices, .. }
                | DrawCommand::EraseTriangles { vertices, .. } => {
                    if !vertices.is_empty() {
                        return None;
                    }
                }
                DrawCommand::Ellipse { .. } => return None,
                DrawCommand::Image { .. } => return None,
            }
        }
        clear
    }

    pub fn pending_commands(&self) -> &[DrawCommand] {
        &self.commands
    }

    pub fn render_loop_counters(&self) -> (u64, u64, u64, u64) {
        (
            self.vertex_buffer_allocations,
            self.vertex_uploads,
            self.primitive_batches,
            self.image_batches,
        )
    }

    pub fn reset_render_loop_counters(&mut self) {
        self.vertex_buffer_allocations = 0;
        self.vertex_uploads = 0;
        self.primitive_batches = 0;
        self.image_batches = 0;
    }

    fn ensure_render_vertex_buffers(&mut self) {
        let mut primitive_vertices = 0usize;
        let mut erase_vertices = 0usize;
        let mut image_vertices = 0usize;
        for command in &self.commands {
            match command {
                DrawCommand::Triangles { vertices, .. } => {
                    primitive_vertices += vertices.len();
                }
                DrawCommand::Ellipse { .. } => {
                    primitive_vertices += 64 * 3;
                }
                DrawCommand::EraseTriangles { vertices, .. } => {
                    erase_vertices = erase_vertices.max(vertices.len());
                }
                DrawCommand::Image { .. } => {
                    image_vertices = image_vertices.max(6);
                }
                DrawCommand::Clear(_) => {}
            }
        }
        self.ensure_primitive_vertex_capacity(primitive_vertices);
        self.ensure_erase_vertex_capacity(erase_vertices);
        self.ensure_image_vertex_capacity(image_vertices);
    }

    fn ensure_primitive_vertex_capacity(&mut self, required: usize) {
        if required == 0 || self.primitive_vertex_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.primitive_vertex_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable primitive vertices"),
            size: (capacity * std::mem::size_of::<Vertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.primitive_vertex_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_erase_vertex_capacity(&mut self, required: usize) {
        if required == 0 || self.erase_vertex_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.erase_vertex_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable erase vertices"),
            size: (capacity * std::mem::size_of::<Vertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.erase_vertex_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_image_vertex_capacity(&mut self, required: usize) {
        if required == 0 || self.image_vertex_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.image_vertex_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable image vertices"),
            size: (capacity * std::mem::size_of::<ImageVertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.image_vertex_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn read_pixels(&mut self) -> Result<Vec<u8>, String> {
        self.read_pixels_after_encoding(false)
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn render_and_read_pixels(&mut self) -> Result<Vec<u8>, String> {
        self.read_pixels_after_encoding(true)
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn read_pixel_region(
        &mut self,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<Vec<u8>, String> {
        let width = width.max(1).min(self.texture_size.width.saturating_sub(x));
        let height = height.max(1).min(self.texture_size.height.saturating_sub(y));
        let bytes_per_pixel = 4usize;
        let unpadded_bytes_per_row = width as usize * bytes_per_pixel;
        let padded_bytes_per_row = align_to(
            unpadded_bytes_per_row,
            wgpu::COPY_BYTES_PER_ROW_ALIGNMENT as usize,
        );
        let output_size = padded_bytes_per_row * height as usize;
        let output = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas region readback buffer"),
            size: output_size as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas region readback encoder"),
            });
        encoder.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &output,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(padded_bytes_per_row as u32),
                    rows_per_image: Some(height),
                },
            },
            wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
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
        let mut pixels = vec![0; unpadded_bytes_per_row * height as usize];
        for row in 0..height as usize {
            let src_start = row * padded_bytes_per_row;
            let dst_start = row * unpadded_bytes_per_row;
            pixels[dst_start..dst_start + unpadded_bytes_per_row]
                .copy_from_slice(&mapped[src_start..src_start + unpadded_bytes_per_row]);
        }
        drop(mapped);
        output.unmap();
        Ok(pixels)
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
            self.encode_commands(&mut encoder);
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

    fn encode_commands(&mut self, encoder: &mut wgpu::CommandEncoder) {
        let clear = self
            .commands
            .iter()
            .rev()
            .find_map(|command| match command {
                DrawCommand::Clear(color) => Some(*color),
                DrawCommand::Triangles { .. } => None,
                DrawCommand::Ellipse { .. } => None,
                DrawCommand::EraseTriangles { .. } => None,
                DrawCommand::Image { .. } => None,
            });
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
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(&self.pipeline);
        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
        pass.set_bind_group(1, &self.clip_textures[0].bind_group, &[]);
        let mut skip_until_last_clear = clear.is_some();
        let mut batched_vertices = std::mem::take(&mut self.primitive_staging);
        batched_vertices.clear();
        let mut batched_clip_id = 0usize;
        for command in &self.commands {
            match command {
                DrawCommand::Clear(color) => {
                    if skip_until_last_clear && Some(*color) == clear {
                        skip_until_last_clear = false;
                    }
                }
                DrawCommand::Triangles { vertices, clip_id } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() && batched_clip_id != *clip_id {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(&self.pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    batched_clip_id = *clip_id;
                    batched_vertices.extend(vertices.iter().map(|(position, color)| Vertex {
                        position: *position,
                        color: color.as_float(),
                    }));
                }
                DrawCommand::Ellipse {
                    cx,
                    cy,
                    rx,
                    ry,
                    color,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() && batched_clip_id != *clip_id {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(&self.pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    batched_clip_id = *clip_id;
                    push_ellipse_vertices(
                        &mut batched_vertices,
                        *cx as f64,
                        *cy as f64,
                        *rx as f64,
                        *ry as f64,
                        *color,
                    );
                }
                DrawCommand::EraseTriangles { vertices, clip_id } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(&self.pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    self.erase_staging.clear();
                    self.erase_staging
                        .extend(vertices.iter().map(|(position, color)| Vertex {
                            position: *position,
                            color: color.as_float(),
                        }));
                    self.vertex_uploads += 1;
                    self.primitive_batches += 1;
                    let buffer = self
                        .erase_vertex_buffer
                        .as_ref()
                        .expect("erase vertex buffer is prepared");
                    self.queue
                        .write_buffer(&buffer, 0, bytemuck::cast_slice(&self.erase_staging));
                    pass.set_pipeline(&self.erase_pipeline);
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    pass.set_bind_group(1, &self.clip_textures[*clip_id].bind_group, &[]);
                    pass.set_vertex_buffer(0, buffer.slice(..));
                    pass.draw(0..self.erase_staging.len() as u32, 0..1);
                }
                DrawCommand::Image {
                    key,
                    vertices,
                    linear,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(&self.pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(texture) = self.textures.get(key) else {
                        continue;
                    };
                    self.image_staging.clear();
                    self.image_staging
                        .extend(vertices.iter().map(|(position, uv, tint)| ImageVertex {
                            position: *position,
                            uv: *uv,
                            tint: tint.as_float(),
                        }));
                    self.vertex_uploads += 1;
                    self.image_batches += 1;
                    let buffer = self
                        .image_vertex_buffer
                        .as_ref()
                        .expect("image vertex buffer is prepared");
                    self.queue
                        .write_buffer(&buffer, 0, bytemuck::cast_slice(&self.image_staging));
                    pass.set_pipeline(&self.image_pipeline);
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    let bind_group = if *linear {
                        &texture.linear_bind_group
                    } else {
                        &texture.nearest_bind_group
                    };
                    pass.set_bind_group(1, bind_group, &[]);
                    pass.set_bind_group(2, &self.clip_textures[*clip_id].bind_group, &[]);
                    pass.set_vertex_buffer(0, buffer.slice(..));
                    pass.draw(0..self.image_staging.len() as u32, 0..1);
                }
            }
        }
        if !batched_vertices.is_empty() {
            self.vertex_uploads += 1;
            self.primitive_batches += 1;
            let buffer = self
                .primitive_vertex_buffer
                .as_ref()
                .expect("primitive vertex buffer is prepared");
            self.queue
                .write_buffer(&buffer, 0, bytemuck::cast_slice(&batched_vertices));
            pass.set_pipeline(&self.pipeline);
            pass.set_bind_group(0, &self.viewport_bind_group, &[]);
            pass.set_bind_group(1, &self.clip_textures[batched_clip_id].bind_group, &[]);
            pass.set_vertex_buffer(0, buffer.slice(..));
            pass.draw(0..batched_vertices.len() as u32, 0..1);
        }
        batched_vertices.clear();
        self.primitive_staging = batched_vertices;
    }
}

fn push_ellipse_vertices(
    vertices: &mut Vec<Vertex>,
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    color: GpuColor,
) {
    let steps = 64usize;
    let color = color.as_float();
    for index in 0..steps {
        let a = 2.0 * std::f64::consts::PI * index as f64 / steps as f64;
        let b = 2.0 * std::f64::consts::PI * (index + 1) as f64 / steps as f64;
        vertices.push(Vertex {
            position: [cx as f32, cy as f32],
            color,
        });
        vertices.push(Vertex {
            position: [(cx + a.cos() * rx) as f32, (cy + a.sin() * ry) as f32],
            color,
        });
        vertices.push(Vertex {
            position: [(cx + b.cos() * rx) as f32, (cy + b.sin() * ry) as f32],
            color,
        });
    }
}
