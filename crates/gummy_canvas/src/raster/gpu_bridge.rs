use crate::{gpu, Rgba};

use super::types::Point;

pub(crate) fn gpu_color(color: Rgba) -> gpu::GpuColor {
    gpu::GpuColor {
        r: color.r,
        g: color.g,
        b: color.b,
        a: color.a,
    }
}

pub(crate) fn push_triangle(
    vertices: &mut Vec<([f32; 2], gpu::GpuColor)>,
    a: Point,
    b: Point,
    c: Point,
    color: Rgba,
) {
    let color = gpu_color(color);
    vertices.push((point_to_gpu(a), color));
    vertices.push((point_to_gpu(b), color));
    vertices.push((point_to_gpu(c), color));
}

fn point_to_gpu(point: Point) -> [f32; 2] {
    [point.0 as f32, point.1 as f32]
}
