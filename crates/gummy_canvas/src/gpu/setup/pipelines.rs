use std::collections::HashMap;

use crate::gpu::pipeline::{
    clip_bind_group_layout, create_blend_ellipse_pipeline, create_erase_pipeline,
    create_image_pipeline, create_image_pipeline_for_blend_mode, create_model_pipeline,
    create_pipeline, create_pipeline_for_blend_mode, create_pixel_prefix_pipeline,
    create_procedural_primitive_pipeline, create_textured_model_pipeline, model_bind_group_layout,
    pixel_prefix_bind_group_layout, texture_bind_group_layout, viewport_bind_group_layout,
};
use crate::BlendMode;

pub(super) struct PipelineResources {
    pub(super) viewport_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) present_texture_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) image_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) clip_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) model_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) pixel_prefix_bind_group_layout: wgpu::BindGroupLayout,
    pub(super) pipeline: wgpu::RenderPipeline,
    pub(super) primitive_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) procedural_primitive_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) erase_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipeline: wgpu::RenderPipeline,
    pub(super) image_pipelines: HashMap<BlendMode, wgpu::RenderPipeline>,
    pub(super) model_pipeline: wgpu::RenderPipeline,
    pub(super) textured_model_pipeline: wgpu::RenderPipeline,
    pub(super) pixel_prefix_pipeline: wgpu::RenderPipeline,
    pub(super) blend_ellipse_pipeline: wgpu::RenderPipeline,
}

pub(super) fn create_pipeline_resources(device: &wgpu::Device) -> PipelineResources {
    let viewport_bind_group_layout = viewport_bind_group_layout(device);
    let present_texture_bind_group_layout = texture_bind_group_layout(device);
    let image_bind_group_layout = texture_bind_group_layout(device);
    let clip_bind_group_layout = clip_bind_group_layout(device);
    let model_bind_group_layout = model_bind_group_layout(device);
    let pipeline = create_pipeline(
        device,
        &viewport_bind_group_layout,
        &clip_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let primitive_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
        .into_iter()
        .map(|mode| {
            (
                mode,
                create_pipeline_for_blend_mode(
                    device,
                    &viewport_bind_group_layout,
                    &clip_bind_group_layout,
                    wgpu::TextureFormat::Rgba8Unorm,
                    mode,
                ),
            )
        })
        .collect();
    let procedural_primitive_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
        .into_iter()
        .map(|mode| {
            (
                mode,
                create_procedural_primitive_pipeline(
                    device,
                    &viewport_bind_group_layout,
                    &clip_bind_group_layout,
                    wgpu::TextureFormat::Rgba8Unorm,
                    mode,
                ),
            )
        })
        .collect();
    let erase_pipeline = create_erase_pipeline(
        device,
        &viewport_bind_group_layout,
        &clip_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let image_pipeline = create_image_pipeline(
        device,
        &viewport_bind_group_layout,
        &image_bind_group_layout,
        &clip_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let image_pipelines = [BlendMode::Blend, BlendMode::Add, BlendMode::Replace]
        .into_iter()
        .map(|mode| {
            (
                mode,
                create_image_pipeline_for_blend_mode(
                    device,
                    &viewport_bind_group_layout,
                    &image_bind_group_layout,
                    &clip_bind_group_layout,
                    wgpu::TextureFormat::Rgba8Unorm,
                    mode,
                ),
            )
        })
        .collect();
    let model_pipeline = create_model_pipeline(
        device,
        &model_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let textured_model_pipeline = create_textured_model_pipeline(
        device,
        &model_bind_group_layout,
        &image_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let pixel_prefix_bind_group_layout = pixel_prefix_bind_group_layout(device);
    let pixel_prefix_pipeline = create_pixel_prefix_pipeline(
        device,
        &pixel_prefix_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );
    let blend_ellipse_pipeline = create_blend_ellipse_pipeline(
        device,
        &pixel_prefix_bind_group_layout,
        wgpu::TextureFormat::Rgba8Unorm,
    );

    PipelineResources {
        viewport_bind_group_layout,
        present_texture_bind_group_layout,
        image_bind_group_layout,
        clip_bind_group_layout,
        model_bind_group_layout,
        pixel_prefix_bind_group_layout,
        pipeline,
        primitive_pipelines,
        procedural_primitive_pipelines,
        erase_pipeline,
        image_pipeline,
        image_pipelines,
        model_pipeline,
        textured_model_pipeline,
        pixel_prefix_pipeline,
        blend_ellipse_pipeline,
    }
}
