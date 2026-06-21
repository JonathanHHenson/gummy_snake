use super::types::*;

impl GpuRenderer {
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

    pub fn draw_image(&mut self, key: u64, vertices: [([f32; 2], [f32; 2]); 6], linear: bool) {
        if self.textures.contains_key(&key) {
            self.commands.push(DrawCommand::Image {
                key,
                vertices,
                linear,
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
