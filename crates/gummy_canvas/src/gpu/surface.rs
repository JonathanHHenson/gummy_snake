use std::sync::Arc;

use winit::window::Window;

use super::pipeline::{create_texture_pipeline, surface_config};
use super::types::*;

impl GpuRenderer {
    pub fn present_texture_to_window(
        &mut self,
        window: Arc<Window>,
        width: u32,
        height: u32,
    ) -> Result<(), String> {
        let width = width.max(1);
        let height = height.max(1);
        self.ensure_surface(Arc::clone(&window), width, height)?;
        let surface = self
            .surface
            .as_ref()
            .ok_or_else(|| "GPU surface was not initialized.".to_string())?;
        let frame = match surface.surface.get_current_texture() {
            Ok(frame) => frame,
            Err(wgpu::SurfaceError::Lost | wgpu::SurfaceError::Outdated) => {
                self.reconfigure_surface(width, height)?;
                self.surface
                    .as_ref()
                    .ok_or_else(|| "GPU surface was not initialized.".to_string())?
                    .surface
                    .get_current_texture()
                    .map_err(|err| format!("Failed to acquire GPU surface texture: {err}"))?
            }
            Err(wgpu::SurfaceError::Timeout) => return Ok(()),
            Err(err) => return Err(format!("Failed to acquire GPU surface texture: {err}")),
        };
        let view = frame
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        let format = self.surface.as_ref().expect("surface exists").config.format;
        let pipeline = self.texture_surface_pipeline(format);
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas offscreen texture bind group"),
            layout: &self.texture_bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&self.texture_view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&self.texture_sampler),
                },
            ],
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas texture present encoder"),
            });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("gummy_canvas texture present pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color::BLACK),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            pass.set_pipeline(&pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.draw(0..6, 0..1);
        }
        window.pre_present_notify();
        self.queue.submit([encoder.finish()]);
        frame.present();
        Ok(())
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub fn drop_surface(&mut self) {
        self.surface = None;
    }

    fn ensure_surface(
        &mut self,
        window: Arc<Window>,
        width: u32,
        height: u32,
    ) -> Result<(), String> {
        let recreate = self
            .surface
            .as_ref()
            .map(|surface| surface.window_id != window.id())
            .unwrap_or(true);
        if recreate {
            let surface = self
                .instance
                .create_surface(Arc::clone(&window))
                .map_err(|err| format!("Failed to create GPU window surface: {err}"))?;
            let capabilities = surface.get_capabilities(&self.adapter);
            let config =
                surface_config(&capabilities, width.max(1), height.max(1)).ok_or_else(|| {
                    "The selected GPU adapter does not support the native window surface."
                        .to_string()
                })?;
            surface.configure(&self.device, &config);
            self.surface = Some(GpuSurface {
                window_id: window.id(),
                surface,
                config,
            });
            return Ok(());
        }
        let needs_reconfigure = self
            .surface
            .as_ref()
            .map(|surface| surface.config.width != width || surface.config.height != height)
            .unwrap_or(false);
        if needs_reconfigure {
            self.reconfigure_surface(width, height)?;
        }
        Ok(())
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    fn reconfigure_surface(&mut self, width: u32, height: u32) -> Result<(), String> {
        let surface = self
            .surface
            .as_mut()
            .ok_or_else(|| "GPU surface was not initialized.".to_string())?;
        surface.config.width = width.max(1);
        surface.config.height = height.max(1);
        surface.surface.configure(&self.device, &surface.config);
        Ok(())
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    fn texture_surface_pipeline(&mut self, format: wgpu::TextureFormat) -> wgpu::RenderPipeline {
        let needs_pipeline = self
            .texture_surface_pipeline
            .as_ref()
            .map(|(existing_format, _)| *existing_format != format)
            .unwrap_or(true);
        if needs_pipeline {
            self.texture_surface_pipeline = Some((
                format,
                create_texture_pipeline(&self.device, &self.texture_bind_group_layout, format),
            ));
        }
        self.texture_surface_pipeline
            .as_ref()
            .expect("texture surface pipeline exists")
            .1
            .clone()
    }
}
