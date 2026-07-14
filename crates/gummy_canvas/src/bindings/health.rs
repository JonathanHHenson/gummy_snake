use crate::runtime::native_window_available as runtime_native_window_available;
use crate::{frame_commands::FRAME_COMMAND_ABI_VERSION, gpu, CANVAS_ABI_VERSION};
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyfunction]
pub(crate) fn health_check() -> &'static str {
    "rust-canvas"
}

#[pyfunction]
pub(crate) fn canvas_abi_version() -> u32 {
    CANVAS_ABI_VERSION
}

#[pyfunction]
pub(crate) fn frame_command_abi_version() -> u32 {
    FRAME_COMMAND_ABI_VERSION
}

#[pyfunction]
pub(crate) fn benchmark_provenance<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let payload = PyDict::new_bound(py);
    payload.set_item(
        "source_commit",
        option_env!("GUMMY_BENCHMARK_SOURCE_COMMIT").unwrap_or("unrecorded"),
    )?;
    payload.set_item(
        "source_digest",
        option_env!("GUMMY_BENCHMARK_SOURCE_DIGEST").unwrap_or("unrecorded"),
    )?;
    payload.set_item(
        "tree_digest",
        option_env!("GUMMY_BENCHMARK_TREE_DIGEST").unwrap_or("unrecorded"),
    )?;
    payload.set_item(
        "profile",
        option_env!("GUMMY_BENCHMARK_BUILD_PROFILE").unwrap_or("unrecorded"),
    )?;
    let features = option_env!("GUMMY_BENCHMARK_BUILD_FEATURES")
        .unwrap_or("")
        .split(',')
        .filter(|feature| !feature.is_empty())
        .collect::<Vec<_>>();
    payload.set_item("features", features)?;
    payload.set_item("canvas_crate_version", env!("CARGO_PKG_VERSION"))?;
    payload.set_item("ecs_crate_version", gummy_ecs::CRATE_VERSION)?;
    payload.set_item("synth_crate_version", gummy_synth::CRATE_VERSION)?;
    payload.set_item("renderer", "wgpu-high-performance-adapter")?;
    payload.set_item("native_window_available", runtime_native_window_available())?;
    if let Some(info) = gpu::GpuRenderer::adapter_info() {
        payload.set_item("gpu_available", true)?;
        payload.set_item("gpu_adapter", info.name)?;
        payload.set_item("gpu_backend", format!("{:?}", info.backend).to_lowercase())?;
        payload.set_item("gpu_driver", info.driver)?;
        payload.set_item("gpu_driver_info", info.driver_info)?;
        payload.set_item(
            "gpu_device_type",
            format!("{:?}", info.device_type).to_lowercase(),
        )?;
        payload.set_item("gpu_vendor_id", info.vendor)?;
        payload.set_item("gpu_device_id", info.device)?;
    } else {
        payload.set_item("gpu_available", false)?;
        payload.set_item("gpu_adapter", py.None())?;
        payload.set_item("gpu_backend", py.None())?;
        payload.set_item("gpu_driver", py.None())?;
        payload.set_item("gpu_driver_info", py.None())?;
        payload.set_item("gpu_device_type", py.None())?;
        payload.set_item("gpu_vendor_id", py.None())?;
        payload.set_item("gpu_device_id", py.None())?;
    }
    Ok(payload)
}

#[pyfunction]
pub(crate) fn native_window_available() -> bool {
    runtime_native_window_available()
}

#[pyfunction]
pub(crate) fn gpu_available() -> bool {
    gpu::GpuRenderer::is_available()
}
