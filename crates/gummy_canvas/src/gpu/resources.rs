//! Python-facing WGPU storage and compute resources.
//!
//! These handles deliberately use the process-shared `GpuDeviceContext`. Python
//! validates friendly values and owns only small wrappers; canonical bulk bytes,
//! shader modules, pipelines, bind groups, dispatch, and mapping remain in Rust.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use pollster::block_on;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use wgpu::util::DeviceExt;

use super::context::GpuDeviceContext;

static STORAGE_ALLOCATIONS: AtomicU64 = AtomicU64::new(0);
static STORAGE_DESTRUCTIONS: AtomicU64 = AtomicU64::new(0);
static STORAGE_CURRENT_BYTES: AtomicU64 = AtomicU64::new(0);
static STORAGE_PEAK_BYTES: AtomicU64 = AtomicU64::new(0);
static STORAGE_UPLOADS: AtomicU64 = AtomicU64::new(0);
static STORAGE_UPLOAD_BYTES: AtomicU64 = AtomicU64::new(0);
static STORAGE_READBACKS: AtomicU64 = AtomicU64::new(0);
static STORAGE_READBACK_BYTES: AtomicU64 = AtomicU64::new(0);
static COMPUTE_SHADER_MODULES: AtomicU64 = AtomicU64::new(0);
static COMPUTE_PIPELINES: AtomicU64 = AtomicU64::new(0);
static COMPUTE_BIND_GROUPS: AtomicU64 = AtomicU64::new(0);
static COMPUTE_DISPATCHES: AtomicU64 = AtomicU64::new(0);
static COMPUTE_WORKGROUPS: AtomicU64 = AtomicU64::new(0);

fn update_peak(peak: &AtomicU64, value: u64) {
    let mut current = peak.load(Ordering::Relaxed);
    while value > current {
        match peak.compare_exchange_weak(current, value, Ordering::Relaxed, Ordering::Relaxed) {
            Ok(_) => break,
            Err(observed) => current = observed,
        }
    }
}

fn gpu_error(context: &str, error: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(format!("{context}: {error}"))
}

#[pyclass(name = "GpuStorageBuffer", unsendable)]
pub(crate) struct GpuStorageBuffer {
    context: Arc<GpuDeviceContext>,
    buffer: Option<wgpu::Buffer>,
    size: usize,
    dtype: String,
}

