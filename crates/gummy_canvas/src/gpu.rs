use bytemuck::{Pod, Zeroable};
use pollster::block_on;
use std::collections::HashMap;
use std::sync::Arc;
#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
use winit::window::{Window, WindowId};

const SHADER: &str = r#"
struct Viewport {
    size: vec2<f32>,
    _padding: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> viewport: Viewport;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) color: vec4<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    let ndc_x = input.position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - input.position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.color = input.color;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    return input.color;
}
"#;

const TEXTURE_SHADER: &str = r#"
struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
    );
    var uvs = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(1.0, 0.0),
    );
    var output: VertexOutput;
    output.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    output.uv = uvs[vertex_index];
    return output;
}

@group(0) @binding(0)
var offscreen_texture: texture_2d<f32>;

@group(0) @binding(1)
var offscreen_sampler: sampler;

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    return textureSample(offscreen_texture, offscreen_sampler, input.uv);
}
"#;

const IMAGE_SHADER: &str = r#"
struct Viewport {
    size: vec2<f32>,
    _padding: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> viewport: Viewport;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) uv: vec2<f32>,
};

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    let ndc_x = input.position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - input.position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.uv = input.uv;
    return output;
}

@group(1) @binding(0)
var image_texture: texture_2d<f32>;

@group(1) @binding(1)
var image_sampler: sampler;

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    return textureSample(image_texture, image_sampler, input.uv);
}
"#;

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod, Zeroable)]
struct Vertex {
    position: [f32; 2],
    color: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod, Zeroable)]
struct ImageVertex {
    position: [f32; 2],
    uv: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod, Zeroable)]
struct ViewportUniform {
    size: [f32; 2],
    _padding: [f32; 2],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GpuColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl GpuColor {
    fn as_float(self) -> [f32; 4] {
        [
            self.r as f32 / 255.0,
            self.g as f32 / 255.0,
            self.b as f32 / 255.0,
            self.a as f32 / 255.0,
        ]
    }
}

#[derive(Clone, Debug)]
pub enum DrawCommand {
    Clear(GpuColor),
    Triangles(Vec<([f32; 2], GpuColor)>),
    Image {
        key: u64,
        vertices: [([f32; 2], [f32; 2]); 6],
        linear: bool,
    },
}

struct TextureAsset {
    _texture: wgpu::Texture,
    _view: wgpu::TextureView,
    nearest_bind_group: wgpu::BindGroup,
    linear_bind_group: wgpu::BindGroup,
}

pub struct GpuRenderer {
    instance: wgpu::Instance,
    adapter: wgpu::Adapter,
    device: Arc<wgpu::Device>,
    queue: Arc<wgpu::Queue>,
    texture: wgpu::Texture,
    texture_view: wgpu::TextureView,
    texture_size: wgpu::Extent3d,
    pipeline: wgpu::RenderPipeline,
    image_pipeline: wgpu::RenderPipeline,
    image_bind_group_layout: wgpu::BindGroupLayout,
    texture_bind_group_layout: wgpu::BindGroupLayout,
    texture_surface_pipeline: Option<(wgpu::TextureFormat, wgpu::RenderPipeline)>,
    texture_sampler: wgpu::Sampler,
    linear_texture_sampler: wgpu::Sampler,
    viewport_buffer: wgpu::Buffer,
    viewport_bind_group: wgpu::BindGroup,
    clear_color: GpuColor,
    commands: Vec<DrawCommand>,
    textures: HashMap<u64, TextureAsset>,
    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    surface: Option<GpuSurface>,
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
struct GpuSurface {
    window_id: WindowId,
    surface: wgpu::Surface<'static>,
    config: wgpu::SurfaceConfiguration,
}

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
        let pipeline =
            create_pipeline(&device, &bind_group_layout, wgpu::TextureFormat::Rgba8Unorm);
        let image_pipeline = create_image_pipeline(
            &device,
            &bind_group_layout,
            &image_bind_group_layout,
            wgpu::TextureFormat::Rgba8Unorm,
        );
        let texture_size = checked_texture_size(width, height, limits.max_texture_dimension_2d)?;
        let texture = create_offscreen_texture(&device, texture_size);
        let texture_view = texture.create_view(&wgpu::TextureViewDescriptor::default());
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
            texture_bind_group_layout: present_texture_bind_group_layout,
            texture_surface_pipeline: None,
            texture_sampler,
            linear_texture_sampler,
            viewport_buffer,
            viewport_bind_group,
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

    pub fn begin_frame(&mut self) {
        self.commands.clear();
    }

