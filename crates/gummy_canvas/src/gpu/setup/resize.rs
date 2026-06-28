use crate::gpu::setup::resources::{
    checked_texture_size, create_depth_texture, create_offscreen_texture,
    create_pixel_prefix_bind_group, create_pixel_prefix_texture,
};
use crate::gpu::types::*;

impl GpuRenderer {
    pub fn resize(&mut self, width: usize, height: usize) -> Result<(), String> {
        let limits = self.device.limits();
        self.texture_size = checked_texture_size(width, height, limits.max_texture_dimension_2d)?;
        self.texture = create_offscreen_texture(&self.device, self.texture_size);
        self.texture_view = self
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        self.depth_texture = create_depth_texture(&self.device, self.texture_size);
        self.depth_texture_view = self
            .depth_texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        self.pixel_prefix_texture = create_pixel_prefix_texture(&self.device, self.texture_size);
        self.pixel_prefix_texture_view = self
            .pixel_prefix_texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        self.text_buffers.clear();
        self.invalidate_retained_render_cache();
        self.pixel_prefix_bind_group = create_pixel_prefix_bind_group(
            &self.device,
            &self.pixel_prefix_bind_group_layout,
            &self.pixel_prefix_texture_view,
            &self.texture_sampler,
            &self.pixel_prefix_uniform_buffer,
        );
        let viewport = ViewportUniform {
            size: [
                self.texture_size.width as f32,
                self.texture_size.height as f32,
            ],
            _padding: [0.0, 0.0],
        };
        self.queue
            .write_buffer(&self.viewport_buffer, 0, bytemuck::bytes_of(&viewport));
        Ok(())
    }
}
