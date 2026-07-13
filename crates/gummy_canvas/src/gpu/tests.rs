use crate::gpu::pipeline::{preferred_surface_format, surface_config};
use crate::gpu::{GpuColor, GpuRenderer, ModelUniform, ModelVertex};
use crate::types::BlendMode;

fn rect_vertices(x0: f32, y0: f32, x1: f32, y1: f32, color: GpuColor) -> Vec<([f32; 2], GpuColor)> {
    vec![
        ([x0, y0], color),
        ([x1, y0], color),
        ([x1, y1], color),
        ([x0, y0], color),
        ([x1, y1], color),
        ([x0, y1], color),
    ]
}

fn image_rect_vertices(
    x0: f32,
    y0: f32,
    x1: f32,
    y1: f32,
    tint: GpuColor,
) -> [([f32; 2], [f32; 2], GpuColor); 6] {
    [
        ([x0, y0], [0.0, 0.0], tint),
        ([x1, y0], [1.0, 0.0], tint),
        ([x1, y1], [1.0, 1.0], tint),
        ([x0, y0], [0.0, 0.0], tint),
        ([x1, y1], [1.0, 1.0], tint),
        ([x0, y1], [0.0, 1.0], tint),
    ]
}

fn flat_model_uniform(color: GpuColor, z: f32) -> ModelUniform {
    let identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ];
    let mut model = identity;
    model[3][2] = z;
    ModelUniform {
        model,
        view_projection: identity,
        base_color: color.as_float(),
        emissive_color: [0.0; 4],
        specular_shininess: [0.0; 4],
        ambient_color: [1.0; 4],
        directional_color: [0.0; 4],
        directional_direction: [0.0, 0.0, -1.0, 0.0],
        point_color: [0.0; 4],
        point_position: [0.0; 4],
        flags: [0.0; 4],
    }
}

fn pixel_at(pixels: &[u8], width: usize, x: usize, y: usize) -> [u8; 4] {
    let index = (y * width + x) * 4;
    [
        pixels[index],
        pixels[index + 1],
        pixels[index + 2],
        pixels[index + 3],
    ]
}

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
fn texture_replacement_and_removal_release_gpu_map_ownership() {
    let mut gpu = match GpuRenderer::new(2, 2) {
        Ok(gpu) => gpu,
        Err(_) => return,
    };
    let first = [255u8, 0, 0, 255];
    let second = [0u8, 0, 255, 255];

    assert_eq!(gpu.upload_texture(7, 1, 1, &first).unwrap(), None);
    assert_eq!(gpu.upload_texture(7, 1, 1, &second).unwrap(), Some(4));
    assert_eq!(gpu.remove_texture(7), Some(4));
    assert_eq!(gpu.remove_texture(7), None);
}

