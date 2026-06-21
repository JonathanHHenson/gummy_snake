mod gpu;
mod image_ops;
mod performance;
mod raster;
mod runtime;
mod software3d;
mod text;

mod bindings;
mod canvas_cache_text;
mod canvas_curves;
mod canvas_gpu_paths;
mod canvas_image_helpers;
mod canvas_images;
mod canvas_lifecycle;
mod canvas_methods;
mod canvas_pixels;
mod canvas_primitives;
mod canvas_text;
mod runtime_style;
#[cfg(test)]
#[allow(unused_imports)]
pub(crate) use bindings::{health_check, native_window_available};

use ab_glyph::FontArc;
use image_ops::{
    alpha_composite_rgba_region, apply_rgba_mask, convert_media_frame_to_rgba,
    crop_rgba_with_padding, filter_rgba, replace_rgba_region, resize_rgba_nearest,
    validate_rgba_buffer,
};
use performance::PerformanceCounters;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList};
use raster::{
    affine_bounds, axis_aligned_image_destination, blit_affine_region, blit_scaled_region,
    clipped_bounds, clipped_dest_rect, clipped_source_rect, draw_axis_aligned_ellipse,
    draw_polygon_overlay, draw_polyline_stroke, ellipse_bounds, fill_disc, fill_rgba_buffer,
    gpu_color, image_to_canvas_matrix, matrix_determinant, matrix_inverse, matrix_transform_point,
    point_to_f32, polygon_is_convex, push_triangle, rgba_to_present_pixel, scale_rect,
    stroke_segment, stroke_width, Matrix, OverlayRegion, Point,
};
use runtime::{
    native_window_available as runtime_native_window_available, InteractiveRuntime, RuntimeEvent,
};
use std::collections::{HashMap, VecDeque};
use std::f64::consts::PI;
use std::sync::atomic::{AtomicU64, Ordering};
use text::{
    default_font_paths, render_text_line, text_ascent as measure_text_ascent,
    text_descent as measure_text_descent, text_width,
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
const CANVAS_ABI_VERSION: u32 = 1;
static NEXT_IMAGE_KEY: AtomicU64 = AtomicU64::new(1);

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
    blend_mode: String,
    erasing: bool,
    image_sampling: String,
    text_font_path: Option<String>,
    text_font_name: String,
    text_size: f64,
    text_align_x: String,
    text_align_y: String,
    text_leading: f64,
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
    image_cache: HashMap<u64, CachedImage>,
    text_cache: HashMap<String, CachedText>,
    text_cache_order: VecDeque<String>,
    font_cache: HashMap<String, FontArc>,
    next_text_key: u64,
    texture_cache_versions: HashMap<u64, u64>,
    runtime: Option<InteractiveRuntime>,
    gpu: Option<gpu::GpuRenderer>,
    gpu_error: Option<String>,
    render_dirty: bool,
    offscreen_dirty: bool,
    pixels_stale: bool,
    texture_stale: bool,
    cached_style_key: Option<usize>,
    cached_style: Option<Style>,
    performance_counters: PerformanceCounters,
}

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bindings::register(m)
}

#[cfg(test)]
mod tests;
