//! Required Gummy Snake canvas runtime and PyO3 extension registration root.
//!
//! This crate owns canvas lifecycle state, GPU/raster rendering, native SDL3
//! presentation/input, assets, pixels, text, and the Python bridge that links
//! `gummy_ecs` and `gummy_synth`. The Python-visible `_canvas` module and canvas
//! ABI are registered here; implementation ownership is documented in the
//! contributor [ownership map](../../../docs/contribute/ownership_map.md).
//!
//! `gummy_ecs` owns canonical ECS storage and physical-plan execution, while
//! `gummy_synth` owns synth/sample/FX/WAV rendering. `gummy_accel` remains a
//! deliberately small optional extension and never replaces this mandatory runtime.

#![allow(
    clippy::arc_with_non_send_sync,
    clippy::too_many_arguments,
    clippy::useless_conversion,
    clippy::useless_vec
)]

mod assets;
mod canvas;
mod canvas_state;
mod config;
mod frame_commands;
mod gpu;
mod images;
mod performance;
mod prelude;
mod raster;
mod runtime;
mod sketch_state;
mod software3d;
mod sound;
mod text;
mod types;

mod bindings;
/// Canvas extension ABI marker validated by Python before runtime construction.
pub(crate) const CANVAS_ABI_VERSION: u32 = 20;

use pyo3::prelude::*;

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bindings::register(m)
}

#[cfg(test)]
mod tests;
