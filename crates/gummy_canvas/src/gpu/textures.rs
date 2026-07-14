use crate::gpu::pipeline::to_wgpu_color;
use crate::gpu::renderer_state::{
    PersistentAtlasEntry, PersistentAtlasPage, PersistentAtlasPlacement,
};
use crate::gpu::types::*;
use crate::types::BlendMode;
use wgpu::util::DeviceExt;

pub(super) fn padded_atlas_pixels(pixels: &[u8], width: usize, height: usize) -> Vec<u8> {
    let padded_width = width + 2;
    let padded_height = height + 2;
    let mut padded = vec![0; padded_width * padded_height * 4];
    for padded_y in 0..padded_height {
        let source_y = padded_y.saturating_sub(1).min(height - 1);
        for padded_x in 0..padded_width {
            let source_x = padded_x.saturating_sub(1).min(width - 1);
            let source_offset = (source_y * width + source_x) * 4;
            let destination_offset = (padded_y * padded_width + padded_x) * 4;
            padded[destination_offset..destination_offset + 4]
                .copy_from_slice(&pixels[source_offset..source_offset + 4]);
        }
    }
    padded
}

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

    pub fn persistent_image_atlas_resident_bytes(&self) -> usize {
        self.persistent_image_atlas
            .pages
            .iter()
            .map(|page| page.width * page.height * 4)
            .sum()
    }

    pub fn place_persistent_atlas_image(
        &mut self,
        key: u64,
        version: u64,
        width: usize,
        height: usize,
        pixels: &[u8],
    ) -> Result<Option<PersistentAtlasPlacement>, String> {
        if width == 0 || height == 0 {
            return Ok(None);
        }
        let expected = width
            .checked_mul(height)
            .and_then(|value| value.checked_mul(4))
            .ok_or_else(|| "Image atlas dimensions are too large.".to_owned())?;
        if pixels.len() != expected {
            return Err(format!(
                "Image atlas source length must be {expected}, got {}.",
                pixels.len()
            ));
        }
        let padded_width = width
            .checked_add(2)
            .ok_or_else(|| "Image atlas width is too large.".to_owned())?;
        let padded_height = height
            .checked_add(2)
            .ok_or_else(|| "Image atlas height is too large.".to_owned())?;
        let page_size = self.persistent_image_atlas.page_size;
        if padded_width > page_size || padded_height > page_size {
            return Ok(None);
        }
        self.persistent_image_atlas.clock = self.persistent_image_atlas.clock.wrapping_add(1);
        let clock = self.persistent_image_atlas.clock;
        if let Some(entry) = self.persistent_image_atlas.entries.get_mut(&key) {
            if entry.width == width && entry.height == height {
                let page = &self.persistent_image_atlas.pages[entry.page_index];
                let uploaded = entry.version != version;
                let placement = PersistentAtlasPlacement {
                    texture_key: page.texture_key,
                    x: entry.x,
                    y: entry.y,
                    page_width: page.width,
                    page_height: page.height,
                    uploaded,
                };
                entry.last_used = clock;
                if !uploaded {
                    return Ok(Some(placement));
                }
                entry.version = version;
                let texture_key = page.texture_key;
                let x = entry.x;
                let y = entry.y;
                let padded_pixels = padded_atlas_pixels(pixels, width, height);
                self.upload_texture_region(
                    texture_key,
                    &padded_pixels,
                    padded_width,
                    padded_height,
                    x - 1,
                    y - 1,
                )?;
                return Ok(Some(placement));
            }
            self.persistent_image_atlas.entries.remove(&key);
        }

        let mut selected_page = None;
        for (index, page) in self.persistent_image_atlas.pages.iter().enumerate() {
            let fits_current_row = page.next_x + padded_width <= page.width
                && page.next_y + padded_height <= page.height;
            let fits_new_row = page.next_y + page.row_height + padded_height <= page.height;
            if fits_current_row || fits_new_row {
                selected_page = Some(index);
                break;
            }
        }
        if selected_page.is_none()
            && self.persistent_image_atlas.pages.len() < self.persistent_image_atlas.max_pages
        {
            let texture_key = self.persistent_image_atlas.next_texture_key;
            self.persistent_image_atlas.next_texture_key = texture_key.wrapping_add(1);
            let zero_pixels = vec![0; page_size * page_size * 4];
            self.upload_texture(texture_key, page_size, page_size, &zero_pixels)?;
            self.persistent_image_atlas.pages.push(PersistentAtlasPage {
                texture_key,
                width: page_size,
                height: page_size,
                next_x: 0,
                next_y: 0,
                row_height: 0,
            });
            selected_page = Some(self.persistent_image_atlas.pages.len() - 1);
        }
        let Some(page_index) = selected_page else {
            return Ok(None);
        };
        let (texture_key, x, y, page_width, page_height) = {
            let page = &mut self.persistent_image_atlas.pages[page_index];
            if page.next_x + padded_width > page.width {
                page.next_x = 0;
                page.next_y += page.row_height;
                page.row_height = 0;
            }
            let x = page.next_x + 1;
            let y = page.next_y + 1;
            page.next_x += padded_width;
            page.row_height = page.row_height.max(padded_height);
            (page.texture_key, x, y, page.width, page.height)
        };
        let padded_pixels = padded_atlas_pixels(pixels, width, height);
        self.upload_texture_region(
            texture_key,
            &padded_pixels,
            padded_width,
            padded_height,
            x - 1,
            y - 1,
        )?;
        self.persistent_image_atlas.entries.insert(
            key,
            PersistentAtlasEntry {
                version,
                page_index,
                x,
                y,
                width,
                height,
                last_used: clock,
            },
        );
        Ok(Some(PersistentAtlasPlacement {
            texture_key,
            x,
            y,
            page_width,
            page_height,
            uploaded: true,
        }))
    }

    fn upload_texture_region(
        &self,
        texture_key: u64,
        pixels: &[u8],
        width: usize,
        height: usize,
        x: usize,
        y: usize,
    ) -> Result<(), String> {
        let asset = self
            .textures
            .get(&texture_key)
            .ok_or_else(|| "Persistent atlas page texture is unavailable.".to_owned())?;
        self.device_context.queue().write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &asset._texture,
                mip_level: 0,
                origin: wgpu::Origin3d {
                    x: x as u32,
                    y: y as u32,
                    z: 0,
                },
                aspect: wgpu::TextureAspect::All,
            },
            pixels,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(width as u32 * 4),
                rows_per_image: Some(height as u32),
            },
            wgpu::Extent3d {
                width: width as u32,
                height: height as u32,
                depth_or_array_layers: 1,
            },
        );
        Ok(())
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

    pub fn upload_pixel_region(
        &mut self,
        pixels: &[u8],
        source_width: usize,
        source_height: usize,
        source_x: usize,
        source_y: usize,
        destination_x: usize,
        destination_y: usize,
        copy_width: usize,
        copy_height: usize,
    ) -> Result<(), String> {
        let expected = source_width
            .checked_mul(source_height)
            .and_then(|value| value.checked_mul(4))
            .ok_or_else(|| "Pixel region dimensions are too large.".to_owned())?;
        if pixels.len() != expected {
            return Err(format!(
                "Pixel region buffer length must be {expected}, got {}.",
                pixels.len()
            ));
        }
        if source_x + copy_width > source_width
            || source_y + copy_height > source_height
            || destination_x + copy_width > self.texture_size.width as usize
            || destination_y + copy_height > self.texture_size.height as usize
        {
            return Err("Pixel region copy exceeds source or destination bounds.".to_owned());
        }
        if copy_width == 0 || copy_height == 0 {
            return Ok(());
        }
        self.previous_render_commands.clear();
        let source_offset = (source_y * source_width + source_x) * 4;
        self.device_context.queue().write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d {
                    x: destination_x as u32,
                    y: destination_y as u32,
                    z: 0,
                },
                aspect: wgpu::TextureAspect::All,
            },
            &pixels[source_offset..],
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(source_width as u32 * 4),
                rows_per_image: Some(source_height as u32),
            },
            wgpu::Extent3d {
                width: copy_width as u32,
                height: copy_height as u32,
                depth_or_array_layers: 1,
            },
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
