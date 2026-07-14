use crate::gpu::pipeline::to_wgpu_color;
use crate::gpu::types::*;
use crate::types::BlendMode;
use wgpu::util::DeviceExt;

impl GpuRenderer {
    pub fn push_clip_path(&mut self, records: &[StrokePathRecord]) -> Result<usize, String> {
        if records.is_empty() {
            return Ok(self.current_clip_id);
        }
        self.write_viewport(self.texture_size.width, self.texture_size.height);
        let texture = self
            .device_context
            .device()
            .create_texture(&wgpu::TextureDescriptor {
                label: Some("gummy_canvas GPU clip path texture"),
                size: self.texture_size,
                mip_level_count: 1,
                sample_count: 1,
                dimension: wgpu::TextureDimension::D2,
                format: wgpu::TextureFormat::Rgba8Unorm,
                usage: wgpu::TextureUsages::RENDER_ATTACHMENT
                    | wgpu::TextureUsages::TEXTURE_BINDING,
                view_formats: &[],
            });
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let record_buffer =
            self.device_context
                .device()
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some("gummy_canvas GPU clip path records"),
                    contents: bytemuck::cast_slice(records),
                    usage: wgpu::BufferUsages::STORAGE,
                });
        let record_bind_group =
            self.device_context
                .device()
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("gummy_canvas GPU clip path records bind group"),
                    layout: &self.stroke_path_bind_group_layout,
                    entries: &[wgpu::BindGroupEntry {
                        binding: 0,
                        resource: record_buffer.as_entire_binding(),
                    }],
                });
        let parent_clip_id = self.current_clip_id;
        let mut encoder =
            self.device_context
                .device()
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("gummy_canvas GPU clip path encoder"),
                });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("gummy_canvas GPU clip path pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(to_wgpu_color(GpuColor {
                            r: 0,
                            g: 0,
                            b: 0,
                            a: 0,
                        })),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            let pipeline = self
                .path_fill_pipelines
                .get(&BlendMode::Blend)
                .ok_or_else(|| {
                    "GPU path-fill pipeline is unavailable for clip_path().".to_string()
                })?;
            pass.set_pipeline(pipeline);
            pass.set_bind_group(0, &self.viewport_bind_group, &[]);
            pass.set_bind_group(1, &self.clip_textures[parent_clip_id].bind_group, &[]);
            pass.set_bind_group(2, &record_bind_group, &[]);
            pass.draw(0..6, 0..1);
        }
        self.device_context.queue().submit([encoder.finish()]);

        let clip_uniform = ClipUniform {
            rect: [
                0.0,
                0.0,
                self.texture_size.width as f32,
                self.texture_size.height as f32,
            ],
            flags: [1.0, 0.0, 0.0, 0.0],
        };
        let uniform_buffer = self
            .device_context
            .device()
            .create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas GPU clip path uniform"),
                size: std::mem::size_of::<ClipUniform>() as u64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
        self.device_context.queue().write_buffer(
            &uniform_buffer,
            0,
            bytemuck::bytes_of(&clip_uniform),
        );
        let bind_group =
            self.device_context
                .device()
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("gummy_canvas GPU clip path bind group"),
                    layout: &self.clip_bind_group_layout,
                    entries: &[
                        wgpu::BindGroupEntry {
                            binding: 0,
                            resource: wgpu::BindingResource::TextureView(&view),
                        },
                        wgpu::BindGroupEntry {
                            binding: 1,
                            resource: wgpu::BindingResource::Sampler(&self.texture_sampler),
                        },
                        wgpu::BindGroupEntry {
                            binding: 2,
                            resource: uniform_buffer.as_entire_binding(),
                        },
                    ],
                });
        self.clip_stack.push(parent_clip_id);
        self.clip_textures.push(ClipTextureAsset {
            _texture: texture,
            _view: view,
            _uniform_buffer: uniform_buffer,
            bind_group,
        });
        self.current_clip_id = self.clip_textures.len() - 1;
        self.clip_generation = self.clip_generation.wrapping_add(1);
        Ok(self.current_clip_id)
    }

    pub fn pop_clip_path(&mut self) {
        let previous = self.clip_stack.pop().unwrap_or(0);
        if previous != self.current_clip_id {
            self.clip_generation = self.clip_generation.wrapping_add(1);
        }
        self.current_clip_id = previous;
    }

    pub fn upload_texture(
        &mut self,
        key: u64,
        width: usize,
        height: usize,
        pixels: &[u8],
    ) -> Result<Option<usize>, String> {
        let expected = width
            .checked_mul(height)
            .and_then(|value| value.checked_mul(4))
            .ok_or_else(|| "Texture dimensions are too large.".to_string())?;
        if pixels.len() != expected {
            return Err(format!(
                "Texture pixel buffer length must be {expected}, got {}.",
                pixels.len()
            ));
        }
        let size = wgpu::Extent3d {
            width: width.max(1) as u32,
            height: height.max(1) as u32,
            depth_or_array_layers: 1,
        };
        let texture = self
            .device_context
            .device()
            .create_texture(&wgpu::TextureDescriptor {
                label: Some("gummy_canvas image texture"),
                size,
                mip_level_count: 1,
                sample_count: 1,
                dimension: wgpu::TextureDimension::D2,
                format: wgpu::TextureFormat::Rgba8Unorm,
                usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
                view_formats: &[],
            });
        self.device_context.queue().write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            pixels,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(width.max(1) as u32 * 4),
                rows_per_image: Some(height.max(1) as u32),
            },
            size,
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let nearest_bind_group =
            self.device_context
                .device()
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("gummy_canvas nearest image texture bind group"),
                    layout: &self.image_bind_group_layout,
                    entries: &[
                        wgpu::BindGroupEntry {
                            binding: 0,
                            resource: wgpu::BindingResource::TextureView(&view),
                        },
                        wgpu::BindGroupEntry {
                            binding: 1,
                            resource: wgpu::BindingResource::Sampler(&self.texture_sampler),
                        },
                    ],
                });
        let linear_bind_group =
            self.device_context
                .device()
                .create_bind_group(&wgpu::BindGroupDescriptor {
                    label: Some("gummy_canvas linear image texture bind group"),
                    layout: &self.image_bind_group_layout,
                    entries: &[
                        wgpu::BindGroupEntry {
                            binding: 0,
                            resource: wgpu::BindingResource::TextureView(&view),
                        },
                        wgpu::BindGroupEntry {
                            binding: 1,
                            resource: wgpu::BindingResource::Sampler(&self.linear_texture_sampler),
                        },
                    ],
                });
        let replaced = self.textures.insert(
            key,
            TextureAsset {
                _texture: texture,
                _view: view,
                nearest_bind_group,
                linear_bind_group,
                bytes: expected,
            },
        );
        if replaced.is_some() {
            self.invalidate_retained_render_cache();
        }
        Ok(replaced.map(|asset| asset.bytes))
    }

    pub fn texture_is_pending(&self, key: u64) -> bool {
        self.commands.iter().any(|command| {
            matches!(
                command,
                DrawCommand::Image { key: command_key, .. }
                    | DrawCommand::ImageBatch { key: command_key, .. }
                    | DrawCommand::TexturedModel {
                        texture_key: command_key,
                        ..
                    } if *command_key == key
            )
        })
    }

    pub fn remove_texture(&mut self, key: u64) -> Option<usize> {
        let removed = self.textures.remove(&key)?;
        self.invalidate_retained_render_cache();
        Some(removed.bytes)
    }

    pub fn draw_image(
        &mut self,
        key: u64,
        vertices: [([f32; 2], [f32; 2], GpuColor); 6],
        linear: bool,
        blend_mode: BlendMode,
    ) {
        if self.textures.contains_key(&key) {
            self.commands.push(DrawCommand::Image {
                key,
                vertices,
                linear,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_image_batch(
        &mut self,
        key: u64,
        vertices: Vec<ImageVertex>,
        linear: bool,
        blend_mode: BlendMode,
    ) {
        if self.textures.contains_key(&key) && !vertices.is_empty() {
            self.commands.push(DrawCommand::ImageBatch {
                key,
                vertices,
                linear,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn upload_pixels(&mut self, pixels: &[u8]) -> Result<(), String> {
        let expected = self.texture_size.width as usize * self.texture_size.height as usize * 4;
        if pixels.len() != expected {
            return Err(format!(
                "Pixel buffer length must be {expected}, got {}.",
                pixels.len()
            ));
        }
        self.previous_render_commands.clear();
        self.device_context.queue().write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            pixels,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(self.texture_size.width * 4),
                rows_per_image: Some(self.texture_size.height),
            },
            self.texture_size,
        );
        Ok(())
    }

    pub(super) fn write_viewport(&self, width: u32, height: u32) {
        let viewport = ViewportUniform {
            size: [width.max(1) as f32, height.max(1) as f32],
            _padding: [0.0, 0.0],
        };
        self.device_context.queue().write_buffer(
            &self.viewport_buffer,
            0,
            bytemuck::bytes_of(&viewport),
        );
    }
}

pub(super) fn blend_mode_id(mode: BlendMode) -> u32 {
    match mode {
        BlendMode::Add => 1,
        BlendMode::Darkest => 2,
        BlendMode::Lightest => 3,
        BlendMode::Difference => 4,
        BlendMode::Exclusion => 5,
        BlendMode::Multiply => 6,
        BlendMode::Screen => 7,
        BlendMode::Blend | BlendMode::Replace => 0,
    }
}
