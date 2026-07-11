use super::common::fixed_function_blend_state;
use crate::gpu::shaders::{
    PATH_FILL_SHADER, PROCEDURAL_PRIMITIVE_SHADER, STROKE_PATH_SHADER, TRIANGLE_SHADER,
};
use crate::gpu::types::{PrimitiveInstance, Vertex};
use crate::types::BlendMode;

pub(in crate::gpu) fn create_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_primitive_pipeline(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        format,
        Some(wgpu::BlendState::ALPHA_BLENDING),
        wgpu::ColorWrites::ALL,
        "gummy_canvas primitive pipeline",
    )
}

pub(in crate::gpu) fn create_pipeline_for_blend_mode(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    mode: BlendMode,
) -> wgpu::RenderPipeline {
    create_primitive_pipeline(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        format,
        fixed_function_blend_state(mode),
        wgpu::ColorWrites::ALL,
        "gummy_canvas primitive blend pipeline",
    )
}

pub(in crate::gpu) fn create_procedural_primitive_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    mode: BlendMode,
) -> wgpu::RenderPipeline {
    create_procedural_primitive_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        format,
        fixed_function_blend_state(mode),
        "gummy_canvas procedural primitive pipeline",
    )
}

pub(in crate::gpu) fn create_procedural_erase_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_procedural_primitive_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        format,
        Some(erase_blend_state()),
        "gummy_canvas procedural erase primitive pipeline",
    )
}

pub(in crate::gpu) fn create_stroke_path_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    mode: BlendMode,
) -> wgpu::RenderPipeline {
    create_stroke_path_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        stroke_path_bind_group_layout,
        format,
        fixed_function_blend_state(mode),
        "gummy_canvas stroke path pipeline",
    )
}

pub(in crate::gpu) fn create_stroke_path_erase_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_stroke_path_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        stroke_path_bind_group_layout,
        format,
        Some(erase_blend_state()),
        "gummy_canvas stroke path erase pipeline",
    )
}

pub(in crate::gpu) fn create_path_fill_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    mode: BlendMode,
) -> wgpu::RenderPipeline {
    create_path_fill_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        stroke_path_bind_group_layout,
        format,
        fixed_function_blend_state(mode),
        "gummy_canvas path fill pipeline",
    )
}

pub(in crate::gpu) fn create_path_fill_erase_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_path_fill_pipeline_with_blend(
        device,
        viewport_bind_group_layout,
        clip_bind_group_layout,
        stroke_path_bind_group_layout,
        format,
        Some(erase_blend_state()),
        "gummy_canvas path fill erase pipeline",
    )
}

fn erase_blend_state() -> wgpu::BlendState {
    wgpu::BlendState {
        color: wgpu::BlendComponent {
            src_factor: wgpu::BlendFactor::One,
            dst_factor: wgpu::BlendFactor::Zero,
            operation: wgpu::BlendOperation::Add,
        },
        alpha: wgpu::BlendComponent {
            src_factor: wgpu::BlendFactor::Zero,
            dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
            operation: wgpu::BlendOperation::Add,
        },
    }
}

fn create_procedural_primitive_pipeline_with_blend(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    blend: Option<wgpu::BlendState>,
    label: &'static str,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas procedural primitive shader"),
        source: wgpu::ShaderSource::Wgsl(PROCEDURAL_PRIMITIVE_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas procedural primitive pipeline layout"),
        bind_group_layouts: &[viewport_bind_group_layout, clip_bind_group_layout],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some(label),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<PrimitiveInstance>() as u64,
                step_mode: wgpu::VertexStepMode::Instance,
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
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x2,
                        offset: (std::mem::size_of::<[f32; 2]>() * 2) as u64,
                        shader_location: 2,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x4,
                        offset: (std::mem::size_of::<[f32; 2]>() * 3) as u64,
                        shader_location: 3,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x4,
                        offset: (std::mem::size_of::<[f32; 2]>() * 3
                            + std::mem::size_of::<[f32; 4]>())
                            as u64,
                        shader_location: 4,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x4,
                        offset: (std::mem::size_of::<[f32; 2]>() * 3
                            + std::mem::size_of::<[f32; 4]>() * 2)
                            as u64,
                        shader_location: 5,
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
                blend,
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
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth24Plus,
            depth_write_enabled: false,
            depth_compare: wgpu::CompareFunction::Always,
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

fn create_stroke_path_pipeline_with_blend(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    blend: Option<wgpu::BlendState>,
    label: &'static str,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas stroke path shader"),
        source: wgpu::ShaderSource::Wgsl(STROKE_PATH_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas stroke path pipeline layout"),
        bind_group_layouts: &[
            viewport_bind_group_layout,
            clip_bind_group_layout,
            stroke_path_bind_group_layout,
        ],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some(label),
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
                blend,
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
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth24Plus,
            depth_write_enabled: false,
            depth_compare: wgpu::CompareFunction::Always,
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

fn create_path_fill_pipeline_with_blend(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    stroke_path_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    blend: Option<wgpu::BlendState>,
    label: &'static str,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas path fill shader"),
        source: wgpu::ShaderSource::Wgsl(PATH_FILL_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas path fill pipeline layout"),
        bind_group_layouts: &[
            viewport_bind_group_layout,
            clip_bind_group_layout,
            stroke_path_bind_group_layout,
        ],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some(label),
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
                blend,
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
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth24Plus,
            depth_write_enabled: false,
            depth_compare: wgpu::CompareFunction::Always,
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}

fn create_primitive_pipeline(
    device: &wgpu::Device,
    viewport_bind_group_layout: &wgpu::BindGroupLayout,
    clip_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
    blend: Option<wgpu::BlendState>,
    write_mask: wgpu::ColorWrites,
    label: &'static str,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("gummy_canvas primitive shader"),
        source: wgpu::ShaderSource::Wgsl(TRIANGLE_SHADER.into()),
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas primitive pipeline layout"),
        bind_group_layouts: &[viewport_bind_group_layout, clip_bind_group_layout],
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some(label),
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
                blend,
                write_mask,
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
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth24Plus,
            depth_write_enabled: false,
            depth_compare: wgpu::CompareFunction::Always,
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}
