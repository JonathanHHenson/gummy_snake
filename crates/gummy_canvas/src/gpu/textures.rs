use crate::gpu::types::*;

impl GpuRenderer {
    pub fn set_clip_mask(
        &mut self,
        x: usize,
        y: usize,
        width: usize,
        height: usize,
        mask_rgba: &[u8],
    ) -> usize {
        let width = width.max(1);
        let height = height.max(1);
        let size = wgpu::Extent3d {
            width: width as u32,
            height: height as u32,
            depth_or_array_layers: 1,
        };
        let texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("gummy_canvas clip mask texture"),
            size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        self.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            mask_rgba,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(width as u32 * 4),
                rows_per_image: Some(height as u32),
            },
            size,
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let clip_uniform = ClipUniform {
            rect: [x as f32, y as f32, width as f32, height as f32],
            flags: [1.0, 0.0, 0.0, 0.0],
        };
        let uniform_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas clip uniform"),
            size: std::mem::size_of::<ClipUniform>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        self.queue
            .write_buffer(&uniform_buffer, 0, bytemuck::bytes_of(&clip_uniform));
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas clip mask bind group"),
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
        self.clip_textures.push(ClipTextureAsset {
            _texture: texture,
            _view: view,
            _uniform_buffer: uniform_buffer,
            bind_group,
        });
        self.current_clip_id = self.clip_textures.len() - 1;
        self.current_clip_id
    }

    pub fn clear_clip_mask(&mut self) {
        self.current_clip_id = 0;
    }

    pub fn upload_texture(
        &mut self,
        key: u64,
        width: usize,
        height: usize,
        pixels: &[u8],
    ) -> Result<(), String> {
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
        let texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("gummy_canvas image texture"),
            size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        self.queue.write_texture(
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
        let nearest_bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
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
        let linear_bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
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
        self.textures.insert(
            key,
            TextureAsset {
                _texture: texture,
                _view: view,
                nearest_bind_group,
                linear_bind_group,
            },
        );
        Ok(())
    }

    pub fn draw_image(
        &mut self,
        key: u64,
        vertices: [([f32; 2], [f32; 2], GpuColor); 6],
        linear: bool,
        blend_mode: crate::BlendMode,
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

    pub fn apply_pixel_prefix_mutation(
        &mut self,
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
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas pixel prefix encoder"),
            });
        encoder.copy_texture_to_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyTextureInfo {
                texture: &self.pixel_prefix_texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            self.texture_size,
        );
        let source_bind_group = self.create_region_effect_bind_group(
            &self.pixel_prefix_texture_view,
            &self.pixel_prefix_uniform_buffer,
            "gummy_canvas pixel prefix source bind group",
        );
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("gummy_canvas pixel prefix pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &self.texture_view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            pass.set_pipeline(&self.pixel_prefix_pipeline);
            pass.set_bind_group(0, &source_bind_group, &[]);
            pass.draw(0..6, 0..1);
        }
        self.queue.submit([encoder.finish()]);
    }

    pub(super) fn create_region_effect_bind_group(
        &self,
        source_view: &wgpu::TextureView,
        uniform_buffer: &wgpu::Buffer,
        label: &'static str,
    ) -> wgpu::BindGroup {
        self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some(label),
            layout: &self.pixel_prefix_bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(source_view),
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
        })
    }

    pub fn upload_pixels(&mut self, pixels: &[u8]) -> Result<(), String> {
        let expected = self.texture_size.width as usize * self.texture_size.height as usize * 4;
        if pixels.len() != expected {
            return Err(format!(
                "Pixel buffer length must be {expected}, got {}.",
                pixels.len()
            ));
        }
        self.queue.write_texture(
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
        self.queue
            .write_buffer(&self.viewport_buffer, 0, bytemuck::bytes_of(&viewport));
    }
}

pub(super) fn blend_mode_id(mode: crate::BlendMode) -> u32 {
    match mode {
        crate::BlendMode::Add => 1,
        crate::BlendMode::Darkest => 2,
        crate::BlendMode::Lightest => 3,
        crate::BlendMode::Difference => 4,
        crate::BlendMode::Exclusion => 5,
        crate::BlendMode::Multiply => 6,
        crate::BlendMode::Screen => 7,
        crate::BlendMode::Blend | crate::BlendMode::Replace => 0,
    }
}
