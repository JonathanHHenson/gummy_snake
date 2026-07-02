use crate::*;
use pyo3::buffer::PyBuffer;

impl Canvas {
    pub(crate) fn update_pixels_impl(&mut self, pixels: Vec<u8>) -> PyResult<()> {
        self.performance_counters.pixel_payload_copies += 1;
        self.update_pixels_from_slice(&pixels)
    }

    pub(crate) fn update_pixel_buffer_impl(
        &mut self,
        py: Python<'_>,
        pixels: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        with_u8_buffer(py, pixels, |payload| self.update_pixels_from_slice(payload))
    }

    fn update_pixels_from_slice(&mut self, pixels: &[u8]) -> PyResult<()> {
        self.performance_counters.pixel_uploads += 1;
        let expected = self.physical_width * self.physical_height * 4;
        if pixels.len() != expected {
            return Err(PyValueError::new_err(format!(
                "Pixel buffer length must be {expected}, got {}.",
                pixels.len()
            )));
        }
        if pixels == self.pixels {
            self.performance_counters.pixel_noop_upload_skips += 1;
            return Ok(());
        }
        self.performance_counters.pixel_full_uploads += 1;
        self.pixels.clear();
        self.pixels.extend_from_slice(pixels);
        self.sync_present_pixels_from_rgba();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.mark_cpu_pixels_uploaded();
        Ok(())
    }

    pub(crate) fn set_pixel_rgba_impl(
        &mut self,
        x: i64,
        y: i64,
        _rgba: (u8, u8, u8, u8),
    ) -> PyResult<()> {
        if let Some(runtime) = self.runtime.as_mut() {
            let _ = runtime.pump_events();
            if runtime.should_close() {
                self.closed = true;
            }
        }
        if x < 0 || y < 0 || x >= self.physical_width as i64 || y >= self.physical_height as i64 {
            return Ok(());
        }
        self.prepare_cpu_composite()
    }

    pub(crate) fn update_pixel_region_impl(
        &mut self,
        pixels: Vec<u8>,
        width: usize,
        height: usize,
        x: i64,
        y: i64,
        alpha_composite: bool,
    ) -> PyResult<()> {
        self.performance_counters.pixel_payload_copies += 1;
        self.update_pixel_region_from_slice(&pixels, width, height, x, y, alpha_composite)
    }

    pub(crate) fn update_pixel_region_buffer_impl(
        &mut self,
        py: Python<'_>,
        pixels: &Bound<'_, PyAny>,
        width: usize,
        height: usize,
        x: i64,
        y: i64,
        alpha_composite: bool,
    ) -> PyResult<()> {
        with_u8_buffer(py, pixels, |payload| {
            self.update_pixel_region_from_slice(payload, width, height, x, y, alpha_composite)
        })
    }

    fn update_pixel_region_from_slice(
        &mut self,
        pixels: &[u8],
        width: usize,
        height: usize,
        _x: i64,
        _y: i64,
        _alpha_composite: bool,
    ) -> PyResult<()> {
        validate_rgba_buffer(pixels.len(), width, height)?;
        self.prepare_cpu_composite()
    }

    pub(crate) fn adjust_pixel_prefix_impl(
        &mut self,
        byte_limit: usize,
        stride: usize,
        red_delta: i16,
        green_delta: i16,
    ) -> PyResult<()> {
        if byte_limit == 0 || stride == 0 {
            return Ok(());
        }
        let pixel_count =
            ((byte_limit.min(self.physical_width * self.physical_height * 4)) + 3) / 4;
        if pixel_count == 0 {
            return Ok(());
        }
        if self.gpu.is_some() {
            if self.texture_stale {
                self.upload_stale_texture(false)?;
            }
            if let Some(gpu) = self.gpu.as_mut() {
                gpu.draw_pixel_prefix_mutation(
                    byte_limit.min(self.physical_width * self.physical_height * 4) as u32,
                    stride as u32,
                    i32::from(red_delta),
                    i32::from(green_delta),
                );
                self.record_native_region_effect_draw(false);
                return Ok(());
            }
        }
        self.prepare_cpu_composite()
    }
}

fn with_u8_buffer<T>(
    py: Python<'_>,
    pixels: &Bound<'_, PyAny>,
    upload: impl FnOnce(&[u8]) -> PyResult<T>,
) -> PyResult<T> {
    let buffer = PyBuffer::<u8>::get_bound(pixels)?;
    let cells = buffer
        .as_slice(py)
        .ok_or_else(|| PyValueError::new_err("Pixel buffers must be C-contiguous bytes."))?;
    let payload = unsafe { std::slice::from_raw_parts(cells.as_ptr() as *const u8, cells.len()) };
    upload(payload)
}
