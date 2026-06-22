use crate::runtime::style::*;
use crate::*;
use pyo3::buffer::PyBuffer;

impl Canvas {
    pub(crate) fn blend_region_impl(
        &mut self,
        source_pixels: Option<Vec<u8>>,
        source_width: Option<usize>,
        source_height: Option<usize>,
        source: (i64, i64, i64, i64),
        destination: (i64, i64, i64, i64),
        mode: &str,
    ) -> PyResult<()> {
        ensure_supported_blend_mode(mode)?;
        let (dest_x, dest_y, dest_w, dest_h) = scale_rect(destination, self.pixel_density);
        if dest_w <= 0 || dest_h <= 0 {
            return Ok(());
        }
        self.prepare_cpu_composite();
        let source_owned;
        let (source_data, source_canvas_width, source_canvas_height, source_rect) =
            if let Some(pixels) = source_pixels {
                let width = source_width.ok_or_else(|| {
                    PyValueError::new_err("External blend source width is required.")
                })?;
                let height = source_height.ok_or_else(|| {
                    PyValueError::new_err("External blend source height is required.")
                })?;
                validate_rgba_buffer(pixels.len(), width, height)?;
                source_owned = pixels;
                (&source_owned[..], width, height, source)
            } else {
                (
                    &self.pixels[..],
                    self.physical_width,
                    self.physical_height,
                    scale_rect(source, self.pixel_density),
                )
            };
        let Some((sx, sy, sw, sh)) =
            clipped_source_rect(source_rect, source_canvas_width, source_canvas_height)
        else {
            return Ok(());
        };
        let Some((dx, dy, dw, dh)) = clipped_dest_rect(
            (dest_x, dest_y, dest_w, dest_h),
            self.physical_width,
            self.physical_height,
        ) else {
            return Ok(());
        };
        let sampled = source_data.to_vec();
        blit_scaled_region(
            &mut self.pixels,
            &mut self.present_pixels,
            self.physical_width,
            &sampled,
            source_canvas_width,
            sx,
            sy,
            sw,
            sh,
            dx,
            dy,
            dw,
            dh,
            false,
            mode,
            "linear",
            self.clip_masks.last().map(Vec::as_slice),
        );
        self.upload_cpu_pixels()?;
        Ok(())
    }
    pub(crate) fn load_pixels_impl(&mut self) -> Vec<u8> {
        self.performance_counters.pixel_readbacks += 1;
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.pixels.clone()
    }

    pub(crate) fn load_pixel_bytes_impl<'py>(&mut self, py: Python<'py>) -> Bound<'py, PyBytes> {
        self.performance_counters.pixel_readbacks += 1;
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
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
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        let region = crop_rgba_with_padding(
            &self.pixels,
            self.physical_width,
            self.physical_height,
            x,
            y,
            width as usize,
            height as usize,
        );
        Ok(PyBytes::new_bound(py, &region))
    }

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
            return Ok(());
        }
        self.pixels.clear();
        self.pixels.extend_from_slice(pixels);
        self.sync_present_pixels_from_rgba();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = true;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = true;
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
        self.prepare_cpu_composite();
        let pixel_index = y as usize * self.physical_width + x as usize;
        let offset = pixel_index * 4;
        let color = [rgba.0, rgba.1, rgba.2, rgba.3];
        self.pixels[offset..offset + 4].copy_from_slice(&color);
        self.present_pixels[pixel_index] = rgba_to_present_pixel(&color);
        self.render_dirty = true;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = true;
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
        self.performance_counters.pixel_uploads += 1;
        self.prepare_cpu_composite();
        if alpha_composite {
            alpha_composite_rgba_region(
                &mut self.pixels,
                self.physical_width,
                self.physical_height,
                &pixels,
                width,
                height,
                x,
                y,
            );
        } else {
            replace_rgba_region(
                &mut self.pixels,
                self.physical_width,
                self.physical_height,
                &pixels,
                width,
                height,
                x,
                y,
            );
        }
        self.sync_present_pixel_region(x, y, width, height);
        self.upload_cpu_pixels()?;
        Ok(())
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
        let region_width = pixel_count.min(self.physical_width);
        let region_height = pixel_count.div_ceil(self.physical_width);
        if self.gpu.is_some() {
            if self.offscreen_dirty {
                self.render_gpu_frame(false);
            } else if self.texture_stale {
                self.upload_stale_texture(false)?;
            }
            if let Some(gpu) = self.gpu.as_mut() {
                gpu.apply_pixel_prefix_mutation(
                    byte_limit.min(self.physical_width * self.physical_height * 4) as u32,
                    stride as u32,
                    i32::from(red_delta),
                    i32::from(green_delta),
                );
                self.performance_counters.gpu_region_effect_passes += 1;
                self.render_dirty = true;
                self.offscreen_dirty = false;
                self.pixels_stale = true;
                self.texture_stale = false;
                return Ok(());
            }
        }
        if self.pixels_stale {
            self.read_gpu_pixels();
        }
        let mut region = crop_rgba_with_padding(
            &self.pixels,
            self.physical_width,
            self.physical_height,
            0,
            0,
            region_width,
            region_height,
        );
        for offset in (0..byte_limit.min(region.len())).step_by(stride) {
            region[offset] = (i16::from(region[offset]) + red_delta).rem_euclid(256) as u8;
            if offset + 1 < region.len() {
                region[offset + 1] =
                    (i16::from(region[offset + 1]) + green_delta).rem_euclid(256) as u8;
            }
        }
        self.update_pixel_region_impl(region, region_width, region_height, 0, 0, false)
    }

    pub(crate) fn filter_pixels_impl(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        self.performance_counters.cpu_fallbacks += 1;
        self.performance_counters.pixel_uploads += 1;
        self.prepare_cpu_composite();
        filter_rgba(&mut self.pixels, mode, value)?;
        self.sync_present_pixels_from_rgba();
        self.upload_cpu_pixels()?;
        Ok(())
    }

    pub(crate) fn save_impl(&mut self, path: &str) -> PyResult<()> {
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        image::save_buffer_with_format(
            path,
            &self.pixels,
            self.physical_width as u32,
            self.physical_height as u32,
            image::ColorType::Rgba8,
            image::ImageFormat::Png,
        )
        .map_err(|err| PyValueError::new_err(format!("Failed to save canvas: {err}")))
    }

    fn sync_present_pixel_region(&mut self, x: i64, y: i64, width: usize, height: usize) {
        let start_x = x.max(0) as usize;
        let start_y = y.max(0) as usize;
        let end_x = ((x + width as i64).max(0) as usize).min(self.physical_width);
        let end_y = ((y + height as i64).max(0) as usize).min(self.physical_height);
        if start_x >= end_x || start_y >= end_y {
            return;
        }
        for row in start_y..end_y {
            let pixel_start = row * self.physical_width + start_x;
            let pixel_end = row * self.physical_width + end_x;
            for index in pixel_start..pixel_end {
                let offset = index * 4;
                self.present_pixels[index] =
                    rgba_to_present_pixel(&self.pixels[offset..offset + 4]);
            }
        }
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
