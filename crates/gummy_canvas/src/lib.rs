#![allow(
    clippy::arc_with_non_send_sync,
    clippy::too_many_arguments,
    clippy::useless_conversion,
    clippy::useless_vec
)]

mod canvas;
mod gpu;
mod images;
mod performance;
mod raster;
mod runtime;
mod sketch_state;
mod software3d;
mod text;

mod bindings;
#[cfg(test)]
#[allow(unused_imports)]
pub(crate) use bindings::{health_check, native_window_available};

use canvas::cache::{ImageCache, TextCache, TextureCache};
use images::{
    alpha_composite_rgba_region, apply_rgba_mask, convert_media_frame_to_rgba,
    crop_rgba_with_padding, filter_rgba, replace_rgba_region, resize_rgba_nearest,
    validate_rgba_buffer,
};
use performance::PerformanceCounters;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList, PyTuple};
use raster::{
    affine_bounds, axis_aligned_image_destination, blit_affine_region, blit_scaled_region,
    clipped_bounds, clipped_dest_rect, clipped_source_rect, draw_axis_aligned_ellipse,
    draw_polygon_overlay, draw_polyline_stroke, ellipse_bounds, fill_axis_aligned_ellipse,
    fill_disc, fill_even_odd_polygon, fill_rgba_buffer, for_even_odd_spans, image_to_canvas_matrix,
    matrix_determinant, matrix_inverse, matrix_transform_point, point_to_f32, polygon_is_convex,
    push_triangle, rasterize_even_odd_mask, rgba_to_present_pixel, scale_rect, stroke_segment,
    stroke_width, Matrix, OverlayRegion, Point,
};
use runtime::{
    native_window_available as runtime_native_window_available, InteractiveRuntime,
    DEFAULT_POINTER_LOCK_MODE,
};
use std::collections::VecDeque;
use std::f64::consts::PI;
use std::fs;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use text::{
    default_font_paths, render_text_line, text_ascent as measure_text_ascent,
    text_descent as measure_text_descent,
};

const SUPPORTED_RENDERER: &str = "p2d";
const SUPPORTED_MODE: &str = "headless";
const INTERACTIVE_MODE: &str = "interactive";
const BLEND_MODE_BLEND: &str = "blend";
const BLEND_MODE_ADD: &str = "add";
const BLEND_MODE_DARKEST: &str = "darkest";
const BLEND_MODE_LIGHTEST: &str = "lightest";
const BLEND_MODE_DIFFERENCE: &str = "difference";
const BLEND_MODE_EXCLUSION: &str = "exclusion";
const BLEND_MODE_MULTIPLY: &str = "multiply";
const BLEND_MODE_REPLACE: &str = "replace";
const BLEND_MODE_SCREEN: &str = "screen";
const IMAGE_CACHE_LIMIT: usize = 1024;
const TEXTURE_CACHE_LIMIT: usize = 1024;
const TEXT_CACHE_LIMIT: usize = 512;
const CANVAS_ABI_VERSION: u32 = 13;
static NEXT_IMAGE_KEY: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub(crate) enum BlendMode {
    Blend,
    Add,
    Darkest,
    Lightest,
    Difference,
    Exclusion,
    Multiply,
    Replace,
    Screen,
}

impl BlendMode {
    fn parse(mode: &str) -> Option<Self> {
        match mode {
            BLEND_MODE_BLEND => Some(Self::Blend),
            BLEND_MODE_ADD => Some(Self::Add),
            BLEND_MODE_DARKEST => Some(Self::Darkest),
            BLEND_MODE_LIGHTEST => Some(Self::Lightest),
            BLEND_MODE_DIFFERENCE => Some(Self::Difference),
            BLEND_MODE_EXCLUSION => Some(Self::Exclusion),
            BLEND_MODE_MULTIPLY => Some(Self::Multiply),
            BLEND_MODE_REPLACE => Some(Self::Replace),
            BLEND_MODE_SCREEN => Some(Self::Screen),
            _ => None,
        }
    }

    fn gpu_fixed_function_supported(self) -> bool {
        matches!(self, Self::Blend | Self::Add | Self::Replace)
    }
}

#[pyclass(name = "Matrix2D", frozen, unsendable)]
#[derive(Clone, Copy, Debug, PartialEq)]
struct Matrix2D {
    #[pyo3(get)]
    a: f64,
    #[pyo3(get)]
    b: f64,
    #[pyo3(get)]
    c: f64,
    #[pyo3(get)]
    d: f64,
    #[pyo3(get)]
    e: f64,
    #[pyo3(get)]
    f: f64,
}

impl Default for Matrix2D {
    fn default() -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    }
}

#[pymethods]
impl Matrix2D {
    #[new]
    #[pyo3(signature = (a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0))]
    fn new(a: f64, b: f64, c: f64, d: f64, e: f64, f: f64) -> Self {
        Self { a, b, c, d, e, f }
    }

