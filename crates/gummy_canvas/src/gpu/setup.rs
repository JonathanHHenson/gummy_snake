use std::collections::HashMap;
use std::sync::Arc;

use pollster::block_on;

use crate::gpu::pipeline::{
    clip_bind_group_layout, create_image_pipeline, create_pipeline, texture_bind_group_layout,
    viewport_bind_group_layout,
};
use crate::gpu::types::*;

fn checked_texture_size(
    width: usize,
    height: usize,
    max_texture_dimension_2d: u32,
) -> Result<wgpu::Extent3d, String> {
    let width = u32::try_from(width.max(1))
        .map_err(|_| format!("Canvas physical width {width} exceeds the GPU texture limit of {max_texture_dimension_2d}."))?;
    let height = u32::try_from(height.max(1))
        .map_err(|_| format!("Canvas physical height {height} exceeds the GPU texture limit of {max_texture_dimension_2d}."))?;
    if width > max_texture_dimension_2d {
        return Err(format!(
            "Canvas physical width {width} exceeds the GPU texture limit of {max_texture_dimension_2d}. Reduce create_canvas() width or pixel_density()."
        ));
    }
    if height > max_texture_dimension_2d {
        return Err(format!(
            "Canvas physical height {height} exceeds the GPU texture limit of {max_texture_dimension_2d}. Reduce create_canvas() height or pixel_density()."
        ));
    }
    Ok(wgpu::Extent3d {
        width,
        height,
        depth_or_array_layers: 1,
    })
}

fn create_offscreen_texture(device: &wgpu::Device, size: wgpu::Extent3d) -> wgpu::Texture {
    device.create_texture(&wgpu::TextureDescriptor {
        label: Some("gummy_canvas offscreen texture"),
        size,
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT
            | wgpu::TextureUsages::TEXTURE_BINDING
            | wgpu::TextureUsages::COPY_SRC
            | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    })
}

fn create_clip_texture(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    width: usize,
    height: usize,
    pixels: &[u8],
) -> wgpu::Texture {
    let size = wgpu::Extent3d {
        width: width.max(1) as u32,
        height: height.max(1) as u32,
        depth_or_array_layers: 1,
    };
    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("gummy_canvas clip mask texture"),
        size,
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    queue.write_texture(
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
    texture
}

fn create_clip_bind_group(
    device: &wgpu::Device,
    layout: &wgpu::BindGroupLayout,
    view: &wgpu::TextureView,
    sampler: &wgpu::Sampler,
    uniform_buffer: &wgpu::Buffer,
) -> wgpu::BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("gummy_canvas clip mask bind group"),
        layout,
        entries: &[
            wgpu::BindGroupEntry {
                binding: 0,
                resource: wgpu::BindingResource::TextureView(view),
            },
            wgpu::BindGroupEntry {
                binding: 1,
                resource: wgpu::BindingResource::Sampler(sampler),
            },
            wgpu::BindGroupEntry {
                binding: 2,
                resource: uniform_buffer.as_entire_binding(),
            },
        ],
    })
}