#[test]
fn mixed_primitive_image_primitive_text_primitive_order_remains_visible() {
    let mut gpu = match GpuRenderer::new(8, 8) {
        Ok(gpu) => gpu,
        Err(_) => return,
    };
    let black = GpuColor {
        r: 0,
        g: 0,
        b: 0,
        a: 255,
    };
    let red = GpuColor {
        r: 255,
        g: 0,
        b: 0,
        a: 255,
    };
    let green = GpuColor {
        r: 0,
        g: 255,
        b: 0,
        a: 255,
    };
    let yellow = GpuColor {
        r: 255,
        g: 255,
        b: 0,
        a: 255,
    };
    let white = GpuColor {
        r: 255,
        g: 255,
        b: 255,
        a: 255,
    };

    gpu.begin_frame();
    gpu.set_clear_color(black);
    gpu.draw_triangles(rect_vertices(0.0, 0.0, 2.0, 2.0, red), BlendMode::Blend);
    gpu.upload_texture(
        42,
        2,
        2,
        &[
            0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255,
        ],
    )
    .unwrap();
    gpu.draw_image(
        42,
        image_rect_vertices(2.0, 0.0, 4.0, 2.0, white),
        false,
        BlendMode::Blend,
    );
    gpu.draw_triangles(rect_vertices(4.0, 0.0, 6.0, 2.0, green), BlendMode::Blend);
    gpu.draw_text("order".to_string(), 0.0, 3.0, 8.0, 4.0, 3.0, 4.0, white);
    gpu.draw_triangles(rect_vertices(6.0, 0.0, 8.0, 2.0, yellow), BlendMode::Blend);

    let pixels = gpu.render_and_read_pixels().unwrap();
    assert_eq!(pixel_at(&pixels, 8, 1, 1), [255, 0, 0, 255]);
    assert_eq!(pixel_at(&pixels, 8, 3, 1), [0, 0, 255, 255]);
    assert_eq!(pixel_at(&pixels, 8, 5, 1), [0, 255, 0, 255]);
    assert_eq!(pixel_at(&pixels, 8, 7, 1), [255, 255, 0, 255]);
    let counters = gpu.render_loop_counters();
    assert_eq!(counters.command_clone_count, 0);
    assert_eq!(counters.command_clone_bytes, 0);
    assert_eq!(counters.command_segment_allocation_count, 0);
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
#[test]
fn retained_replay_recycles_command_streams_without_cloning() {
    let mut gpu = match GpuRenderer::new(8, 8) {
        Ok(gpu) => gpu,
        Err(_) => return,
    };
    let black = GpuColor {
        r: 0,
        g: 0,
        b: 0,
        a: 255,
    };
    let red = GpuColor {
        r: 255,
        g: 0,
        b: 0,
        a: 255,
    };
    let vertices = std::sync::Arc::new(rect_vertices(0.0, 0.0, 8.0, 8.0, red));
    gpu.reset_render_loop_counters();

    for _ in 0..2 {
        gpu.begin_frame();
        gpu.set_clear_color(black);
        gpu.draw_retained_triangles(7, std::sync::Arc::clone(&vertices), BlendMode::Blend);
        gpu.render();
    }

    let counters = gpu.render_loop_counters();
    assert_eq!(counters.retained_batch_cache_misses, 1);
    assert_eq!(counters.retained_batch_cache_hits, 1);
    assert_eq!(counters.command_clone_count, 0);
    assert_eq!(counters.command_clone_bytes, 0);
    assert_eq!(counters.command_segment_allocation_count, 0);
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
#[test]
fn model_depth_and_uniform_offsets_survive_text_boundaries() {
    let mut gpu = match GpuRenderer::new(8, 8) {
        Ok(gpu) => gpu,
        Err(_) => return,
    };
    let black = GpuColor {
        r: 0,
        g: 0,
        b: 0,
        a: 255,
    };
    let red = GpuColor {
        r: 255,
        g: 0,
        b: 0,
        a: 255,
    };
    let green = GpuColor {
        r: 0,
        g: 255,
        b: 0,
        a: 255,
    };
    let transparent = GpuColor {
        r: 255,
        g: 255,
        b: 255,
        a: 0,
    };
    let vertices = [
        ModelVertex {
            position: [-1.0, -1.0, 0.0],
            normal: [0.0, 0.0, 1.0],
            uv: [0.0, 0.0],
        },
        ModelVertex {
            position: [1.0, -1.0, 0.0],
            normal: [0.0, 0.0, 1.0],
            uv: [1.0, 0.0],
        },
        ModelVertex {
            position: [1.0, 1.0, 0.0],
            normal: [0.0, 0.0, 1.0],
            uv: [1.0, 1.0],
        },
        ModelVertex {
            position: [-1.0, 1.0, 0.0],
            normal: [0.0, 0.0, 1.0],
            uv: [0.0, 1.0],
        },
    ];
    let index_count = gpu
        .ensure_model_mesh(99, &vertices, &[0, 1, 2, 0, 2, 3])
        .unwrap();

    gpu.begin_frame();
    gpu.set_clear_color(black);
    gpu.draw_model(99, index_count, flat_model_uniform(red, 0.2));
    gpu.draw_text(
        "depth".to_string(),
        0.0,
        0.0,
        8.0,
        4.0,
        3.0,
        4.0,
        transparent,
    );
    gpu.draw_model(99, index_count, flat_model_uniform(green, 0.8));

    let pixels = gpu.render_and_read_pixels().unwrap();
    assert_eq!(pixel_at(&pixels, 8, 4, 4), [255, 0, 0, 255]);
    let counters = gpu.render_loop_counters();
    assert_eq!(counters.command_clone_count, 0);
    assert_eq!(counters.command_clone_bytes, 0);
    assert_eq!(counters.command_segment_allocation_count, 0);
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
#[test]
fn surface_config_requests_auto_no_vsync_present_mode() {
    let capabilities = wgpu::SurfaceCapabilities {
        formats: vec![wgpu::TextureFormat::Rgba8Unorm],
        present_modes: vec![wgpu::PresentMode::Fifo, wgpu::PresentMode::Immediate],
        alpha_modes: vec![wgpu::CompositeAlphaMode::Opaque],
        usages: wgpu::TextureUsages::RENDER_ATTACHMENT,
    };

    let config = surface_config(&capabilities, 640, 480).unwrap();

    assert_eq!(config.present_mode, wgpu::PresentMode::AutoNoVsync);
    assert_eq!(config.desired_maximum_frame_latency, 1);
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
#[test]
fn surface_config_requests_auto_no_vsync_even_when_fifo_is_only_listed_mode() {
    let capabilities = wgpu::SurfaceCapabilities {
        formats: vec![wgpu::TextureFormat::Rgba8Unorm],
        present_modes: vec![wgpu::PresentMode::Fifo],
        alpha_modes: vec![wgpu::CompositeAlphaMode::Opaque],
        usages: wgpu::TextureUsages::RENDER_ATTACHMENT,
    };

    let config = surface_config(&capabilities, 640, 480).unwrap();

    assert_eq!(config.present_mode, wgpu::PresentMode::AutoNoVsync);
}
