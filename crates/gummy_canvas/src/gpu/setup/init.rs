use std::collections::HashMap;
use std::sync::Arc;

use pollster::block_on;

use crate::gpu::setup::pipelines::create_pipeline_resources;
use crate::gpu::setup::resources::{
    checked_texture_size, create_default_clip_textures, create_depth_texture,
    create_linear_texture_sampler, create_model_uniform_bind_group, create_model_uniform_buffer,
    create_nearest_texture_sampler, create_offscreen_texture, create_pixel_prefix_bind_group,
    create_pixel_prefix_texture, create_text_resources, create_viewport_bind_group,
};
use crate::gpu::types::*;

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
        let pipelines = create_pipeline_resources(&device);
        let texture_sampler = create_nearest_texture_sampler(&device);
        let linear_texture_sampler = create_linear_texture_sampler(&device);
        let text_resources = create_text_resources(&device, &queue);
        let viewport_bind_group = create_viewport_bind_group(
            &device,
            &pipelines.viewport_bind_group_layout,
            &viewport_buffer,
        );
        let model_uniform_capacity = 16usize;
        let model_uniform_buffer = create_model_uniform_buffer(&device, model_uniform_capacity);
        let model_uniform_bind_group = create_model_uniform_bind_group(
            &device,
            &pipelines.model_bind_group_layout,
            &model_uniform_buffer,
        );
        let pixel_prefix_uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas pixel prefix uniform"),
            size: std::mem::size_of::<PixelPrefixUniform>() as u64,
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
            &pipelines.pixel_prefix_bind_group_layout,
            &pixel_prefix_texture_view,
            &texture_sampler,
            &pixel_prefix_uniform_buffer,
        );
        let clip_textures = create_default_clip_textures(
            &device,
            &queue,
            &pipelines.clip_bind_group_layout,
            &texture_sampler,
        );
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
            pipeline: pipelines.pipeline,
            primitive_pipelines: pipelines.primitive_pipelines,
            procedural_primitive_pipelines: pipelines.procedural_primitive_pipelines,
            procedural_erase_pipeline: pipelines.procedural_erase_pipeline,
            stroke_path_pipelines: pipelines.stroke_path_pipelines,
            stroke_path_erase_pipeline: pipelines.stroke_path_erase_pipeline,
            path_fill_pipelines: pipelines.path_fill_pipelines,
            path_fill_erase_pipeline: pipelines.path_fill_erase_pipeline,
            image_pipeline: pipelines.image_pipeline,
            image_pipelines: pipelines.image_pipelines,
            model_pipeline: pipelines.model_pipeline,
            model_wireframe_pipeline: pipelines.model_wireframe_pipeline,
            textured_model_pipeline: pipelines.textured_model_pipeline,
            pixel_prefix_pipeline: pipelines.pixel_prefix_pipeline,
            pixel_filter_pipeline: pipelines.pixel_filter_pipeline,
            blend_ellipse_pipeline: pipelines.blend_ellipse_pipeline,
            model_bind_group_layout: pipelines.model_bind_group_layout,
            stroke_path_bind_group_layout: pipelines.stroke_path_bind_group_layout,
            model_uniform_buffer,
            model_uniform_bind_group,
            model_uniform_capacity,
            pixel_prefix_bind_group_layout: pipelines.pixel_prefix_bind_group_layout,
            pixel_prefix_uniform_buffer,
            pixel_prefix_texture,
            pixel_prefix_texture_view,
            pixel_prefix_bind_group,
            image_bind_group_layout: pipelines.image_bind_group_layout,
            clip_bind_group_layout: pipelines.clip_bind_group_layout,
            texture_bind_group_layout: pipelines.present_texture_bind_group_layout,
            texture_surface_pipeline: None,
            texture_sampler,
            linear_texture_sampler,
            text_font_system: text_resources.font_system,
            text_swash_cache: text_resources.swash_cache,
            text_viewport: text_resources.viewport,
            text_atlas: text_resources.atlas,
            text_renderer: text_resources.renderer,
            text_buffers: HashMap::new(),
            viewport_buffer,
            viewport_bind_group,
            clip_textures,
            current_clip_id: 0,
            clip_stack: Vec::new(),
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
            image_staging: Vec::new(),
            primitive_vertex_buffer: None,
            primitive_vertex_capacity: 0,
            procedural_primitive_buffer: None,
            procedural_primitive_capacity: 0,
            stroke_path_buffer: None,
            stroke_path_record_capacity: 0,
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