impl GpuRenderer {
    pub fn new(width: usize, height: usize) -> Result<Self, String> {
        let instance = wgpu::Instance::default();
        let adapter = block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .map_err(|err| format!("No supported GPU adapter is available for gummy_canvas: {err}"))?;
        let limits = adapter.limits();
        let (device, queue) = block_on(adapter.request_device(&wgpu::DeviceDescriptor {
            label: Some("gummy_canvas device"),
            required_features: wgpu::Features::empty(),
            required_limits: limits.clone(),
            memory_hints: wgpu::MemoryHints::Performance,
            trace: wgpu::Trace::Off,
        }))
        .map_err(|err| format!("Failed to create GPU device for gummy_canvas: {err}"))?;
        let device: Arc<wgpu::Device> = Arc::new(device);
        let queue: Arc<wgpu::Queue> = Arc::new(queue);
        let viewport_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas viewport uniform"),
            size: std::mem::size_of::<ViewportUniform>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let bind_group_layout = viewport_bind_group_layout(&device);
        let present_texture_bind_group_layout = texture_bind_group_layout(&device);
        let image_bind_group_layout = texture_bind_group_layout(&device);
        let clip_bind_group_layout = clip_bind_group_layout(&device);
        let texture_sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("gummy_canvas nearest texture sampler"),
            address_mode_u: wgpu::AddressMode::ClampToEdge,
            address_mode_v: wgpu::AddressMode::ClampToEdge,
            address_mode_w: wgpu::AddressMode::ClampToEdge,
            mag_filter: wgpu::FilterMode::Nearest,
            min_filter: wgpu::FilterMode::Nearest,
            mipmap_filter: wgpu::FilterMode::Nearest,
            ..wgpu::SamplerDescriptor::default()
        });
        let linear_texture_sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("gummy_canvas linear texture sampler"),
            address_mode_u: wgpu::AddressMode::ClampToEdge,
            address_mode_v: wgpu::AddressMode::ClampToEdge,
            address_mode_w: wgpu::AddressMode::ClampToEdge,
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            mipmap_filter: wgpu::FilterMode::Nearest,
            ..wgpu::SamplerDescriptor::default()
        });
        let viewport_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas viewport bind group"),
            layout: &bind_group_layout,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: viewport_buffer.as_entire_binding(),
            }],
        });
        let pipeline = create_pipeline(
            &device,
            &bind_group_layout,
            &clip_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let image_pipeline = create_image_pipeline(
            &device,
            &bind_group_layout,
            &image_bind_group_layout,
            &clip_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let texture_size = checked_texture_size(width, height, limits.max_texture_dimension_2d)?;
        let texture = create_offscreen_texture(&device, texture_size);
        let texture_view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let clip_texture = create_clip_texture(&device, &queue, 1, 1, &[255, 255, 255, 255]);
        let clip_texture_view = clip_texture.create_view(&wgpu::TextureViewDescriptor::default());
        let clip_uniform = ClipUniform {
            rect: [0.0, 0.0, 1.0, 1.0],
            flags: [0.0, 0.0, 0.0, 0.0],
        };
        let clip_uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas clip uniform"),
            size: std::mem::size_of::<ClipUniform>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        queue.write_buffer(&clip_uniform_buffer, 0, bytemuck::bytes_of(&clip_uniform));
        let clip_bind_group = create_clip_bind_group(
            &device,
            &clip_bind_group_layout,
            &clip_texture_view,
            &texture_sampler,
            &clip_uniform_buffer,
        );
        let clip_textures = vec![ClipTextureAsset {
            _texture: clip_texture,
            _view: clip_texture_view,
            _uniform_buffer: clip_uniform_buffer,
            bind_group: clip_bind_group,
        }];
        let mut renderer = Self {
            instance,
            adapter,
            device,
            queue,
            texture,
            texture_view,
            texture_size,
            pipeline,
            image_pipeline,
            image_bind_group_layout,
            clip_bind_group_layout,
            texture_bind_group_layout: present_texture_bind_group_layout,
            texture_surface_pipeline: None,
            texture_sampler,
            linear_texture_sampler,
            viewport_buffer,
            viewport_bind_group,
            clip_textures,
            current_clip_id: 0,
            clear_color: GpuColor {
                r: 0,
                g: 0,
                b: 0,
                a: 0,
            },
            commands: Vec::new(),
            textures: HashMap::new(),
            #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
            surface: None,
        };
        renderer.resize(width, height)?;
        renderer.clear_transparent();
        renderer.render();
        Ok(renderer)
    }

    pub fn resize(&mut self, width: usize, height: usize) -> Result<(), String> {
        let limits = self.device.limits();
        self.texture_size = checked_texture_size(width, height, limits.max_texture_dimension_2d)?;
        self.texture = create_offscreen_texture(&self.device, self.texture_size);
        self.texture_view = self
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
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

    pub fn is_available() -> bool {
        let instance = wgpu::Instance::default();
        block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .is_ok()
    }
}
