use crate::prelude::*;

impl Canvas {
    pub(crate) fn dimensions_impl(&self) -> (i64, i64, usize, usize, f64) {
        (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )
    }

    pub(crate) fn display_density_impl(&self) -> f64 {
        if let Some(runtime) = self.runtime.as_ref() {
            runtime.display_density()
        } else if self.window_open {
            self.pixel_density.max(1.0)
        } else {
            1.0
        }
    }

    pub(crate) fn native_window_available_impl(&self) -> bool {
        runtime_native_window_available()
    }

    pub(crate) fn gpu_available_impl(&self) -> bool {
        self.gpu.is_some()
    }

    pub(crate) fn gpu_status_impl(&self) -> String {
        self.gpu_error
            .clone()
            .unwrap_or_else(|| "available".to_string())
    }

    pub(crate) fn performance_counters_impl<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let dict = self.performance_counters.to_dict(py)?;
        if let Some(gpu) = self.gpu.as_ref() {
            let gpu_counters = gpu.render_loop_counters();
            dict.set_item(
                "gpu_vertex_buffer_allocations",
                gpu_counters.vertex_buffer_allocations,
            )?;
            dict.set_item("gpu_vertex_uploads", gpu_counters.vertex_uploads)?;
            dict.set_item(
                "gpu_uploaded_vertex_bytes",
                gpu_counters.uploaded_vertex_bytes,
            )?;
            dict.set_item("gpu_primitive_batches", gpu_counters.primitive_batches)?;
            dict.set_item("gpu_image_batches", gpu_counters.image_batches)?;
            dict.set_item("gpu_encode_time_ms", gpu_counters.encode_time_ms)?;
            dict.set_item(
                "retained_batch_cache_hits",
                gpu_counters.retained_batch_cache_hits,
            )?;
            dict.set_item(
                "retained_batch_cache_misses",
                gpu_counters.retained_batch_cache_misses,
            )?;
            dict.set_item(
                "retained_batch_reused_bytes",
                gpu_counters.retained_batch_reused_bytes,
            )?;
            dict.set_item(
                "retained_batch_cache_evictions",
                gpu_counters.retained_batch_cache_evictions,
            )?;
            dict.set_item("gpu_command_clone_count", gpu_counters.command_clone_count)?;
            dict.set_item("gpu_command_clone_bytes", gpu_counters.command_clone_bytes)?;
            dict.set_item(
                "gpu_command_segment_allocation_count",
                gpu_counters.command_segment_allocation_count,
            )?;
        }
        Ok(dict)
    }

    pub(crate) fn reset_performance_counters_impl(&mut self) {
        self.performance_counters = PerformanceCounters::default();
        let image_resident = self.image_cache.resident_bytes() as u64;
        self.performance_counters.image_cache_resident_bytes = image_resident;
        self.performance_counters.image_cache_peak_bytes = image_resident;
        self.update_texture_cache_byte_counters();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.reset_render_loop_counters();
        }
    }
}
