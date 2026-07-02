use crate::{gpu, Rgba};

pub(crate) fn gpu_color(color: Rgba) -> gpu::GpuColor {
    gpu::GpuColor {
        r: color.r,
        g: color.g,
        b: color.b,
        a: color.a,
    }
}