#[pymethods]
impl GpuStorageBuffer {
    #[staticmethod]
    fn from_bytes(payload: Vec<u8>, size: usize, dtype: &str) -> PyResult<Self> {
        if !matches!(dtype, "float" | "int") {
            return Err(PyValueError::new_err(
                "GpuStorageBuffer dtype must be 'float' or 'int'.",
            ));
        }
        let expected = size
            .checked_mul(4)
            .ok_or_else(|| PyValueError::new_err("Storage buffer size is too large."))?;
        if payload.len() != expected {
            return Err(PyValueError::new_err(format!(
                "Storage buffer payload must contain {expected} bytes, got {}.",
                payload.len()
            )));
        }
        let context = GpuDeviceContext::process_shared().map_err(|error| {
            gpu_error(
                "Native WGPU storage buffers require an available non-fallback GPU adapter",
                error,
            )
        })?;
        let allocation_size = expected.max(4);
        if allocation_size as u64 > context.limits().max_buffer_size {
            return Err(PyValueError::new_err(format!(
                "Storage buffer requires {allocation_size} bytes, exceeding the adapter limit of {} bytes.",
                context.limits().max_buffer_size
            )));
        }
        let buffer = if payload.is_empty() {
            context.device().create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas empty storage buffer"),
                size: allocation_size as u64,
                usage: wgpu::BufferUsages::STORAGE
                    | wgpu::BufferUsages::COPY_DST
                    | wgpu::BufferUsages::COPY_SRC,
                mapped_at_creation: false,
            })
        } else {
            context
                .device()
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some("gummy_canvas storage buffer"),
                    contents: &payload,
                    usage: wgpu::BufferUsages::STORAGE
                        | wgpu::BufferUsages::COPY_DST
                        | wgpu::BufferUsages::COPY_SRC,
                })
        };
        STORAGE_ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        let current =
            STORAGE_CURRENT_BYTES.fetch_add(expected as u64, Ordering::Relaxed) + expected as u64;
        update_peak(&STORAGE_PEAK_BYTES, current);
        if expected > 0 {
            STORAGE_UPLOADS.fetch_add(1, Ordering::Relaxed);
            STORAGE_UPLOAD_BYTES.fetch_add(expected as u64, Ordering::Relaxed);
        }
        Ok(Self {
            context,
            buffer: Some(buffer),
            size,
            dtype: dtype.to_owned(),
        })
    }

    #[getter]
    fn size(&self) -> usize {
        self.size
    }

    #[getter]
    fn dtype(&self) -> &str {
        &self.dtype
    }

    #[getter]
    fn closed(&self) -> bool {
        self.buffer.is_none()
    }

    fn update_bytes(&self, payload: Vec<u8>, offset: usize) -> PyResult<()> {
        let buffer = self.open_buffer()?;
        if payload.len() % 4 != 0 {
            return Err(PyValueError::new_err(
                "Storage buffer updates must contain whole 32-bit elements.",
            ));
        }
        let byte_offset = offset
            .checked_mul(4)
            .ok_or_else(|| PyValueError::new_err("Storage buffer update offset is too large."))?;
        let end = byte_offset
            .checked_add(payload.len())
            .ok_or_else(|| PyValueError::new_err("Storage buffer update is too large."))?;
        if end > self.size * 4 {
            return Err(PyValueError::new_err(
                "Storage buffer update exceeds buffer size.",
            ));
        }
        if !payload.is_empty() {
            self.context
                .queue()
                .write_buffer(buffer, byte_offset as u64, &payload);
            STORAGE_UPLOADS.fetch_add(1, Ordering::Relaxed);
            STORAGE_UPLOAD_BYTES.fetch_add(payload.len() as u64, Ordering::Relaxed);
        }
        Ok(())
    }

    fn read_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let source = self.open_buffer()?;
        let byte_len = self.size * 4;
        if byte_len == 0 {
            return Ok(PyBytes::new_bound(py, &[]));
        }
        let staging = self
            .context
            .device()
            .create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas storage readback buffer"),
                size: byte_len as u64,
                usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
                mapped_at_creation: false,
            });
        let mut encoder =
            self.context
                .device()
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("gummy_canvas storage readback encoder"),
                });
        encoder.copy_buffer_to_buffer(source, 0, &staging, 0, byte_len as u64);
        self.context.queue().submit([encoder.finish()]);
        let slice = staging.slice(..byte_len as u64);
        let (sender, receiver) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |result| {
            let _ = sender.send(result);
        });
        self.context
            .device()
            .poll(wgpu::PollType::Wait)
            .map_err(|error| {
                gpu_error("Failed while waiting for storage-buffer readback", error)
            })?;
        receiver
            .recv()
            .map_err(|error| gpu_error("Failed to receive storage-buffer map status", error))?
            .map_err(|error| gpu_error("Failed to map storage buffer", error))?;
        let mapped = slice.get_mapped_range();
        let result = PyBytes::new_bound(py, &mapped);
        drop(mapped);
        staging.unmap();
        STORAGE_READBACKS.fetch_add(1, Ordering::Relaxed);
        STORAGE_READBACK_BYTES.fetch_add(byte_len as u64, Ordering::Relaxed);
        Ok(result)
    }

    fn close(&mut self) {
        self.release();
    }
}

impl GpuStorageBuffer {
    fn open_buffer(&self) -> PyResult<&wgpu::Buffer> {
        self.buffer
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("GpuStorageBuffer has been closed."))
    }

    fn release(&mut self) {
        if self.buffer.take().is_some() {
            STORAGE_DESTRUCTIONS.fetch_add(1, Ordering::Relaxed);
            STORAGE_CURRENT_BYTES.fetch_sub((self.size * 4) as u64, Ordering::Relaxed);
        }
    }
}

impl Drop for GpuStorageBuffer {
    fn drop(&mut self) {
        self.release();
    }
}

#[pyclass(name = "GpuComputeShader", unsendable)]
pub(crate) struct GpuComputeShader {
    context: Arc<GpuDeviceContext>,
    module: wgpu::ShaderModule,
    entry_point: String,
    label: Option<String>,
}

