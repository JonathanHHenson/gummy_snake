use super::*;

#[pyfunction]
pub(crate) fn health_check() -> &'static str {
    "rust-canvas"
}

#[pyfunction]
pub(crate) fn canvas_abi_version() -> u32 {
    CANVAS_ABI_VERSION
}

#[pyfunction]
pub(crate) fn native_window_available() -> bool {
    runtime_native_window_available()
}

#[pyfunction]
pub(crate) fn gpu_available() -> bool {
    gpu::GpuRenderer::is_available()
}

#[pyfunction]
pub(crate) fn image_resize_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    target_width: usize,
    target_height: usize,
) -> PyResult<Bound<'py, PyBytes>> {
    validate_rgba_buffer(pixels.len(), width, height)?;
    if target_width == 0 || target_height == 0 {
        return Err(PyValueError::new_err(
            "Image.resize() dimensions must be positive.",
        ));
    }
    let resized = resize_rgba_nearest(&pixels, width, height, target_width, target_height);
    Ok(PyBytes::new_bound(py, &resized))
}

#[pyfunction]
pub(crate) fn image_crop_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    sx: i64,
    sy: i64,
    sw: i64,
    sh: i64,
) -> PyResult<Bound<'py, PyBytes>> {
    validate_rgba_buffer(pixels.len(), width, height)?;
    if sw <= 0 || sh <= 0 {
        return Err(PyValueError::new_err(
            "Image region dimensions must be positive.",
        ));
    }
    let cropped = crop_rgba_with_padding(&pixels, width, height, sx, sy, sw as usize, sh as usize);
    Ok(PyBytes::new_bound(py, &cropped))
}

#[pyfunction]
pub(crate) fn image_alpha_composite_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    source_width: usize,
    source_height: usize,
    source_pixels: Vec<u8>,
    dx: i64,
    dy: i64,
) -> PyResult<Bound<'py, PyBytes>> {
    validate_rgba_buffer(pixels.len(), width, height)?;
    validate_rgba_buffer(source_pixels.len(), source_width, source_height)?;
    let mut composited = pixels;
    alpha_composite_rgba_region(
        &mut composited,
        width,
        height,
        &source_pixels,
        source_width,
        source_height,
        dx,
        dy,
    );
    Ok(PyBytes::new_bound(py, &composited))
}

#[pyfunction]
pub(crate) fn image_mask_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    mask_width: usize,
    mask_height: usize,
    mask_pixels: Vec<u8>,
) -> PyResult<Bound<'py, PyBytes>> {
    validate_rgba_buffer(pixels.len(), width, height)?;
    validate_rgba_buffer(mask_pixels.len(), mask_width, mask_height)?;
    let mut masked = pixels;
    apply_rgba_mask(
        &mut masked,
        width,
        height,
        &mask_pixels,
        mask_width,
        mask_height,
    );
    Ok(PyBytes::new_bound(py, &masked))
}

#[pyfunction(signature = (width, height, pixels, mode, value=None))]
pub(crate) fn image_filter_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    mode: &str,
    value: Option<f64>,
) -> PyResult<Bound<'py, PyBytes>> {
    validate_rgba_buffer(pixels.len(), width, height)?;
    let mut filtered = pixels;
    filter_rgba(&mut filtered, mode, value)?;
    Ok(PyBytes::new_bound(py, &filtered))
}

#[pyfunction]
pub(crate) fn media_frame_to_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    channels: usize,
    pixels: Vec<u8>,
) -> PyResult<Bound<'py, PyBytes>> {
    let expected = width
        .checked_mul(height)
        .and_then(|pixel_count| pixel_count.checked_mul(channels))
        .ok_or_else(|| PyValueError::new_err("Media frame dimensions are too large."))?;
    if pixels.len() != expected {
        return Err(PyValueError::new_err(format!(
            "Media frame buffer length must be {expected}, got {}.",
            pixels.len()
        )));
    }
    let rgba = convert_media_frame_to_rgba(width, height, channels, &pixels)?;
    Ok(PyBytes::new_bound(py, &rgba))
}

#[pyfunction]
pub(crate) fn parse_obj_model<'py>(
    py: Python<'py>,
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<Bound<'py, PyDict>> {
    software3d::parse_obj_model(py, text, source, normalize)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub(crate) fn project_shade_faces<'py>(
    py: Python<'py>,
    meshes: &Bound<'py, PyAny>,
    camera: &Bound<'py, PyAny>,
    projection: &Bound<'py, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'py, PyAny>,
    lights: &Bound<'py, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
) -> PyResult<Bound<'py, PyList>> {
    software3d::project_shade_faces(
        py,
        meshes,
        camera,
        projection,
        viewport_width,
        viewport_height,
        material,
        lights,
        normal_material,
        cull_backfaces,
    )
}

#[pyfunction]
pub(crate) fn rasterize_faces_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    faces: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    software3d::rasterize_faces_rgba(py, width, height, faces)
}

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    m.add_function(wrap_pyfunction!(canvas_abi_version, m)?)?;
    m.add_function(wrap_pyfunction!(native_window_available, m)?)?;
    m.add_function(wrap_pyfunction!(gpu_available, m)?)?;
    m.add_function(wrap_pyfunction!(image_resize_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_crop_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_alpha_composite_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_mask_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_filter_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(media_frame_to_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(parse_obj_model, m)?)?;
    m.add_function(wrap_pyfunction!(project_shade_faces, m)?)?;
    m.add_function(wrap_pyfunction!(rasterize_faces_rgba, m)?)?;
    m.add("CANVAS_ABI_VERSION", CANVAS_ABI_VERSION)?;
    m.add_class::<Canvas>()?;
    m.add_class::<CanvasImage>()?;
    Ok(())
}
