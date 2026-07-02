use crate::gpu::shaders::{MODEL_SHADER, TEXTURED_MODEL_SHADER};
use crate::gpu::types::ModelVertex;

pub(in crate::gpu) fn create_model_pipeline(
    device: &wgpu::Device,
    model_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_model_pipeline_inner(
        device,
        model_bind_group_layout,
        &[],
        format,
        MODEL_SHADER,
        "gummy_canvas model shader",
        "gummy_canvas model pipeline",
        wgpu::PrimitiveTopology::TriangleList,
        Some(wgpu::Face::Back),
        true,
        wgpu::CompareFunction::Less,
    )
}

pub(in crate::gpu) fn create_model_wireframe_pipeline(
    device: &wgpu::Device,
    model_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_model_pipeline_inner(
        device,
        model_bind_group_layout,
        &[],
        format,
        MODEL_SHADER,
        "gummy_canvas model wireframe shader",
        "gummy_canvas model wireframe pipeline",
        wgpu::PrimitiveTopology::LineList,
        None,
        false,
        wgpu::CompareFunction::LessEqual,
    )
}

pub(in crate::gpu) fn create_textured_model_pipeline(
    device: &wgpu::Device,
    model_bind_group_layout: &wgpu::BindGroupLayout,
    image_bind_group_layout: &wgpu::BindGroupLayout,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    create_model_pipeline_inner(
        device,
        model_bind_group_layout,
        &[image_bind_group_layout],
        format,
        TEXTURED_MODEL_SHADER,
        "gummy_canvas textured model shader",
        "gummy_canvas textured model pipeline",
        wgpu::PrimitiveTopology::TriangleList,
        Some(wgpu::Face::Back),
        true,
        wgpu::CompareFunction::Less,
    )
}

fn create_model_pipeline_inner(
    device: &wgpu::Device,
    model_bind_group_layout: &wgpu::BindGroupLayout,
    additional_bind_group_layouts: &[&wgpu::BindGroupLayout],
    format: wgpu::TextureFormat,
    shader_source: &str,
    shader_label: &'static str,
    pipeline_label: &'static str,
    topology: wgpu::PrimitiveTopology,
    cull_mode: Option<wgpu::Face>,
    depth_write_enabled: bool,
    depth_compare: wgpu::CompareFunction,
) -> wgpu::RenderPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some(shader_label),
        source: wgpu::ShaderSource::Wgsl(shader_source.into()),
    });
    let mut bind_group_layouts = vec![model_bind_group_layout];
    bind_group_layouts.extend_from_slice(additional_bind_group_layouts);
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("gummy_canvas model pipeline layout"),
        bind_group_layouts: &bind_group_layouts,
        push_constant_ranges: &[],
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some(pipeline_label),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<ModelVertex>() as u64,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &[
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x3,
                        offset: 0,
                        shader_location: 0,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x3,
                        offset: std::mem::size_of::<[f32; 3]>() as u64,
                        shader_location: 1,
                    },
                    wgpu::VertexAttribute {
                        format: wgpu::VertexFormat::Float32x2,
                        offset: (std::mem::size_of::<[f32; 3]>() * 2) as u64,
                        shader_location: 2,
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
            topology,
            strip_index_format: None,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode,
            polygon_mode: wgpu::PolygonMode::Fill,
            unclipped_depth: false,
            conservative: false,
        },
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth24Plus,
            depth_write_enabled,
            depth_compare,
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    })
}