#[pymethods]
impl GpuComputeShader {
    #[staticmethod]
    #[pyo3(signature = (source, entry_point="main", label=None))]
    fn from_wgsl(source: &str, entry_point: &str, label: Option<String>) -> PyResult<Self> {
        if source.trim().is_empty() {
            return Err(PyValueError::new_err(
                "Compute shader WGSL source cannot be empty.",
            ));
        }
        if entry_point.trim().is_empty() {
            return Err(PyValueError::new_err(
                "Compute shader entry point cannot be empty.",
            ));
        }
        let context = GpuDeviceContext::process_shared().map_err(|error| {
            gpu_error(
                "Native WGPU compute requires an available non-fallback GPU adapter",
                error,
            )
        })?;
        context
            .device()
            .push_error_scope(wgpu::ErrorFilter::Validation);
        let module = context
            .device()
            .create_shader_module(wgpu::ShaderModuleDescriptor {
                label: label.as_deref().or(Some("gummy_canvas compute shader")),
                source: wgpu::ShaderSource::Wgsl(source.into()),
            });
        if let Some(error) = block_on(context.device().pop_error_scope()) {
            return Err(gpu_error(
                format!(
                    "Failed to compile WGSL compute shader{}",
                    label
                        .as_deref()
                        .map(|value| format!(" {value:?}"))
                        .unwrap_or_default()
                )
                .as_str(),
                error,
            ));
        }
        COMPUTE_SHADER_MODULES.fetch_add(1, Ordering::Relaxed);
        Ok(Self {
            context,
            module,
            entry_point: entry_point.to_owned(),
            label,
        })
    }

    #[pyo3(signature = (buffers, x, y=1, z=1))]
    fn dispatch(
        &self,
        buffers: Vec<PyRef<'_, GpuStorageBuffer>>,
        x: u32,
        y: u32,
        z: u32,
    ) -> PyResult<()> {
        if x == 0 || y == 0 || z == 0 {
            return Err(PyValueError::new_err(
                "Compute dispatch dimensions must be positive.",
            ));
        }
        if buffers.is_empty() {
            return Err(PyValueError::new_err(
                "Compute dispatch requires at least one storage buffer binding.",
            ));
        }
        if buffers.len() as u32 > self.context.limits().max_storage_buffers_per_shader_stage {
            return Err(PyValueError::new_err(format!(
                "Compute dispatch requests {} storage buffers, exceeding the adapter limit of {}.",
                buffers.len(),
                self.context.limits().max_storage_buffers_per_shader_stage
            )));
        }
        let layout_entries = (0..buffers.len())
            .map(|index| wgpu::BindGroupLayoutEntry {
                binding: index as u32,
                visibility: wgpu::ShaderStages::COMPUTE,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Storage { read_only: false },
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            })
            .collect::<Vec<_>>();
        let bind_group_layout =
            self.context
                .device()
                .create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
                    label: Some("gummy_canvas compute storage layout"),
                    entries: &layout_entries,
                });
        let pipeline_layout =
            self.context
                .device()
                .create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
                    label: Some("gummy_canvas compute pipeline layout"),
                    bind_group_layouts: &[&bind_group_layout],
                    push_constant_ranges: &[],
                });
        self.context
            .device()
            .push_error_scope(wgpu::ErrorFilter::Validation);
        let pipeline =
            self.context
                .device()
                .create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                    label: self
                        .label
                        .as_deref()
                        .or(Some("gummy_canvas compute pipeline")),
                    layout: Some(&pipeline_layout),
                    module: &self.module,
                    entry_point: Some(&self.entry_point),
                    compilation_options: wgpu::PipelineCompilationOptions::default(),
                    cache: None,
                });
        if let Some(error) = block_on(self.context.device().pop_error_scope()) {
            return Err(gpu_error(
                format!(
                    "Failed to create compute pipeline for entry point {:?}",
                    self.entry_point
                )
                .as_str(),
                error,
            ));
        }
        let mut bind_entries = Vec::with_capacity(buffers.len());
        for (index, buffer) in buffers.iter().enumerate() {
            bind_entries.push(wgpu::BindGroupEntry {
                binding: index as u32,
                resource: buffer.open_buffer()?.as_entire_binding(),
            });
        }
        let bind_group = self
            .context
            .device()
            .create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("gummy_canvas compute bind group"),
                layout: &bind_group_layout,
                entries: &bind_entries,
            });
        let mut encoder =
            self.context
                .device()
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("gummy_canvas compute encoder"),
                });
        {
            let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor {
                label: Some("gummy_canvas compute pass"),
                timestamp_writes: None,
            });
            pass.set_pipeline(&pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.dispatch_workgroups(x, y, z);
        }
        self.context.queue().submit([encoder.finish()]);
        self.context
            .device()
            .poll(wgpu::PollType::Wait)
            .map_err(|error| gpu_error("Failed while waiting for compute dispatch", error))?;
        COMPUTE_PIPELINES.fetch_add(1, Ordering::Relaxed);
        COMPUTE_BIND_GROUPS.fetch_add(1, Ordering::Relaxed);
        COMPUTE_DISPATCHES.fetch_add(1, Ordering::Relaxed);
        COMPUTE_WORKGROUPS.fetch_add(
            u64::from(x) * u64::from(y) * u64::from(z),
            Ordering::Relaxed,
        );
        Ok(())
    }
}

