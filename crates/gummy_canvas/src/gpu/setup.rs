use std::collections::HashMap;
use std::sync::Arc;

use pollster::block_on;

use crate::gpu::pipeline::{
    clip_bind_group_layout, create_blend_ellipse_pipeline, create_erase_pipeline,
    create_image_pipeline, create_image_pipeline_for_blend_mode, create_model_pipeline,
    create_pipeline, create_pipeline_for_blend_mode, create_pixel_prefix_pipeline,
    create_procedural_primitive_pipeline, create_textured_model_pipeline, model_bind_group_layout,
    pixel_prefix_bind_group_layout, texture_bind_group_layout, viewport_bind_group_layout,
};
use crate::gpu::types::*;
use crate::BlendMode;

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

fn create_depth_texture(device: &wgpu::Device, size: wgpu::Extent3d) -> wgpu::Texture {
    device.create_texture(&wgpu::TextureDescriptor {
        label: Some("gummy_canvas 3D depth texture"),
        size,
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Depth24Plus,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        view_formats: &[],
    })
}

fn create_pixel_prefix_texture(device: &wgpu::Device, size: wgpu::Extent3d) -> wgpu::Texture {
    device.create_texture(&wgpu::TextureDescriptor {
        label: Some("gummy_canvas pixel prefix target texture"),
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

fn create_pixel_prefix_bind_group(
    device: &wgpu::Device,
    layout: &wgpu::BindGroupLayout,
    view: &wgpu::TextureView,
    sampler: &wgpu::Sampler,
    uniform_buffer: &wgpu::Buffer,
) -> wgpu::BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("gummy_canvas pixel prefix bind group"),
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

fn create_model_uniform_buffer(device: &wgpu::Device, capacity: usize) -> wgpu::Buffer {
    device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("gummy_canvas model uniforms"),
        size: (capacity.max(1) * std::mem::size_of::<ModelUniform>()) as u64,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    })
}

fn create_model_uniform_bind_group(
    device: &wgpu::Device,
    layout: &wgpu::BindGroupLayout,
    buffer: &wgpu::Buffer,
) -> wgpu::BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("gummy_canvas model uniform bind group"),
        layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: buffer.as_entire_binding(),
        }],
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
        let model_bind_group_layout = model_bind_group_layout(&device);
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
        let text_font_system = glyphon::FontSystem::new();
        let text_swash_cache = glyphon::SwashCache::new();
        let text_cache = glyphon::Cache::new(&device);
        let text_viewport = glyphon::Viewport::new(&device, &text_cache);
        let mut text_atlas = glyphon::TextAtlas::new(
            &device,
            &queue,
            &text_cache,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let text_renderer = glyphon::TextRenderer::new(
            &mut text_atlas,
            &device,
            wgpu::MultisampleState::default(),
            None,
        );
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
        let primitive_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
            .into_iter()
            .map(|mode| {
                (
                    mode,
                    create_pipeline_for_blend_mode(
                        &device,
                        &bind_group_layout,
                        &clip_bind_group_layout,
                        wgpu::TextureFormat::Rgba8Unorm,
                        mode,
                    ),
                )
            })
            .collect();
        let procedural_primitive_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
            .into_iter()
            .map(|mode| {
                (
                    mode,
                    create_procedural_primitive_pipeline(
                        &device,
                        &bind_group_layout,
                        &clip_bind_group_layout,
                        wgpu::TextureFormat::Rgba8Unorm,
                        mode,
                    ),
                )
            })
            .collect();
        let erase_pipeline = create_erase_pipeline(
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
        let image_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
            .into_iter()
            .map(|mode| {
                (
                    mode,
                    create_image_pipeline_for_blend_mode(
                        &device,
                        &bind_group_layout,
                        &image_bind_group_layout,
                        &clip_bind_group_layout,
                        wgpu::TextureFormat::Rgba8Unorm,
                        mode,
                    ),
                )
            })
            .collect();
        let model_pipeline = create_model_pipeline(
            &device,
            &model_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let textured_model_pipeline = create_textured_model_pipeline(
            &device,
            &model_bind_group_layout,
            &image_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let model_uniform_capacity = 16usize;
        let model_uniform_buffer = create_model_uniform_buffer(&device, model_uniform_capacity);
        let model_uniform_bind_group = create_model_uniform_bind_group(
            &device,
            &model_bind_group_layout,
            &model_uniform_buffer,
        );
        let pixel_prefix_bind_group_layout = pixel_prefix_bind_group_layout(&device);
        let pixel_prefix_pipeline = create_pixel_prefix_pipeline(
            &device,
            &pixel_prefix_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let blend_ellipse_pipeline = create_blend_ellipse_pipeline(
            &device,
            &pixel_prefix_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let pixel_prefix_uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas pixel prefix uniform"),
            size: std::mem::size_of::<PixelPrefixUniform>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let blend_ellipse_uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas blend ellipse uniform"),
            size: std::mem::size_of::<BlendEllipseUniform>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let texture_size = checked_texture_size(width, height, limits.max_texture_dimension_2d)?;
        let texture = create_offscreen_texture(&device, texture_size);
        let texture_view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let depth_texture = create_depth_texture(&device, texture_size);
        let depth_texture_view = depth_texture.create_view(&wgpu::TextureViewDescriptor::default());
        let pixel_prefix_texture = create_pixel_prefix_texture(&device, texture_size);
        let pixel_prefix_texture_view =
            pixel_prefix_texture.create_view(&wgpu::TextureViewDescriptor::default());
        let pixel_prefix_bind_group = create_pixel_prefix_bind_group(
            &device,
            &pixel_prefix_bind_group_layout,
            &pixel_prefix_texture_view,
            &texture_sampler,
            &pixel_prefix_uniform_buffer,
        );
        let blend_ellipse_bind_group = create_pixel_prefix_bind_group(
            &device,
            &pixel_prefix_bind_group_layout,
            &pixel_prefix_texture_view,
            &texture_sampler,
            &blend_ellipse_uniform_buffer,
        );
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
            depth_texture,
            depth_texture_view,
            texture_size,
            pipeline,
            primitive_pipelines,
            procedural_primitive_pipelines,
            erase_pipeline,
            image_pipeline,
            image_pipelines,
            model_pipeline,
            textured_model_pipeline,
            pixel_prefix_pipeline,
            blend_ellipse_pipeline,
            model_bind_group_layout,
            model_uniform_buffer,
            model_uniform_bind_group,
            model_uniform_capacity,
            pixel_prefix_bind_group_layout,
            pixel_prefix_uniform_buffer,
            blend_ellipse_uniform_buffer,
            pixel_prefix_texture,
            pixel_prefix_texture_view,
            pixel_prefix_bind_group,
            blend_ellipse_bind_group,
            image_bind_group_layout,
            clip_bind_group_layout,
            texture_bind_group_layout: present_texture_bind_group_layout,
            texture_surface_pipeline: None,
            texture_sampler,
            linear_texture_sampler,
            text_font_system,
            text_swash_cache,
            text_viewport,
            text_atlas,
            text_renderer,
            text_buffers: HashMap::new(),
            viewport_buffer,
            viewport_bind_group,
            clip_textures,
            current_clip_id: 0,
            clip_generation: 0,
            previous_render_clip_generation: 0,
            clear_color: GpuColor {
                r: 0,
                g: 0,
                b: 0,
                a: 0,
            },
            commands: Vec::new(),
            previous_render_commands: Vec::new(),
            textures: HashMap::new(),
            model_meshes: HashMap::new(),
            primitive_staging: Vec::new(),
            erase_staging: Vec::new(),
            image_staging: Vec::new(),
            primitive_vertex_buffer: None,
            primitive_vertex_capacity: 0,
            procedural_primitive_buffer: None,
            procedural_primitive_capacity: 0,
            erase_vertex_buffer: None,
            erase_vertex_capacity: 0,
            image_vertex_buffer: None,
            image_vertex_capacity: 0,
            vertex_buffer_allocations: 0,
            vertex_uploads: 0,
            uploaded_vertex_bytes: 0,
            primitive_batches: 0,
            image_batches: 0,
            encode_time_ms: 0.0,
            retained_batch_cache_hits: 0,
            retained_batch_cache_misses: 0,
            retained_batch_reused_bytes: 0,
            retained_batch_cache_evictions: 0,
            #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
            surface: None,
        };
        renderer.resize(width, height)?;
        renderer.draw_text(
            ".".to_string(),
            0.0,
            0.0,
            16.0,
            16.0,
            12.0,
            12.0,
            GpuColor {
                r: 255,
                g: 255,
                b: 255,
                a: 0,
            },
        );
        renderer.render();
        renderer.begin_frame();
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
        self.depth_texture = create_depth_texture(&self.device, self.texture_size);
        self.depth_texture_view = self
            .depth_texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        self.pixel_prefix_texture = create_pixel_prefix_texture(&self.device, self.texture_size);
        self.pixel_prefix_texture_view = self
            .pixel_prefix_texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        self.text_buffers.clear();
        self.previous_render_commands.clear();
        self.pixel_prefix_bind_group = create_pixel_prefix_bind_group(
            &self.device,
            &self.pixel_prefix_bind_group_layout,
            &self.pixel_prefix_texture_view,
            &self.texture_sampler,
            &self.pixel_prefix_uniform_buffer,
        );
        self.blend_ellipse_bind_group = create_pixel_prefix_bind_group(
            &self.device,
            &self.pixel_prefix_bind_group_layout,
            &self.pixel_prefix_texture_view,
            &self.texture_sampler,
            &self.blend_ellipse_uniform_buffer,
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