    pub fn set_clear_color(&mut self, color: GpuColor) {
        self.clear_color = color;
        self.commands.push(DrawCommand::Clear(color));
    }

    pub fn clear_transparent(&mut self) {
        self.set_clear_color(GpuColor {
            r: 0,
            g: 0,
            b: 0,
            a: 0,
        });
    }

    pub fn draw_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::Triangles(vertices));
        }
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

    pub fn draw_image(&mut self, key: u64, vertices: [([f32; 2], [f32; 2]); 6], linear: bool) {
        if self.textures.contains_key(&key) {
            self.commands.push(DrawCommand::Image {
                key,
                vertices,
                linear,
            });
        }
    }

    pub fn render(&mut self) {
        self.write_viewport(self.texture_size.width, self.texture_size.height);
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas render encoder"),
            });
        self.encode_commands(&mut encoder, &self.texture_view, &self.pipeline);
        self.queue.submit([encoder.finish()]);
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
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

    pub fn read_pixels(&self) -> Result<Vec<u8>, String> {
        let bytes_per_pixel = 4usize;
        let unpadded_bytes_per_row = self.texture_size.width as usize * bytes_per_pixel;
        let padded_bytes_per_row = align_to(
            unpadded_bytes_per_row,
            wgpu::COPY_BYTES_PER_ROW_ALIGNMENT as usize,
        );
        let output_size = padded_bytes_per_row * self.texture_size.height as usize;
        let output = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas readback buffer"),
            size: output_size as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("gummy_canvas readback encoder"),
            });
        encoder.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &self.texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &output,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(padded_bytes_per_row as u32),
                    rows_per_image: Some(self.texture_size.height),
                },
            },
            self.texture_size,
        );
        self.queue.submit([encoder.finish()]);
        let slice = output.slice(..);
        let (sender, receiver) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |result| {
            let _ = sender.send(result);
        });
        let _ = self.device.poll(wgpu::PollType::Wait);
        receiver
            .recv()
            .map_err(|err| format!("Failed to receive GPU readback status: {err}"))?
            .map_err(|err| format!("Failed to map GPU readback buffer: {err}"))?;
        let mapped = slice.get_mapped_range();
        let mut pixels = vec![0; unpadded_bytes_per_row * self.texture_size.height as usize];
        for y in 0..self.texture_size.height as usize {
            let src_start = y * padded_bytes_per_row;
            let dst_start = y * unpadded_bytes_per_row;
            pixels[dst_start..dst_start + unpadded_bytes_per_row]
                .copy_from_slice(&mapped[src_start..src_start + unpadded_bytes_per_row]);
        }
        drop(mapped);
        output.unmap();
        Ok(pixels)
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

    fn write_viewport(&self, width: u32, height: u32) {
        let viewport = ViewportUniform {
            size: [width.max(1) as f32, height.max(1) as f32],
            _padding: [0.0, 0.0],
        };
        self.queue
            .write_buffer(&self.viewport_buffer, 0, bytemuck::bytes_of(&viewport));
    }

    fn encode_commands(
        &self,
        encoder: &mut wgpu::CommandEncoder,
        view: &wgpu::TextureView,
        pipeline: &wgpu::RenderPipeline,
    ) {
        let clear = self
            .commands
            .iter()
            .rev()
            .find_map(|command| match command {
                DrawCommand::Clear(color) => Some(*color),
                DrawCommand::Triangles(_) => None,
                DrawCommand::Image { .. } => None,
            });
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas primitive render pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: clear
                        .map(to_wgpu_color)
                        .map(wgpu::LoadOp::Clear)
                        .unwrap_or(wgpu::LoadOp::Load),
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        pass.set_pipeline(pipeline);
        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
        let mut skip_until_last_clear = clear.is_some();
        let mut batched_vertices = Vec::new();
        for command in &self.commands {
            match command {
                DrawCommand::Clear(color) => {
                    if skip_until_last_clear && Some(*color) == clear {
                        skip_until_last_clear = false;
                    }
                }
                DrawCommand::Triangles(vertices) => {
                    if skip_until_last_clear {
                        continue;
                    }
                    batched_vertices.extend(vertices.iter().map(|(position, color)| Vertex {
                        position: *position,
                        color: color.as_float(),
                    }));
                }
                DrawCommand::Image {
                    key,
                    vertices,
                    linear,
                } => {
                    if skip_until_last_clear {
                        continue;
                    }
                    if !batched_vertices.is_empty() {
                        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                            label: Some("gummy_canvas primitive vertices"),
                            size: (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64,
                            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                            mapped_at_creation: false,
                        });
                        self.queue.write_buffer(
                            &buffer,
                            0,
                            bytemuck::cast_slice(&batched_vertices),
                        );
                        pass.set_pipeline(pipeline);
                        pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                        pass.set_vertex_buffer(0, buffer.slice(..));
                        pass.draw(0..batched_vertices.len() as u32, 0..1);
                        batched_vertices.clear();
                    }
                    let Some(texture) = self.textures.get(key) else {
                        continue;
                    };
                    let image_vertices: Vec<ImageVertex> = vertices
                        .iter()
                        .map(|(position, uv)| ImageVertex {
                            position: *position,
                            uv: *uv,
                        })
                        .collect();
                    let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                        label: Some("gummy_canvas image vertices"),
                        size: (image_vertices.len() * std::mem::size_of::<ImageVertex>()) as u64,
                        usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                        mapped_at_creation: false,
                    });
                    self.queue
                        .write_buffer(&buffer, 0, bytemuck::cast_slice(&image_vertices));
                    pass.set_pipeline(&self.image_pipeline);
                    pass.set_bind_group(0, &self.viewport_bind_group, &[]);
                    let bind_group = if *linear {
                        &texture.linear_bind_group
                    } else {
                        &texture.nearest_bind_group
                    };
                    pass.set_bind_group(1, bind_group, &[]);
                    pass.set_vertex_buffer(0, buffer.slice(..));
                    pass.draw(0..image_vertices.len() as u32, 0..1);
                }
            }
        }
        if !batched_vertices.is_empty() {
            let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas primitive vertices"),
                size: (batched_vertices.len() * std::mem::size_of::<Vertex>()) as u64,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            self.queue
                .write_buffer(&buffer, 0, bytemuck::cast_slice(&batched_vertices));
            pass.set_vertex_buffer(0, buffer.slice(..));
            pass.draw(0..batched_vertices.len() as u32, 0..1);
        }
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
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

