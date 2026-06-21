use std::collections::HashMap;
use std::sync::Arc;

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
use winit::window::WindowId;

use bytemuck::{Pod, Zeroable};

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct Vertex {
    pub(super) position: [f32; 2],
    pub(super) color: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ImageVertex {
    pub(super) position: [f32; 2],
    pub(super) uv: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ViewportUniform {
    pub(super) size: [f32; 2],
    pub(super) _padding: [f32; 2],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GpuColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl GpuColor {
    pub(super) fn as_float(self) -> [f32; 4] {
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

pub(super) struct TextureAsset {
    pub(super) _texture: wgpu::Texture,
    pub(super) _view: wgpu::TextureView,
    pub(super) nearest_bind_group: wgpu::BindGroup,
    pub(super) linear_bind_group: wgpu::BindGroup,
}

pub struct GpuRenderer {
    pub(super) instance: wgpu::Instance,
    pub(super) adapter: wgpu::Adapter,
    pub(super) device: Arc<wgpu::Device>,
    pub(super) queue: Arc<wgpu::Queue>,
    pub(super) texture: wgpu::Texture,
    pub(super) texture_view: wgpu::TextureView,
    pub(super) texture_size: wgpu::Extent3d,
    pub(super) pipeline: wgpu::RenderPipeline,
    pub(super) image_pipeline: wgpu::RenderPipeline,
    pub(super) image_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) texture_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) texture_surface_pipeline: Option<(wgpu::TextureFormat, wgpu::RenderPipeline)>,
    pub(super) texture_sampler: wgpu::Sampler,
    pub(super) linear_texture_sampler: wgpu::Sampler,
    pub(super) viewport_buffer: wgpu::Buffer,
    pub(super) viewport_bind_group: wgpu::BindGroup,
    pub(super) clear_color: GpuColor,
    pub(super) commands: Vec<DrawCommand>,
    pub(super) textures: HashMap<u64, TextureAsset>,
    #[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
    pub(super) surface: Option<GpuSurface>,
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub(super) struct GpuSurface {
    pub(super) window_id: WindowId,
    pub(super) surface: wgpu::Surface<'static>,
    pub(super) config: wgpu::SurfaceConfiguration,
}