#[pyfunction]
pub(crate) fn webgpu_context_info<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let context = GpuDeviceContext::process_shared().map_err(|error| {
        gpu_error(
            "Native WGPU resources require an available non-fallback GPU adapter",
            error,
        )
    })?;
    let info = context.adapter().get_info();
    let result = PyDict::new_bound(py);
    result.set_item("backend", format!("{:?}", info.backend).to_lowercase())?;
    result.set_item("adapter", info.name)?;
    result.set_item("native_gpu", true)?;
    result.set_item("storage_buffers", true)?;
    result.set_item("compute_shaders", true)?;
    result.set_item("browser_context", false)?;
    result.set_item("max_buffer_size", context.limits().max_buffer_size)?;
    result.set_item(
        "max_storage_buffers_per_shader_stage",
        context.limits().max_storage_buffers_per_shader_stage,
    )?;
    Ok(result)
}

#[pyfunction]
pub(crate) fn gpu_resource_diagnostics<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new_bound(py);
    for (name, counter) in [
        ("storage_buffer_allocations", &STORAGE_ALLOCATIONS),
        ("storage_buffer_destructions", &STORAGE_DESTRUCTIONS),
        ("storage_buffer_current_bytes", &STORAGE_CURRENT_BYTES),
        ("storage_buffer_peak_bytes", &STORAGE_PEAK_BYTES),
        ("storage_buffer_uploads", &STORAGE_UPLOADS),
        ("storage_buffer_upload_bytes", &STORAGE_UPLOAD_BYTES),
        ("storage_buffer_readbacks", &STORAGE_READBACKS),
        ("storage_buffer_readback_bytes", &STORAGE_READBACK_BYTES),
        ("compute_shader_modules", &COMPUTE_SHADER_MODULES),
        ("compute_pipelines", &COMPUTE_PIPELINES),
        ("compute_bind_groups", &COMPUTE_BIND_GROUPS),
        ("compute_dispatches", &COMPUTE_DISPATCHES),
        ("compute_workgroups", &COMPUTE_WORKGROUPS),
    ] {
        result.set_item(name, counter.load(Ordering::Relaxed))?;
    }
    Ok(result)
}

#[pyfunction]
pub(crate) fn reset_gpu_resource_diagnostics() {
    for counter in [
        &STORAGE_ALLOCATIONS,
        &STORAGE_DESTRUCTIONS,
        &STORAGE_PEAK_BYTES,
        &STORAGE_UPLOADS,
        &STORAGE_UPLOAD_BYTES,
        &STORAGE_READBACKS,
        &STORAGE_READBACK_BYTES,
        &COMPUTE_SHADER_MODULES,
        &COMPUTE_PIPELINES,
        &COMPUTE_BIND_GROUPS,
        &COMPUTE_DISPATCHES,
        &COMPUTE_WORKGROUPS,
    ] {
        counter.store(0, Ordering::Relaxed);
    }
    STORAGE_PEAK_BYTES.store(
        STORAGE_CURRENT_BYTES.load(Ordering::Relaxed),
        Ordering::Relaxed,
    );
}