fn to_wgpu_color(color: GpuColor) -> wgpu::Color {
    wgpu::Color {
        r: color.r as f64 / 255.0,
        g: color.g as f64 / 255.0,
        b: color.b as f64 / 255.0,
        a: color.a as f64 / 255.0,
    }
}

fn viewport_bind_group_layout(device: &wgpu::Device) -> wgpu::BindGroupLayout {
    device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: Some("gummy_canvas viewport bind group layout"),
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::VERTEX,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }],
    })
}

fn texture_bind_group_layout(device: &wgpu::Device) -> wgpu::BindGroupLayout {
    device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: Some("gummy_canvas texture bind group layout"),
        entries: &[
            wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                    view_dimension: wgpu::TextureViewDimension::D2,
                    multisampled: false,
                },
                count: None,
            },
            wgpu::BindGroupLayoutEntry {
                binding: 1,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                count: None,
            },
        ],
    })
}

fn create_pipeline(
    device: &wgpu::Device,
    bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas primitive shader"),
        source: wgpu::ShaderSource::Wgsl(SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas primitive pipeline layout"),
        bind_group_layouts: &[bind_group_layout],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("gummy_canvas primitive pipeline"),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<Vertex>() as u64,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &[
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x2,
                        offset: 0,
                        shader_location: 0,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x4,
                        offset: std::mem::size_of::<[f32; 2]>() as u64,
                        shader_location: 1,
                    },
                ],
            }],
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some("fs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            targets: &[Some(wgpu::ColorTargetState {
                format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            strip_index_format: None,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode: None,
            polygon_mode: wgpu::PolygonMode::Fill,
            unclipped_depth: false,
            conservative: false,
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

fn create_texture_pipeline(
    device: &wgpu::Device,
    bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas texture present shader"),
        source: wgpu::ShaderSource::Wgsl(TEXTURE_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas texture present pipeline layout"),
        bind_group_layouts: &[bind_group_layout],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("gummy_canvas texture present pipeline"),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[],
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some("fs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            targets: &[Some(wgpu::ColorTargetState {
                format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            ..wgpu::PrimitiveState::default()
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

fn create_image_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    image_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas image shader"),
        source: wgpu::ShaderSource::Wgsl(IMAGE_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas image pipeline layout"),
        bind_group_layouts: &[viewport_bind_group_layout, image_bind_group_layout],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("gummy_canvas image pipeline"),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<ImageVertex>() as u64,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &[
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x2,
                        offset: 0,
                        shader_location: 0,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x2,
                        offset: std::mem::size_of::<[f32; 2]>() as u64,
                        shader_location: 1,
                    },
                ],
            }],
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some("fs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            targets: &[Some(wgpu::ColorTargetState {
                format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            strip_index_format: None,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode: None,
            polygon_mode: wgpu::PolygonMode::Fill,
            unclipped_depth: false,
            conservative: false,
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
fn surface_config(
    capabilities: &wgpu::SurfaceCapabilities,
    width: u32,
    height: u32,
) -> Option<wgpu::SurfaceConfiguration> {
    let format = preferred_surface_format(&capabilities.formats)?;
    let present_mode = [
        wgpu::PresentMode::Immediate,
        wgpu::PresentMode::Mailbox,
        wgpu::PresentMode::Fifo,
    ]
    .into_iter()
    .find(|mode| capabilities.present_modes.contains(mode))
    .or_else(|| capabilities.present_modes.first().copied())?;
    let alpha_mode = capabilities
        .alpha_modes
        .iter()
        .copied()
        .find(|mode| *mode == wgpu::CompositeAlphaMode::Opaque)
        .or_else(|| capabilities.alpha_modes.first().copied())
        .unwrap_or(wgpu::CompositeAlphaMode::Auto);

    Some(wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format,
        width,
        height,
        present_mode,
        desired_maximum_frame_latency: 1,
        alpha_mode,
        view_formats: vec![],
    })
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
fn preferred_surface_format(formats: &[wgpu::TextureFormat]) -> Option<wgpu::TextureFormat> {
    [
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Bgra8Unorm,
    ]
    .into_iter()
    .find(|format| formats.contains(format))
    .or_else(|| formats.iter().copied().find(|format| !format.is_srgb()))
    .or_else(|| formats.first().copied())
}

fn align_to(value: usize, alignment: usize) -> usize {
    value.div_ceil(alignment) * alignment
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preferred_surface_format_uses_rgba_unorm_when_available() {
        let format = preferred_surface_format(&[
            wgpu::TextureFormat::Bgra8UnormSrgb,
            wgpu::TextureFormat::Rgba8Unorm,
            wgpu::TextureFormat::Bgra8Unorm,
        ]);

        assert_eq!(format, Some(wgpu::TextureFormat::Rgba8Unorm));
    }

    #[test]
    fn preferred_surface_format_falls_back_to_bgra_unorm() {
        let format = preferred_surface_format(&[
            wgpu::TextureFormat::Bgra8UnormSrgb,
            wgpu::TextureFormat::Bgra8Unorm,
        ]);

        assert_eq!(format, Some(wgpu::TextureFormat::Bgra8Unorm));
    }

    #[test]
    fn preferred_surface_format_avoids_srgb_when_possible() {
        let format = preferred_surface_format(&[
            wgpu::TextureFormat::Bgra8UnormSrgb,
            wgpu::TextureFormat::Rgba16Float,
        ]);

        assert_eq!(format, Some(wgpu::TextureFormat::Rgba16Float));
    }

    #[test]
    fn preferred_surface_format_uses_first_format_as_last_resort() {
        let format = preferred_surface_format(&[
            wgpu::TextureFormat::Bgra8UnormSrgb,
            wgpu::TextureFormat::Rgba8UnormSrgb,
        ]);

        assert_eq!(format, Some(wgpu::TextureFormat::Bgra8UnormSrgb));
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    #[test]
    fn surface_config_prefers_immediate_present_mode_when_available() {
        let capabilities = wgpu::SurfaceCapabilities {
            formats: vec![wgpu::TextureFormat::Rgba8Unorm],
            present_modes: vec![wgpu::PresentMode::Fifo, wgpu::PresentMode::Immediate],
            alpha_modes: vec![wgpu::CompositeAlphaMode::Opaque],
            usages: wgpu::TextureUsages::RENDER_ATTACHMENT,
        };

        let config = surface_config(&capabilities, 640, 480).unwrap();

        assert_eq!(config.present_mode, wgpu::PresentMode::Immediate);
        assert_eq!(config.desired_maximum_frame_latency, 1);
    }

    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    #[test]
    fn surface_config_falls_back_to_fifo_present_mode() {
        let capabilities = wgpu::SurfaceCapabilities {
            formats: vec![wgpu::TextureFormat::Rgba8Unorm],
            present_modes: vec![wgpu::PresentMode::Fifo],
            alpha_modes: vec![wgpu::CompositeAlphaMode::Opaque],
            usages: wgpu::TextureUsages::RENDER_ATTACHMENT,
        };

        let config = surface_config(&capabilities, 640, 480).unwrap();

        assert_eq!(config.present_mode, wgpu::PresentMode::Fifo);
    }
}
