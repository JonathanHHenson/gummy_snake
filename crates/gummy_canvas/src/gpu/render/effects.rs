use crate::gpu::types::*;
use crate::types::BlendMode;
use wgpu::util::DeviceExt;

impl GpuRenderer {
    pub(super) fn encode_blend_ellipse_pass(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        mode: BlendMode,
    ) {
        let uniform_buffer = self
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("gummy_canvas blend ellipse pass uniform"),
                contents: bytemuck::bytes_of(&BlendEllipseUniform {
                    center_radius: [cx, cy, rx.max(0.0001), ry.max(0.0001)],
                    color: color.as_float(),
                    mode: crate::gpu::textures::blend_mode_id(mode),
                    _padding: [0; 7],
                }),
                usage: wgpu::BufferUsages::UNIFORM,
            });
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas blend ellipse pass bind group"),
            layout: &self.pixel_prefix_bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&self.pixel_prefix_texture_view),
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
        pass.set_bind_group(0, &bind_group, &[]);
        pass.set_scissor_rect(x, y, width, height);
        pass.draw(0..6, 0..1);
    }

    pub(super) fn encode_pixel_filter_pass(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        mode: u32,
        value: f32,
    ) {
        self.queue.write_buffer(
            &self.pixel_prefix_uniform_buffer,
            0,
            bytemuck::bytes_of(&PixelFilterUniform {
                mode,
                value,
                _padding: [0; 2],
            }),
        );
        if self.texture_size.width == 0 || self.texture_size.height == 0 {
            return;
        }
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
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas ordered pixel filter pass"),
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
        pass.set_pipeline(&self.pixel_filter_pipeline);
        pass.set_bind_group(0, &self.pixel_prefix_bind_group, &[]);
        pass.draw(0..6, 0..1);
    }

    pub(super) fn encode_pixel_prefix_pass(
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
        let total_pixels = self
            .texture_size
            .width
            .saturating_mul(self.texture_size.height);
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
}
