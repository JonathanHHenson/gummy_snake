use super::*;
use crate::runtime_style::*;

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
        self.performance_counters.pixel_uploads += 1;
        let expected = self.physical_width * self.physical_height * 4;
        if pixels.len() != expected {
            return Err(PyValueError::new_err(format!(
                "Pixel buffer length must be {expected}, got {}.",
                pixels.len()
            )));
        }
        self.pixels = pixels;
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

    pub(crate) fn update_pixel_region_impl(
        &mut self,
        pixels: Vec<u8>,
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
        self.sync_present_pixels_from_rgba();
        self.upload_cpu_pixels()?;
        Ok(())
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
}