    #[staticmethod]
    fn identity() -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    }

    #[staticmethod]
    fn translation(x: f64, y: f64) -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, x, y)
    }

    #[staticmethod]
    fn rotation(angle: f64) -> Self {
        let (sine, cosine) = angle.sin_cos();
        Self::new(cosine, sine, -sine, cosine, 0.0, 0.0)
    }

    #[staticmethod]
    #[pyo3(signature = (x, y=None))]
    fn scaling(x: f64, y: Option<f64>) -> Self {
        Self::new(x, 0.0, 0.0, y.unwrap_or(x), 0.0, 0.0)
    }

    #[staticmethod]
    fn shear_x(angle: f64) -> Self {
        Self::new(1.0, 0.0, angle.tan(), 1.0, 0.0, 0.0)
    }

    #[staticmethod]
    fn shear_y(angle: f64) -> Self {
        Self::new(1.0, angle.tan(), 0.0, 1.0, 0.0, 0.0)
    }

    fn multiply(&self, other: PyRef<'_, Self>) -> Self {
        Self::new(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )
    }

    fn transform_point(&self, x: f64, y: f64) -> (f64, f64) {
        (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )
    }

    fn inverse(&self) -> PyResult<Self> {
        let determinant = self.a * self.d - self.b * self.c;
        if determinant.abs() < 1e-12 {
            return Err(PyValueError::new_err("Matrix is not invertible."));
        }
        Ok(Self::new(
            self.d / determinant,
            -self.b / determinant,
            -self.c / determinant,
            self.a / determinant,
            (self.c * self.f - self.d * self.e) / determinant,
            (self.b * self.e - self.a * self.f) / determinant,
        ))
    }

    fn as_tuple<'py>(&self, py: Python<'py>) -> Bound<'py, PyTuple> {
        PyTuple::new_bound(py, [self.a, self.b, self.c, self.d, self.e, self.f])
    }

    fn __repr__(&self) -> String {
        format!(
            "Matrix2D(a={}, b={}, c={}, d={}, e={}, f={})",
            self.a, self.b, self.c, self.d, self.e, self.f
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Rgba {
    r: u8,
    g: u8,
    b: u8,
    a: u8,
}

impl Rgba {
    fn from_tuple(tuple: (u8, u8, u8, u8)) -> Self {
        Self {
            r: tuple.0,
            g: tuple.1,
            b: tuple.2,
            a: tuple.3,
        }
    }

    fn as_array(self) -> [u8; 4] {
        [self.r, self.g, self.b, self.a]
    }
}

#[derive(Clone, Debug)]
struct Style {
    fill: Option<Rgba>,
    stroke: Option<Rgba>,
    stroke_weight: f64,
    image_tint: Option<Rgba>,
    blend_mode: String,
    blend_mode_kind: BlendMode,
    erasing: bool,
    image_sampling: String,
    text_font_path: Option<String>,
    text_font_name: String,
    text_size: f64,
    text_align_x: String,
    text_align_y: String,
    text_leading: f64,
}

impl Default for Style {
    fn default() -> Self {
        Self {
            fill: Some(Rgba {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            }),
            stroke: Some(Rgba {
                r: 0,
                g: 0,
                b: 0,
                a: 255,
            }),
            stroke_weight: 1.0,
            image_tint: None,
            blend_mode: BLEND_MODE_BLEND.to_string(),
            blend_mode_kind: BlendMode::Blend,
            erasing: false,
            image_sampling: "linear".to_string(),
            text_font_path: None,
            text_font_name: "default".to_string(),
            text_size: 12.0,
            text_align_x: "left".to_string(),
            text_align_y: "baseline".to_string(),
            text_leading: 14.0,
        }
    }
}

#[derive(Clone, Debug)]
struct CachedImage {
    version: u64,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
}

#[derive(Clone, Debug)]
struct CachedText {
    texture_key: u64,
    image: CachedImage,
    bbox_left: i32,
    bbox_top: i32,
    ascent: f64,
}

#[derive(Clone, Copy, Debug)]
struct CachedTextMetrics {
    width: f64,
    ascent: f64,
    descent: f64,
}

#[pyclass(name = "CanvasImage", unsendable)]
#[derive(Clone, Debug)]
struct CanvasImage {
    key: u64,
    version: u64,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
}

#[pymethods]
impl CanvasImage {
    #[staticmethod]
    fn from_file(path: &str) -> PyResult<Self> {
        let image = image::open(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load image {path}: {err}")))?
            .to_rgba8();
        let (width, height) = image.dimensions();
        Ok(Self::from_pixels(
            width as usize,
            height as usize,
            image.into_raw(),
        ))
    }

    #[staticmethod]
    fn from_rgba_bytes(width: usize, height: usize, pixels: Vec<u8>) -> PyResult<Self> {
        validate_rgba_buffer(pixels.len(), width, height)?;
        Ok(Self::from_pixels(width, height, pixels))
    }

    #[getter]
    fn width(&self) -> usize {
        self.width
    }

    #[getter]
    fn height(&self) -> usize {
        self.height
    }

    #[getter]
    fn version(&self) -> u64 {
        self.version
    }

    #[getter]
    fn key(&self) -> u64 {
        self.key
    }

    fn get_pixel(&self, x: usize, y: usize) -> PyResult<(u8, u8, u8, u8)> {
        let offset = self.pixel_offset(x, y)?;
        Ok((
            self.pixels[offset],
            self.pixels[offset + 1],
            self.pixels[offset + 2],
            self.pixels[offset + 3],
        ))
    }

    fn set_pixel(&mut self, x: usize, y: usize, r: u8, g: u8, b: u8, a: u8) -> PyResult<()> {
        let offset = self.pixel_offset(x, y)?;
        self.pixels[offset..offset + 4].copy_from_slice(&[r, g, b, a]);
        self.bump_version();
        Ok(())
    }

    fn replace_rgba_bytes(&mut self, pixels: Vec<u8>) -> PyResult<()> {
        validate_rgba_buffer(pixels.len(), self.width, self.height)?;
        self.pixels = pixels;
        self.bump_version();
        Ok(())
    }

    fn copy(&self) -> Self {
        Self::from_pixels(self.width, self.height, self.pixels.clone())
    }

    fn crop(&self, sx: i64, sy: i64, sw: i64, sh: i64) -> PyResult<Self> {
        if sw <= 0 || sh <= 0 {
            return Err(PyValueError::new_err(
                "Image region dimensions must be positive.",
            ));
        }
        Ok(Self::from_pixels(
            sw as usize,
            sh as usize,
            crop_rgba_with_padding(
                &self.pixels,
                self.width,
                self.height,
                sx,
                sy,
                sw as usize,
                sh as usize,
            ),
        ))
    }

    fn resize(&mut self, target_width: usize, target_height: usize) -> PyResult<()> {
        if target_width == 0 || target_height == 0 {
            return Err(PyValueError::new_err(
                "Image.resize() dimensions must be positive.",
            ));
        }
        self.pixels = resize_rgba_nearest(
            &self.pixels,
            self.width,
            self.height,
            target_width,
            target_height,
        );
        self.width = target_width;
        self.height = target_height;
        self.bump_version();
        Ok(())
    }

    fn mask(&mut self, mask: PyRef<'_, CanvasImage>) -> PyResult<()> {
        apply_rgba_mask(
            &mut self.pixels,
            self.width,
            self.height,
            &mask.pixels,
            mask.width,
            mask.height,
        );
        self.bump_version();
        Ok(())
    }

    #[pyo3(signature = (mode, value=None))]
    fn filter(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        filter_rgba(&mut self.pixels, mode, value)?;
        self.bump_version();
        Ok(())
    }

    fn alpha_composite(&mut self, source: PyRef<'_, CanvasImage>, dx: i64, dy: i64) {
        alpha_composite_rgba_region(
            &mut self.pixels,
            self.width,
            self.height,
            &source.pixels,
            source.width,
            source.height,
            dx,
            dy,
        );
        self.bump_version();
    }

    fn save(&self, path: &str) -> PyResult<()> {
        image::save_buffer_with_format(
            path,
            &self.pixels,
            self.width as u32,
            self.height as u32,
            image::ColorType::Rgba8,
            image::ImageFormat::Png,
        )
        .map_err(|err| PyValueError::new_err(format!("Failed to save image {path}: {err}")))
    }

    fn to_rgba_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.pixels)
    }
}

impl CanvasImage {
    fn from_pixels(width: usize, height: usize, pixels: Vec<u8>) -> Self {
        Self {
            key: NEXT_IMAGE_KEY.fetch_add(1, Ordering::Relaxed),
            version: 0,
            width,
            height,
            pixels,
        }
    }

    fn pixel_offset(&self, x: usize, y: usize) -> PyResult<usize> {
        if x >= self.width || y >= self.height {
            return Err(PyValueError::new_err(
                "Pixel coordinates are outside the image bounds.",
            ));
        }
        Ok((y * self.width + x) * 4)
    }

    fn bump_version(&mut self) {
        self.version = self.version.wrapping_add(1);
    }
}

#[pyclass(name = "CanvasSound", unsendable)]
#[derive(Clone, Debug)]
struct CanvasSound {
    path: String,
    bytes: Vec<u8>,
    duration: Option<f64>,
}

#[pymethods]
impl CanvasSound {
    #[staticmethod]
    fn from_file(path: &str) -> PyResult<Self> {
        let bytes = fs::read(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load sound {path}: {err}")))?;
        let duration = wav_duration_seconds(&bytes)?;
        Ok(Self {
            path: path.to_owned(),
            bytes,
            duration,
        })
    }

    #[getter]
    fn path(&self) -> &str {
        &self.path
    }

    #[getter]
    fn duration(&self) -> Option<f64> {
        self.duration
    }

    #[getter]
    fn byte_len(&self) -> usize {
        self.bytes.len()
    }

    fn to_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.bytes)
    }
}

