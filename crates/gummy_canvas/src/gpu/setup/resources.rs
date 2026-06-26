use crate::gpu::types::{ClipTextureAsset, ClipUniform, ModelUniform};

pub(super) fn checked_texture_size(
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

pub(super) fn create_offscreen_texture(
    device: &wgpu::Device,
    size: wgpu::Extent3d,
) -> wgpu::Texture {
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

pub(super) fn create_depth_texture(device: &wgpu::Device, size: wgpu::Extent3d) -> wgpu::Texture {
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

pub(super) fn create_pixel_prefix_texture(
    device: &wgpu::Device,
    size: wgpu::Extent3d,
) -> wgpu::Texture {
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

pub(super) fn create_pixel_prefix_bind_group(
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

pub(super) fn create_clip_texture(
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

pub(super) fn create_clip_bind_group(
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

pub(super) fn create_model_uniform_buffer(device: &wgpu::Device, capacity: usize) -> wgpu::Buffer {
    device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("gummy_canvas model uniforms"),
        size: (capacity.max(1) * std::mem::size_of::<ModelUniform>()) as u64,
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    })
}

pub(super) fn create_model_uniform_bind_group(
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

pub(super) struct TextResources {
    pub(super) font_system: glyphon::FontSystem,
    pub(super) swash_cache: glyphon::SwashCache,
    pub(super) viewport: glyphon::Viewport,
    pub(super) atlas: glyphon::TextAtlas,
    pub(super) renderer: glyphon::TextRenderer,
}

pub(super) fn create_nearest_texture_sampler(device: &wgpu::Device) -> wgpu::Sampler {
    device.create_sampler(&wgpu::SamplerDescriptor {
        label: Some("gummy_canvas nearest texture sampler"),
        address_mode_u: wgpu::AddressMode::ClampToEdge,
        address_mode_v: wgpu::AddressMode::ClampToEdge,
        address_mode_w: wgpu::AddressMode::ClampToEdge,
        mag_filter: wgpu::FilterMode::Nearest,
        min_filter: wgpu::FilterMode::Nearest,
        mipmap_filter: wgpu::FilterMode::Nearest,
        ..wgpu::SamplerDescriptor::default()
    })
}

pub(super) fn create_linear_texture_sampler(device: &wgpu::Device) -> wgpu::Sampler {
    device.create_sampler(&wgpu::SamplerDescriptor {
        label: Some("gummy_canvas linear texture sampler"),
        address_mode_u: wgpu::AddressMode::ClampToEdge,
        address_mode_v: wgpu::AddressMode::ClampToEdge,
        address_mode_w: wgpu::AddressMode::ClampToEdge,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::FilterMode::Nearest,
        ..wgpu::SamplerDescriptor::default()
    })
}

pub(super) fn create_text_resources(device: &wgpu::Device, queue: &wgpu::Queue) -> TextResources {
    let font_system = glyphon::FontSystem::new();
    let swash_cache = glyphon::SwashCache::new();
    let cache = glyphon::Cache::new(device);
    let viewport = glyphon::Viewport::new(device, &cache);
    let mut atlas = glyphon::TextAtlas::new(device, queue, &cache, wgpu::TextureFormat::Rgba8Unorm);
    let renderer =
        glyphon::TextRenderer::new(&mut atlas, device, wgpu::MultisampleState::default(), None);
    TextResources {
        font_system,
        swash_cache,
        viewport,
        atlas,
        renderer,
    }
}

pub(super) fn create_viewport_bind_group(
    device: &wgpu::Device,
    layout: &wgpu::BindGroupLayout,
    viewport_buffer: &wgpu::Buffer,
) -> wgpu::BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("gummy_canvas viewport bind group"),
        layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: viewport_buffer.as_entire_binding(),
        }],
    })
}

pub(super) fn create_default_clip_textures(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    layout: &wgpu::BindGroupLayout,
    sampler: &wgpu::Sampler,
) -> Vec<ClipTextureAsset> {
    let clip_texture = create_clip_texture(device, queue, 1, 1, &[255, 255, 255, 255]);
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
        device,
        layout,
        &clip_texture_view,
        sampler,
        &clip_uniform_buffer,
    );
    vec![ClipTextureAsset {
        _texture: clip_texture,
        _view: clip_texture_view,
        _uniform_buffer: clip_uniform_buffer,
        bind_group: clip_bind_group,
    }]
}
