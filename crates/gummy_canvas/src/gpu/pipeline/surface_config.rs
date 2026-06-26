#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub(in crate::gpu) fn surface_config(
    capabilities: &wgpu::SurfaceCapabilities,
    width: u32,
    height: u32,
) -> Option<wgpu::SurfaceConfiguration> {
    let format = preferred_surface_format(&capabilities.formats)?;
    let present_mode = wgpu::PresentMode::AutoNoVsync;
    let alpha_mode = capabilities
        .alpha_modes
        .iter()
        .copied()
        .find(|mode| *mode == wgpu::CompositeAlphaMode::Opaque)
        .or_else(|| capabilities.alpha_modes.first().copied())
        .unwrap_or(wgpu::CompositeAlphaMode::Auto);

    Some(wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format,
        width,
        height,
        present_mode,
        desired_maximum_frame_latency: 1,
        alpha_mode,
        view_formats: vec![],
    })
}

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
pub(in crate::gpu) fn preferred_surface_format(
    formats: &[wgpu::TextureFormat],
) -> Option<wgpu::TextureFormat> {
    [
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Bgra8Unorm,
    ]
    .into_iter()
    .find(|format| formats.contains(format))
    .or_else(|| formats.iter().copied().find(|format| !format.is_srgb()))
    .or_else(|| formats.first().copied())
}