fn wav_duration_seconds(bytes: &[u8]) -> PyResult<Option<f64>> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Ok(None);
    }

    let mut offset = 12usize;
    let mut channels: Option<u16> = None;
    let mut sample_rate: Option<u32> = None;
    let mut bits_per_sample: Option<u16> = None;
    let mut data_len: Option<u32> = None;

    while offset.checked_add(8).is_some_and(|end| end <= bytes.len()) {
        let chunk_id = &bytes[offset..offset + 4];
        let chunk_len = u32::from_le_bytes([
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]);
        offset += 8;
        let chunk_len_usize = chunk_len as usize;
        if offset
            .checked_add(chunk_len_usize)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(PyValueError::new_err(
                "Could not load WAV sound: malformed chunk length.",
            ));
        }
        let chunk = &bytes[offset..offset + chunk_len_usize];
        match chunk_id {
            b"fmt " => {
                if chunk.len() < 16 {
                    return Err(PyValueError::new_err(
                        "Could not load WAV sound: malformed fmt chunk.",
                    ));
                }
                channels = Some(u16::from_le_bytes([chunk[2], chunk[3]]));
                sample_rate = Some(u32::from_le_bytes([chunk[4], chunk[5], chunk[6], chunk[7]]));
                bits_per_sample = Some(u16::from_le_bytes([chunk[14], chunk[15]]));
            }
            b"data" => {
                data_len = Some(chunk_len);
            }
            _ => {}
        }
        offset += chunk_len_usize + (chunk_len_usize % 2);
    }

    let Some(channels) = channels else {
        return Ok(None);
    };
    let Some(sample_rate) = sample_rate else {
        return Ok(None);
    };
    let Some(bits_per_sample) = bits_per_sample else {
        return Ok(None);
    };
    let Some(data_len) = data_len else {
        return Ok(None);
    };
    let bytes_per_sample = u32::from(bits_per_sample).div_ceil(8);
    let frame_bytes = u32::from(channels).saturating_mul(bytes_per_sample);
    if sample_rate == 0 || frame_bytes == 0 {
        return Ok(None);
    }
    Ok(Some(
        data_len as f64 / frame_bytes as f64 / sample_rate as f64,
    ))
}

