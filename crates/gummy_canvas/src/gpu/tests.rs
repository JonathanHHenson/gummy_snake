use crate::gpu::pipeline::{preferred_surface_format, surface_config};
use crate::gpu::{GpuColor, GpuRenderer};
use crate::BlendMode;

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
