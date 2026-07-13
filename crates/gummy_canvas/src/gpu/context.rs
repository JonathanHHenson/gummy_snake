//! Shared immutable WGPU infrastructure for canvas renderers.
//!
//! A context owns the WGPU instance, selected adapter, device, and queue. It is
//! reference counted so renderers may share one device without sharing mutable
//! canvas targets, command streams, caches, or presentation surfaces. Device
//! loss and process-local lifecycle management remain outside this first
//! extraction; this type intentionally does not create replacement devices.

use std::sync::{Arc, Mutex, OnceLock};

use pollster::block_on;

static PROCESS_DEVICE_CONTEXT: OnceLock<Mutex<Option<Arc<GpuDeviceContext>>>> = OnceLock::new();

/// Immutable WGPU infrastructure that may be shared by GPU renderers.
pub(super) struct GpuDeviceContext {
    instance: wgpu::Instance,
    adapter: wgpu::Adapter,
    device: wgpu::Device,
    queue: wgpu::Queue,
    limits: wgpu::Limits,
}

impl GpuDeviceContext {
    /// Return the process-local WGPU context, creating it once without a fallback adapter.
    pub(super) fn process_shared() -> Result<Arc<Self>, String> {
        let slot = PROCESS_DEVICE_CONTEXT.get_or_init(|| Mutex::new(None));
        let mut guard = slot
            .lock()
            .map_err(|_| "gummy_canvas GPU device context lock was poisoned.".to_owned())?;
        if let Some(context) = guard.as_ref() {
            return Ok(Arc::clone(context));
        }
        let context = Self::new()?;
        *guard = Some(Arc::clone(&context));
        Ok(context)
    }

    /// Creates one explicit WGPU device context without selecting a fallback adapter.
    pub(super) fn new() -> Result<Arc<Self>, String> {
        let instance = wgpu::Instance::default();
        let adapter = block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .map_err(|err| format!("No supported GPU adapter is available for gummy_canvas: {err}"))?;
        let limits = adapter.limits();
        let (device, queue) = block_on(adapter.request_device(&wgpu::DeviceDescriptor {
            label: Some("gummy_canvas device"),
            required_features: wgpu::Features::empty(),
            required_limits: limits.clone(),
            memory_hints: wgpu::MemoryHints::Performance,
            trace: wgpu::Trace::Off,
        }))
        .map_err(|err| format!("Failed to create GPU device for gummy_canvas: {err}"))?;

        Ok(Arc::new(Self {
            instance,
            adapter,
            device,
            queue,
            limits,
        }))
    }

    pub(super) fn instance(&self) -> &wgpu::Instance {
        &self.instance
    }

    pub(super) fn adapter(&self) -> &wgpu::Adapter {
        &self.adapter
    }

    pub(super) fn device(&self) -> &wgpu::Device {
        &self.device
    }

    pub(super) fn queue(&self) -> &wgpu::Queue {
        &self.queue
    }

    pub(super) fn limits(&self) -> &wgpu::Limits {
        &self.limits
    }

    pub(super) fn adapter_info() -> Option<wgpu::AdapterInfo> {
        let instance = wgpu::Instance::default();
        block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: None,
            force_fallback_adapter: false,
        }))
        .ok()
        .map(|adapter| adapter.get_info())
    }
}
