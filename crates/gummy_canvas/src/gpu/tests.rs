use crate::gpu::pipeline::{preferred_surface_format, surface_config};

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
