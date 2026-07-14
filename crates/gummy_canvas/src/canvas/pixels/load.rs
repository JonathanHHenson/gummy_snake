use crate::canvas_state::Canvas;
use crate::images::crop_rgba_with_padding;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

impl Canvas {
    pub(crate) fn ensure_cpu_pixel_buffer(&mut self) {
        if self.pixels.is_empty() {
            self.pixels = vec![0; self.physical_width * self.physical_height * 4];
        }
    }

    pub(crate) fn ensure_present_pixel_buffer(&mut self) {
        if self.present_pixels.is_empty() {
            self.present_pixels = vec![0; self.physical_width * self.physical_height];
        }
    }

    pub(crate) fn load_pixels_impl(&mut self) -> Vec<u8> {
        self.performance_counters.pixel_readbacks += 1;
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.ensure_cpu_pixel_buffer();
        let byte_count = self.pixels.len() as u64;
        self.performance_counters.pixel_readback_requested_bytes += byte_count;
        self.performance_counters.pixel_readback_copied_bytes += byte_count;
        self.pixels.clone()
    }

    pub(crate) fn load_pixel_bytes_impl<'py>(&mut self, py: Python<'py>) -> Bound<'py, PyBytes> {
        self.performance_counters.pixel_readbacks += 1;
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.ensure_cpu_pixel_buffer();
        let byte_count = self.pixels.len() as u64;
        self.performance_counters.pixel_readback_requested_bytes += byte_count;
        self.performance_counters.pixel_readback_copied_bytes += byte_count;
        self.performance_counters.pixel_bytes_created += 1;
        PyBytes::new_bound(py, &self.pixels)
    }

    pub(crate) fn load_pixel_region_impl<'py>(
        &mut self,
        py: Python<'py>,
        x: i64,
        y: i64,
        width: i64,
        height: i64,
    ) -> PyResult<Bound<'py, PyBytes>> {
        if width <= 0 || height <= 0 {
            return Err(PyValueError::new_err(
                "Pixel region dimensions must be positive.",
            ));
        }
        self.performance_counters.pixel_readbacks += 1;
        let requested_bytes = (width as u64)
            .checked_mul(height as u64)
            .and_then(|pixels| pixels.checked_mul(4))
            .ok_or_else(|| PyValueError::new_err("Pixel region byte length is too large."))?;
        let region = if self.pixels_stale && self.gpu.is_some() {
            self.flush_pending_3d_triangles();
            let encode_render = self.offscreen_dirty;
            let result = self
                .gpu
                .as_mut()
                .expect("GPU availability checked before region readback")
                .read_pixel_region(x, y, width as usize, height as usize, encode_render)
                .map_err(|error| {
                    PyValueError::new_err(format!("GPU pixel-region readback failed: {error}"))
                })?;
            self.performance_counters.gpu_pixel_readbacks += 1;
            if encode_render {
                self.performance_counters.gpu_frames_rendered += 1;
                if let Some(gpu) = self.gpu.as_mut() {
                    gpu.begin_frame();
                }
                self.mark_gpu_rendered_without_readback();
            }
            result
        } else {
            self.ensure_cpu_pixel_buffer();
            crop_rgba_with_padding(
                &self.pixels,
                self.physical_width,
                self.physical_height,
                x,
                y,
                width as usize,
                height as usize,
            )
        };
        self.performance_counters.pixel_readback_requested_bytes += requested_bytes;
        self.performance_counters.pixel_readback_copied_bytes += region.len() as u64;
        self.performance_counters.pixel_bytes_created += 1;
        Ok(PyBytes::new_bound(py, &region))
    }
}
