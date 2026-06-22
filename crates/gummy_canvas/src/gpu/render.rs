use crate::gpu::pipeline::{align_to, to_wgpu_color};
use crate::gpu::types::*;
use crate::BlendMode;
use wgpu::util::DeviceExt;

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

    pub fn draw_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>, blend_mode: BlendMode) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::Triangles {
                vertices,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn ensure_model_mesh(
        &mut self,
        key: u64,
        vertices: &[ModelVertex],
        indices: &[u32],
    ) -> Result<u32, String> {
        if let Some(mesh) = self.model_meshes.get(&key) {
            return Ok(mesh.index_count);
        }
        if vertices.is_empty() || indices.is_empty() {
            return Ok(0);
        }
        let index_count = u32::try_from(indices.len())
            .map_err(|_| "model index count exceeds GPU draw limits".to_owned())?;
        let vertex_buffer = self
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("gummy_canvas model vertices"),
                contents: bytemuck::cast_slice(vertices),
                usage: wgpu::BufferUsages::VERTEX,
            });
        let index_buffer = self
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("gummy_canvas model indices"),
                contents: bytemuck::cast_slice(indices),
                usage: wgpu::BufferUsages::INDEX,
            });
        self.model_meshes.insert(
            key,
            GpuModelMesh {
                _vertex_buffer: vertex_buffer,
                _index_buffer: index_buffer,
                index_count,
            },
        );
        self.vertex_buffer_allocations += 2;
        Ok(index_count)
    }

    pub fn draw_model(&mut self, key: u64, index_count: u32, uniform: ModelUniform) {
        if index_count > 0 {
            self.commands.push(DrawCommand::Model {
                key,
                index_count,
                uniform,
            });
        }
    }

    pub fn draw_textured_model(
        &mut self,
        model_key: u64,
        texture_key: u64,
        index_count: u32,
        uniform: ModelUniform,
        linear: bool,
    ) {
        if index_count > 0 {
            self.commands.push(DrawCommand::TexturedModel {
                model_key,
                texture_key,
                index_count,
                uniform,
                linear,
            });
        }
    }

    pub fn draw_filled_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::Ellipse {
                cx,
                cy,
                rx,
                ry,
                color,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_blend_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::BlendEllipse {
                cx,
                cy,
                rx,
                ry,
                color,
                blend_mode,
            });
        }
    }

    pub fn draw_pixel_prefix_mutation(
        &mut self,
        byte_limit: u32,
        stride: u32,
        red_delta: i32,
        green_delta: i32,
    ) {
        if byte_limit > 0 && stride > 0 {
            self.commands.push(DrawCommand::PixelPrefix {
                byte_limit,
                stride,
                red_delta,
                green_delta,
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

    pub fn draw_text(
        &mut self,
        text: String,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        font_size: f32,
        line_height: f32,
        color: GpuColor,
    ) {
        if !text.is_empty() && font_size > 0.0 && line_height > 0.0 {
            self.commands.push(DrawCommand::Text {
                text,
                x,
                y,
                width: width.max(1.0),
                height: height.max(line_height).max(1.0),
                font_size,
                line_height,
                color,
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
                DrawCommand::Ellipse { .. }
                | DrawCommand::BlendEllipse { .. }
                | DrawCommand::PixelPrefix { .. }
                | DrawCommand::Model { .. }
                | DrawCommand::TexturedModel { .. }
                | DrawCommand::Text { .. } => return None,
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
                DrawCommand::BlendEllipse { .. } => {}
                DrawCommand::PixelPrefix { .. } => {}
                DrawCommand::EraseTriangles { vertices, .. } => {
                    erase_vertices += vertices.len();
                }
                DrawCommand::Image { .. } => {
                    image_vertices += 6;
                }
                DrawCommand::Model { .. } | DrawCommand::TexturedModel { .. } => {}
                DrawCommand::Text { .. } => {}
                DrawCommand::Clear(_) => {}
            }
        }
        self.ensure_primitive_vertex_capacity(primitive_vertices);
        self.ensure_erase_vertex_capacity(erase_vertices);
        self.ensure_image_vertex_capacity(image_vertices);
        let model_uniforms = self
            .commands
            .iter()
            .filter(|command| {
                matches!(
                    command,
                    DrawCommand::Model { .. } | DrawCommand::TexturedModel { .. }
                )
            })
            .count();
        self.ensure_model_uniform_capacity(model_uniforms);
    }

    fn ensure_model_uniform_capacity(&mut self, required: usize) {
        if required == 0 || self.model_uniform_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.model_uniform_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas model uniforms"),
            size: (capacity * std::mem::size_of::<ModelUniform>()) as u64,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        self.model_uniform_bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas model uniform bind group"),
            layout: &self.model_bind_group_layout,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: self.model_uniform_buffer.as_entire_binding(),
            }],
        });
        self.model_uniform_capacity = capacity;
        self.vertex_buffer_allocations += 1;
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
        if !self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::BlendEllipse { .. }
                    | DrawCommand::PixelPrefix { .. }
                    | DrawCommand::Text { .. }
            )
        }) {
            self.encode_plain_commands(encoder);
            return;
        }

        let commands = self.commands.clone();
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
                        self.encode_plain_commands(encoder);
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
                        self.encode_plain_commands(encoder);
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
                DrawCommand::Text { .. } => {
                    self.commands = commands[segment_start..index].to_vec();
                    if !self.commands.is_empty() {
                        self.encode_plain_commands(encoder);
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
            self.encode_plain_commands(encoder);
        }
        self.commands = commands;
    }

    fn encode_plain_commands(&mut self, encoder: &mut wgpu::CommandEncoder) {
        let clear = self
            .commands
            .iter()
            .rev()
            .find_map(|command| match command {
                DrawCommand::Clear(color) => Some(*color),
                DrawCommand::Triangles { .. } => None,
                DrawCommand::Ellipse { .. } => None,
                DrawCommand::BlendEllipse { .. } => None,
                DrawCommand::PixelPrefix { .. } => None,
                DrawCommand::Model { .. } => None,
                DrawCommand::TexturedModel { .. } => None,
                DrawCommand::Text { .. } => None,
                DrawCommand::EraseTriangles { .. } => None,
                DrawCommand::Image { .. } => None,
            });
        let last_clear_index = self
            .commands
            .iter()
            .rposition(|command| matches!(command, DrawCommand::Clear(_)));
        let has_image_commands = self
            .commands
            .iter()
            .any(|command| matches!(command, DrawCommand::Image { .. }));
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
                let DrawCommand::Image { key, vertices, .. } = command else {
                    continue;
                };
                if !self.textures.contains_key(key) {
                    continue;
                }
                let offset = image_staging.len();
                image_staging.extend(vertices.iter().map(|(position, uv, tint)| ImageVertex {
                    position: *position,
                    uv: *uv,
                    tint: tint.as_float(),
                }));
                image_offsets[command_index] = Some((offset, vertices.len()));
            }
            if !image_staging.is_empty() {
                self.vertex_uploads += 1;
                let buffer = self
                    .image_vertex_buffer
                    .as_ref()
                    .expect("image vertex buffer is prepared");
                self.queue
                    .write_buffer(buffer, 0, bytemuck::cast_slice(&image_staging));
            }
        }
        let mut model_uniforms = Vec::new();
        let mut model_uniform_indices = if self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::Model { .. } | DrawCommand::TexturedModel { .. }
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
            let uniform = match command {
                DrawCommand::Model { uniform, .. } | DrawCommand::TexturedModel { uniform, .. } => {
                    uniform
                }
                _ => continue,
            };
            let uniform_index = model_uniforms.len() as u32;
            model_uniforms.push(*uniform);
            model_uniform_indices[command_index] = Some(uniform_index);
        }
        if !model_uniforms.is_empty() {
            self.queue.write_buffer(
                &self.model_uniform_buffer,
                0,
                bytemuck::cast_slice(&model_uniforms),
            );
            self.vertex_uploads += 1;
        }
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
        let mut skip_until_last_clear = clear.is_some();
        let mut batched_vertices = std::mem::take(&mut self.primitive_staging);
        batched_vertices.clear();
        let mut batched_clip_id = 0usize;
        let mut batched_blend_mode = BlendMode::Blend;
        let mut primitive_vertex_offset = 0usize;
        let mut erase_vertex_offset = 0usize;
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
                    if !batched_vertices.is_empty()
                        && (batched_clip_id != *clip_id || batched_blend_mode != *blend_mode)
                    {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    batched_clip_id = *clip_id;
                    batched_blend_mode = *blend_mode;
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
                    blend_mode,
                    clip_id,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty()
                        && (batched_clip_id != *clip_id || batched_blend_mode != *blend_mode)
                    {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    batched_clip_id = *clip_id;
                    batched_blend_mode = *blend_mode;
                    push_ellipse_vertices(
                        &mut batched_vertices,
                        *cx as f64,
                        *cy as f64,
                        *rx as f64,
                        *ry as f64,
                        *color,
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
                    if !batched_vertices.is_empty() {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(mesh) = self.model_meshes.get(key) else {
                        continue;
                    };
                    let Some(uniform_index) = model_uniform_indices[command_index] else {
                        continue;
                    };
                    let count = (*index_count).min(mesh.index_count);
                    if count == 0 {
                        continue;
                    }
                    self.primitive_batches += 1;
                    pass.set_pipeline(&self.model_pipeline);
                    pass.set_bind_group(0, &self.model_uniform_bind_group, &[]);
                    pass.set_vertex_buffer(0, mesh._vertex_buffer.slice(..));
                    pass.set_index_buffer(mesh._index_buffer.slice(..), wgpu::IndexFormat::Uint32);
                    pass.draw_indexed(0..count, 0, uniform_index..uniform_index + 1);
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
                    if !batched_vertices.is_empty() {
                        self.vertex_uploads += 1;
                        self.primitive_batches += 1;
                        let buffer = self
                            .primitive_vertex_buffer
                            .as_ref()
                            .expect("primitive vertex buffer is prepared");
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(mesh) = self.model_meshes.get(model_key) else {
                        continue;
                    };
                    let Some(texture) = self.textures.get(texture_key) else {
                        continue;
                    };
                    let Some(uniform_index) = model_uniform_indices[command_index] else {
                        continue;
                    };
                    let count = (*index_count).min(mesh.index_count);
                    if count == 0 {
                        continue;
                    }
                    self.primitive_batches += 1;
                    pass.set_pipeline(&self.textured_model_pipeline);
                    pass.set_bind_group(0, &self.model_uniform_bind_group, &[]);
                    let bind_group = if *linear {
                        &texture.linear_bind_group
                    } else {
                        &texture.nearest_bind_group
                    };
                    pass.set_bind_group(1, bind_group, &[]);
                    pass.set_vertex_buffer(0, mesh._vertex_buffer.slice(..));
                    pass.set_index_buffer(mesh._index_buffer.slice(..), wgpu::IndexFormat::Uint32);
                    pass.draw_indexed(0..count, 0, uniform_index..uniform_index + 1);
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
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
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
                    let offset_bytes = (erase_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                    let size_bytes =
                        (self.erase_staging.len() * std::mem::size_of::<Vertex>()) as u64;
                    self.queue.write_buffer(
                        &buffer,
                        offset_bytes,
                        bytemuck::cast_slice(&self.erase_staging),
                    );
                    erase_vertex_offset += self.erase_staging.len();
                    pass.set_pipeline(&self.erase_pipeline);
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    pass.set_bind_group(1, &self.clip_textures[*clip_id].bind_group, &[]);
                    pass.set_vertex_buffer(
                        0,
                        buffer.slice(offset_bytes..offset_bytes + size_bytes),
                    );
                    pass.draw(0..self.erase_staging.len() as u32, 0..1);
                }
                DrawCommand::Image {
                    key,
                    vertices: _,
                    linear,
                    blend_mode,
                    clip_id,
                } => {
                    if command_index < skip_image_commands_until {
                        continue;
                    }
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
                        let offset_bytes =
                            (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
                        let size_bytes =
                            (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
                        self.queue.write_buffer(
                            &buffer,
                            offset_bytes,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        primitive_vertex_offset += batched_vertices.len();
                        pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_bind_group(
                            1,
                            &self.clip_textures[batched_clip_id].bind_group,
                            &[],
                        );
                        pass.set_vertex_buffer(
                            0,
                            buffer.slice(offset_bytes..offset_bytes + size_bytes),
                        );
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(texture) = self.textures.get(key) else {
                        continue;
                    };
                    let Some((image_vertex_offset, image_vertex_len)) =
                        image_offsets[command_index]
                    else {
                        continue;
                    };
                    let mut batched_image_vertex_len = image_vertex_len;
                    let mut next_command_index = command_index + 1;
                    while next_command_index < self.commands.len() {
                        let DrawCommand::Image {
                            key: next_key,
                            vertices: _,
                            linear: next_linear,
                            blend_mode: next_blend_mode,
                            clip_id: next_clip_id,
                        } = &self.commands[next_command_index]
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
                        let Some((next_offset, next_len)) = image_offsets[next_command_index]
                        else {
                            break;
                        };
                        if next_offset != image_vertex_offset + batched_image_vertex_len {
                            break;
                        }
                        batched_image_vertex_len += next_len;
                        next_command_index += 1;
                    }
                    skip_image_commands_until = next_command_index;
                    self.image_batches += 1;
                    let buffer = self
                        .image_vertex_buffer
                        .as_ref()
                        .expect("image vertex buffer is prepared");
                    let offset_bytes =
                        (image_vertex_offset * std::mem::size_of::<ImageVertex>()) as u64;
                    let size_bytes =
                        (batched_image_vertex_len * std::mem::size_of::<ImageVertex>()) as u64;
                    pass.set_pipeline(self.image_pipeline_for(*blend_mode));
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    let bind_group = if *linear {
                        &texture.linear_bind_group
                    } else {
                        &texture.nearest_bind_group
                    };
                    pass.set_bind_group(1, bind_group, &[]);
                    pass.set_bind_group(2, &self.clip_textures[*clip_id].bind_group, &[]);
                    pass.set_vertex_buffer(
                        0,
                        buffer.slice(offset_bytes..offset_bytes + size_bytes),
                    );
                    pass.draw(0..batched_image_vertex_len as u32, 0..1);
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
            let offset_bytes = (primitive_vertex_offset * std::mem::size_of::<Vertex>()) as u64;
            let size_bytes = (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64;
            self.queue.write_buffer(
                &buffer,
                offset_bytes,
                bytemuck::cast_slice(&batched_vertices),
            );
            pass.set_pipeline(self.primitive_pipeline(batched_blend_mode));
            pass.set_bind_group(0, &self.viewport_bind_group, &[]);
            pass.set_bind_group(1, &self.clip_textures[batched_clip_id].bind_group, &[]);
            pass.set_vertex_buffer(0, buffer.slice(offset_bytes..offset_bytes + size_bytes));
            pass.draw(0..batched_vertices.len() as u32, 0..1);
        }
        batched_vertices.clear();
        self.primitive_staging = batched_vertices;
        image_staging.clear();
        self.image_staging = image_staging;
    }

    fn encode_blend_ellipse_pass(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        mode: BlendMode,
    ) {
        self.queue.write_buffer(
            &self.blend_ellipse_uniform_buffer,
            0,
            bytemuck::bytes_of(&BlendEllipseUniform {
                center_radius: [cx, cy, rx.max(0.0001), ry.max(0.0001)],
                color: color.as_float(),
                mode: crate::gpu::textures::blend_mode_id(mode),
                _padding: [0; 7],
            }),
        );
        let Some((x, y, width, height)) = self.effect_bounds(cx, cy, rx, ry) else {
            return;
        };
        encoder.copy_texture_to_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyTextureInfo {
                texture: &self.pixel_prefix_texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
        );
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas ordered blend ellipse pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &self.texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Load,
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(&self.blend_ellipse_pipeline);
        pass.set_bind_group(0, &self.blend_ellipse_bind_group, &[]);
        pass.set_scissor_rect(x, y, width, height);
        pass.draw(0..6, 0..1);
    }

    fn encode_pixel_prefix_pass(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        byte_limit: u32,
        stride: u32,
        red_delta: i32,
        green_delta: i32,
    ) {
        self.queue.write_buffer(
            &self.pixel_prefix_uniform_buffer,
            0,
            bytemuck::bytes_of(&PixelPrefixUniform {
                byte_limit,
                stride,
                red_delta,
                green_delta,
            }),
        );
        let Some((x, y, width, height)) = self.pixel_prefix_bounds(byte_limit) else {
            return;
        };
        encoder.copy_texture_to_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyTextureInfo {
                texture: &self.pixel_prefix_texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
        );
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas pixel prefix pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &self.texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Load,
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(&self.pixel_prefix_pipeline);
        pass.set_bind_group(0, &self.pixel_prefix_bind_group, &[]);
        pass.set_scissor_rect(x, y, width, height);
        pass.draw(0..6, 0..1);
    }

    fn pixel_prefix_bounds(&self, byte_limit: u32) -> Option<(u32, u32, u32, u32)> {
        let total_pixels = self.texture_size.width.saturating_mul(self.texture_size.height);
        let affected_pixels = byte_limit.div_ceil(4).min(total_pixels);
        if affected_pixels == 0 || self.texture_size.width == 0 {
            return None;
        }
        let width = affected_pixels.min(self.texture_size.width);
        let height = affected_pixels.div_ceil(self.texture_size.width);
        Some((0, 0, width, height))
    }

    fn effect_bounds(&self, cx: f32, cy: f32, rx: f32, ry: f32) -> Option<(u32, u32, u32, u32)> {
        let x0 = (cx - rx).floor().max(0.0) as u32;
        let y0 = (cy - ry).floor().max(0.0) as u32;
        let x1 = (cx + rx).ceil().clamp(0.0, self.texture_size.width as f32) as u32;
        let y1 = (cy + ry).ceil().clamp(0.0, self.texture_size.height as f32) as u32;
        if x1 <= x0 || y1 <= y0 {
            return None;
        }
        Some((x0, y0, x1 - x0, y1 - y0))
    }
    fn encode_text_pass(&mut self, encoder: &mut wgpu::CommandEncoder, commands: &[DrawCommand]) {
        self.text_viewport.update(
            &self.queue,
            glyphon::Resolution {
                width: self.texture_size.width,
                height: self.texture_size.height,
            },
        );
        let mut text_keys = Vec::new();
        let mut areas = Vec::new();
        for command in commands {
            let DrawCommand::Text {
                text,
                x,
                y,
                width,
                height,
                font_size,
                line_height,
                color,
            } = command
            else {
                continue;
            };
            let key = format!("{font_size:.2}|{line_height:.2}|{width:.2}|{height:.2}|{text}");
            if !self.text_buffers.contains_key(&key) {
                let mut buffer = glyphon::Buffer::new(
                    &mut self.text_font_system,
                    glyphon::Metrics::new(*font_size, *line_height),
                );
                buffer.set_size(&mut self.text_font_system, Some(*width), Some(*height));
                buffer.set_text(
                    &mut self.text_font_system,
                    text,
                    &glyphon::Attrs::new().family(glyphon::Family::SansSerif),
                    glyphon::Shaping::Advanced,
                );
                buffer.shape_until_scroll(&mut self.text_font_system, false);
                self.text_buffers.insert(key.clone(), buffer);
            }
            text_keys.push((key, *x, *y, *color));
        }
        for (key, x, y, color) in &text_keys {
            let Some(buffer) = self.text_buffers.get(key) else {
                continue;
            };
            areas.push(glyphon::TextArea {
                buffer,
                left: *x,
                top: *y,
                scale: 1.0,
                bounds: glyphon::TextBounds::default(),
                default_color: glyphon::Color::rgba(color.r, color.g, color.b, color.a),
                custom_glyphs: &[],
            });
        }
        if areas.is_empty() {
            return;
        }
        if self
            .text_renderer
            .prepare(
                &self.device,
                &self.queue,
                &mut self.text_font_system,
                &mut self.text_atlas,
                &self.text_viewport,
                areas,
                &mut self.text_swash_cache,
            )
            .is_err()
        {
            return;
        }
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas glyphon text pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &self.texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Load,
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        let _ = self
            .text_renderer
            .render(&self.text_atlas, &self.text_viewport, &mut pass);
        drop(pass);
        self.text_atlas.trim();
    }

    fn primitive_pipeline(&self, blend_mode: BlendMode) -> &wgpu::RenderPipeline {
        self.primitive_pipelines
            .get(&blend_mode)
            .unwrap_or(&self.pipeline)
    }

    fn image_pipeline_for(&self, blend_mode: BlendMode) -> &wgpu::RenderPipeline {
        self.image_pipelines
            .get(&blend_mode)
            .unwrap_or(&self.image_pipeline)
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
