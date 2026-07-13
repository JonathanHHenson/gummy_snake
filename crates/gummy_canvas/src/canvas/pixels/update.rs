use crate::prelude::*;
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
        if pixels == self.pixels || (self.pixels.is_empty() && pixels.iter().all(|&byte| byte == 0))
        {
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
        rgba: (u8, u8, u8, u8),
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
        self.sync_pixels_for_explicit_pixel_write();
        self.ensure_present_pixel_buffer();
        let offset = (y as usize * self.physical_width + x as usize) * 4;
        self.pixels[offset] = rgba.0;
        self.pixels[offset + 1] = rgba.1;
        self.pixels[offset + 2] = rgba.2;
        self.pixels[offset + 3] = rgba.3;
        self.present_pixels[y as usize * self.physical_width + x as usize] =
            rgba_to_present_pixel(&self.pixels[offset..offset + 4]);
        self.performance_counters.pixel_region_uploads += 1;
        self.mark_cpu_pixels_uploaded();
        Ok(())
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
        x: i64,
        y: i64,
        alpha_composite: bool,
    ) -> PyResult<()> {
        validate_rgba_buffer(pixels.len(), width, height)?;
        if width == 0 || height == 0 {
            return Ok(());
        }
        let Some((src_x, src_y, dst_x, dst_y, copy_width, copy_height)) = clipped_region(
            width,
            height,
            self.physical_width,
            self.physical_height,
            x,
            y,
        ) else {
            return Ok(());
        };
        self.sync_pixels_for_explicit_pixel_write();
        self.ensure_present_pixel_buffer();
        for row in 0..copy_height {
            let source_offset = ((src_y + row) * width + src_x) * 4;
            let destination_offset = ((dst_y + row) * self.physical_width + dst_x) * 4;
            let byte_count = copy_width * 4;
            if alpha_composite {
                for column in 0..copy_width {
                    let source = source_offset + column * 4;
                    let destination = destination_offset + column * 4;
                    alpha_blend_pixel(
                        &mut self.pixels[destination..destination + 4],
                        &pixels[source..source + 4],
                    );
                    self.present_pixels[(dst_y + row) * self.physical_width + dst_x + column] =
                        rgba_to_present_pixel(&self.pixels[destination..destination + 4]);
                }
            } else {
                self.pixels[destination_offset..destination_offset + byte_count]
                    .copy_from_slice(&pixels[source_offset..source_offset + byte_count]);
                for column in 0..copy_width {
                    let destination = destination_offset + column * 4;
                    self.present_pixels[(dst_y + row) * self.physical_width + dst_x + column] =
                        rgba_to_present_pixel(&self.pixels[destination..destination + 4]);
                }
            }
        }
        self.performance_counters.pixel_region_uploads += 1;
        self.mark_cpu_pixels_uploaded();
        Ok(())
    }

    fn sync_pixels_for_explicit_pixel_write(&mut self) {
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.ensure_cpu_pixel_buffer();
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
            (byte_limit.min(self.physical_width * self.physical_height * 4)).div_ceil(4);
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

fn clipped_region(
    source_width: usize,
    source_height: usize,
    destination_width: usize,
    destination_height: usize,
    x: i64,
    y: i64,
) -> Option<(usize, usize, usize, usize, usize, usize)> {
    let dst_x = x.max(0) as usize;
    let dst_y = y.max(0) as usize;
    let src_x = if x < 0 { (-x) as usize } else { 0 };
    let src_y = if y < 0 { (-y) as usize } else { 0 };
    if src_x >= source_width
        || src_y >= source_height
        || dst_x >= destination_width
        || dst_y >= destination_height
    {
        return None;
    }
    let copy_width = (source_width - src_x).min(destination_width - dst_x);
    let copy_height = (source_height - src_y).min(destination_height - dst_y);
    if copy_width == 0 || copy_height == 0 {
        return None;
    }
    Some((src_x, src_y, dst_x, dst_y, copy_width, copy_height))
}

fn alpha_blend_pixel(destination: &mut [u8], source: &[u8]) {
    let src_alpha = source[3] as f32 / 255.0;
    let dst_alpha = destination[3] as f32 / 255.0;
    let out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha);
    if out_alpha <= 0.0 {
        destination.copy_from_slice(&[0, 0, 0, 0]);
        return;
    }
    for channel in 0..3 {
        let src = source[channel] as f32 / 255.0;
        let dst = destination[channel] as f32 / 255.0;
        let out = (src * src_alpha + dst * dst_alpha * (1.0 - src_alpha)) / out_alpha;
        destination[channel] = (out * 255.0).round().clamp(0.0, 255.0) as u8;
    }
    destination[3] = (out_alpha * 255.0).round().clamp(0.0, 255.0) as u8;
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
