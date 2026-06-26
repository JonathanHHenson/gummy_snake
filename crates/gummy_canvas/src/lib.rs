#![allow(
    clippy::arc_with_non_send_sync,
    clippy::too_many_arguments,
    clippy::useless_conversion,
    clippy::useless_vec
)]

mod assets;
mod canvas;
mod canvas_state;
mod gpu;
mod images;
mod performance;
mod raster;
mod runtime;
mod sketch_state;
mod software3d;
mod sound;
mod text;
mod types;

mod bindings;
#[cfg(test)]
#[allow(unused_imports)]
pub(crate) use bindings::{health_check, native_window_available};

pub(crate) use assets::{CachedImage, CachedText, CachedTextMetrics, CanvasImage};
pub(crate) use canvas_state::{Canvas, Pending3dTriangle};
pub(crate) use sound::CanvasSound;
pub(crate) use types::{BlendMode, Matrix2D, Rgba, Style};

use canvas::cache::{ImageCache, TextCache, TextureCache};
use images::{
    alpha_composite_rgba_region, crop_rgba_with_padding, filter_rgba, replace_rgba_region,
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

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bindings::register(m)
}

#[cfg(test)]
mod tests;
