//! Transitional internal import surface for legacy canvas implementation modules.
//!
//! This is deliberately crate-private and is not a public compatibility API. It
//! centralizes cross-cutting PyO3 and runtime names that were previously leaked
//! by `lib.rs`; new modules should import their narrow owning modules directly.
//! The crate root stays limited to module declarations and `_canvas` registration.

pub(crate) use crate::assets::{CachedImage, CachedText, CachedTextMetrics, CanvasImage};

pub(crate) use crate::canvas::cache::{ImageCache, TextCache, TextureCache};
pub(crate) use crate::canvas_state::Canvas;
pub(crate) use crate::config::*;
pub(crate) use crate::images::{crop_rgba_with_padding, validate_rgba_buffer};
pub(crate) use crate::performance::PerformanceCounters;
pub(crate) use crate::raster::{
    clipped_source_rect, image_to_canvas_matrix, matrix_determinant, matrix_transform_point,
    point_to_f32, polygon_is_convex, rgba_to_present_pixel, stroke_width, Matrix, Point,
};
pub(crate) use crate::runtime::{
    native_window_available as runtime_native_window_available, InteractiveRuntime,
    DEFAULT_POINTER_LOCK_MODE,
};
pub(crate) use crate::sound::{
    synth_play_serialized_plan, synth_play_wav_bytes, CanvasAudioPlayback, CanvasSound,
};
pub(crate) use crate::text::{
    default_font_paths, render_text_line, text_ascent as measure_text_ascent,
    text_descent as measure_text_descent,
};
pub(crate) use crate::types::{BlendMode, Matrix2D, Rgba, Style};
pub(crate) use crate::CANVAS_ABI_VERSION;
pub(crate) use crate::{sketch_state, software3d};
pub(crate) use pyo3::exceptions::PyValueError;
pub(crate) use pyo3::prelude::*;
pub(crate) use pyo3::types::{PyAny, PyBytes, PyDict, PyList};
pub(crate) use std::collections::VecDeque;
pub(crate) use std::f64::consts::PI;
