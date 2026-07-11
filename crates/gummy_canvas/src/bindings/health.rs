use crate::runtime::native_window_available as runtime_native_window_available;
use crate::{gpu, CANVAS_ABI_VERSION};
use pyo3::prelude::*;

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
