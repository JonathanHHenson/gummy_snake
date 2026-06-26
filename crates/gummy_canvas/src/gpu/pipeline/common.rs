use crate::gpu::types::GpuColor;
use crate::BlendMode;

pub(in crate::gpu) fn to_wgpu_color(color: GpuColor) -> wgpu::Color {
    wgpu::Color {
        r: color.r as f64 / 255.0,
        g: color.g as f64 / 255.0,
        b: color.b as f64 / 255.0,
        a: color.a as f64 / 255.0,
    }
}

pub(in crate::gpu) fn fixed_function_blend_state(mode: BlendMode) -> Option<wgpu::BlendState> {
    match mode {
        BlendMode::Blend => Some(wgpu::BlendState::ALPHA_BLENDING),
        BlendMode::Add => Some(wgpu::BlendState {
            color: wgpu::BlendComponent {
                src_factor: wgpu::BlendFactor::SrcAlpha,
                dst_factor: wgpu::BlendFactor::One,
                operation: wgpu::BlendOperation::Add,
            },
            alpha: wgpu::BlendComponent {
                src_factor: wgpu::BlendFactor::One,
                dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                operation: wgpu::BlendOperation::Add,
            },
        }),
        BlendMode::Replace => None,
        _ => Some(wgpu::BlendState::ALPHA_BLENDING),
    }
}

pub(in crate::gpu) fn align_to(value: usize, alignment: usize) -> usize {
    value.div_ceil(alignment) * alignment
}
