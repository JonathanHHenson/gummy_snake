use std::sync::Arc;

use bytemuck::{Pod, Zeroable};

mod draw_command;
#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub(super) use super::renderer_state::GpuSurface;
pub(super) use super::renderer_state::{ClipTextureAsset, GpuModelMesh, GpuRenderer, TextureAsset};
pub(super) use draw_command::DestinationBlendShape;
pub use draw_command::DrawCommand;

pub(super) const STROKE_PATH_RECORD_ALIGNMENT: usize = 16;
pub type StrokePathRecord = [f32; 4];

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct Vertex {
    pub(super) position: [f32; 2],
    pub(super) color: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub(crate) struct ImageVertex {
    pub(crate) position: [f32; 2],
    pub(crate) uv: [f32; 2],
    pub(crate) tint: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub struct PrimitiveInstance {
    pub p0: [f32; 2],
    pub p1: [f32; 2],
    pub p2: [f32; 2],
    pub bounds: [f32; 4],
    pub color: [f32; 4],
    pub params: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod, Zeroable)]
pub struct ModelVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Pod, Zeroable)]
pub struct ModelUniform {
    pub model: [[f32; 4]; 4],
    pub view_projection: [[f32; 4]; 4],
    pub base_color: [f32; 4],
    pub emissive_color: [f32; 4],
    pub specular_shininess: [f32; 4],
    pub ambient_color: [f32; 4],
    pub directional_color: [f32; 4],
    pub directional_direction: [f32; 4],
    pub point_color: [f32; 4],
    pub point_position: [f32; 4],
    pub flags: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ViewportUniform {
    pub(super) size: [f32; 2],
    pub(super) _padding: [f32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct ClipUniform {
    pub(super) rect: [f32; 4],
    pub(super) flags: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct PixelPrefixUniform {
    pub(super) byte_limit: u32,
    pub(super) stride: u32,
    pub(super) red_delta: i32,
    pub(super) green_delta: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct DestinationBlendUniform {
    pub(super) center_extent: [f32; 4],
    pub(super) color: [f32; 4],
    pub(super) mode: u32,
    pub(super) shape: u32,
    pub(super) _padding: [u32; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub(super) struct PixelFilterUniform {
    pub(super) mode: u32,
    pub(super) value: f32,
    pub(super) _padding: [u32; 2],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GpuColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl GpuColor {
    pub(crate) fn as_float(self) -> [f32; 4] {
        [
            self.r as f32 / 255.0,
            self.g as f32 / 255.0,
            self.b as f32 / 255.0,
            self.a as f32 / 255.0,
        ]
    }
}

#[derive(Clone, Debug)]
pub struct RetainedTriangleVertices {
    pub key: u64,
    pub vertices: Arc<Vec<([f32; 2], GpuColor)>>,
}

impl PartialEq for RetainedTriangleVertices {
    fn eq(&self, other: &Self) -> bool {
        self.key == other.key
    }
}

#[derive(Clone, Debug)]
pub struct RetainedPrimitiveInstances {
    pub key: u64,
    pub instances: Arc<Vec<PrimitiveInstance>>,
}

impl PartialEq for RetainedPrimitiveInstances {
    fn eq(&self, other: &Self) -> bool {
        self.key == other.key
    }
}