#[pyclass(unsendable)]
struct Canvas {
    width: i64,
    height: i64,
    physical_width: usize,
    physical_height: usize,
    pixel_density: f64,
    mode: String,
    window_open: bool,
    closed: bool,
    pixels: Vec<u8>,
    present_pixels: Vec<u32>,
    erase_color: Rgba,
    image_cache: ImageCache,
    text_cache: TextCache,
    text_cache_order: VecDeque<String>,
    texture_cache_versions: TextureCache,
    clip_masks: Vec<Vec<bool>>,
    clip_bounds: Vec<(usize, usize, usize, usize)>,
    runtime: Option<InteractiveRuntime>,
    pointer_lock_mode: String,
    gpu: Option<gpu::GpuRenderer>,
    gpu_error: Option<String>,
    render_dirty: bool,
    offscreen_dirty: bool,
    pixels_stale: bool,
    texture_stale: bool,
    last_reusable_text_frame_signature: Option<String>,
    pending_reusable_text_frame_signature: Option<String>,
    cpu_compositing_active: bool,
    image_text_active_this_frame: bool,
    cached_style_key: Option<(usize, i64)>,
    cached_style: Option<Style>,
    current_style: Style,
    style_stack: Vec<Style>,
    current_matrix: Matrix,
    matrix_stack: Vec<Matrix>,
    performance_counters: PerformanceCounters,
    pending_3d_triangles: Vec<Pending3dTriangle>,
    primitive_batch_cache_key: Option<u64>,
    primitive_batch_cache_record_count: usize,
    primitive_batch_cache_vertices: std::sync::Arc<Vec<([f32; 2], gpu::GpuColor)>>,
    primitive_batch_cache_instances: std::sync::Arc<Vec<gpu::PrimitiveInstance>>,
}

#[derive(Clone, Copy, Debug)]
struct Pending3dTriangle {
    depth: f64,
    vertices: [([f32; 2], gpu::GpuColor); 3],
}

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bindings::register(m)
}

#[cfg(test)]
mod tests;
