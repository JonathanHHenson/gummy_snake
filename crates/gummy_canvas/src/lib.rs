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
pub(crate) use canvas_state::Canvas;
pub(crate) use sound::CanvasSound;
pub(crate) use types::{BlendMode, Matrix2D, Rgba, Style};

use canvas::cache::{ImageCache, TextCache, TextureCache};
use images::{crop_rgba_with_padding, validate_rgba_buffer};
use performance::PerformanceCounters;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList, PyTuple};
use raster::{
    clipped_source_rect, image_to_canvas_matrix, matrix_determinant, matrix_transform_point,
    point_to_f32, polygon_is_convex, rgba_to_present_pixel, stroke_width, Matrix, Point,
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
const CANVAS_ABI_VERSION: u32 = 15;

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bindings::register(m)
}

#[cfg(test)]
mod tests;
