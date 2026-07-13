use crate::prelude::*;
use image::codecs::gif::{GifEncoder, Repeat};
use image::{Delay, Frame, RgbaImage};
use std::fs::File;
use std::io::BufWriter;

impl Canvas {
    pub(crate) fn filter_pixels_impl(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        let filter_mode = pixel_filter_mode(mode)?;
        if self.texture_stale {
            self.upload_stale_texture(false)?;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_pixel_filter(filter_mode, pixel_filter_value(mode, value));
            self.record_native_region_effect_draw(false);
            return Ok(());
        }
        self.prepare_cpu_composite()
    }

    pub(crate) fn save_impl(&mut self, path: &str) -> PyResult<()> {
        self.prepare_pixels_for_export();
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

    pub(crate) fn save_gif_impl(
        &mut self,
        path: &str,
        count: usize,
        frame_duration_ms: u32,
    ) -> PyResult<()> {
        if count == 0 {
            return Err(PyValueError::new_err("save_gif() count must be positive."));
        }
        if self.physical_width == 0 || self.physical_height == 0 {
            return Err(PyValueError::new_err(
                "save_gif() requires a non-empty canvas.",
            ));
        }
        self.prepare_pixels_for_export();
        let file = File::create(path)
            .map_err(|err| PyValueError::new_err(format!("Failed to create GIF {path}: {err}")))?;
        let writer = BufWriter::new(file);
        let mut encoder = GifEncoder::new(writer);
        encoder.set_repeat(Repeat::Infinite).map_err(|err| {
            PyValueError::new_err(format!("Failed to configure GIF {path}: {err}"))
        })?;
        let delay = Delay::from_numer_denom_ms(frame_duration_ms, 1);
        for _ in 0..count {
            let image = RgbaImage::from_raw(
                self.physical_width as u32,
                self.physical_height as u32,
                self.pixels.clone(),
            )
            .ok_or_else(|| PyValueError::new_err("Canvas pixel buffer has invalid dimensions."))?;
            encoder
                .encode_frame(Frame::from_parts(image, 0, 0, delay))
                .map_err(|err| {
                    PyValueError::new_err(format!("Failed to encode GIF {path}: {err}"))
                })?;
        }
        Ok(())
    }

    fn prepare_pixels_for_export(&mut self) {
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.ensure_cpu_pixel_buffer();
    }
}

fn pixel_filter_mode(mode: &str) -> PyResult<u32> {
    match mode {
        "gray" => Ok(1),
        "invert" => Ok(2),
        "threshold" => Ok(3),
        "blur" => Ok(4),
        "posterize" => Ok(5),
        "erode" => Ok(6),
        "dilate" => Ok(7),
        _ => Err(PyValueError::new_err(format!(
            "Unsupported image filter {mode:?}."
        ))),
    }
}

fn pixel_filter_value(mode: &str, value: Option<f64>) -> f32 {
    match mode {
        "threshold" => value.unwrap_or(0.5).clamp(0.0, 1.0) as f32,
        "posterize" => value.unwrap_or(4.0).clamp(2.0, 255.0) as f32,
        _ => value.unwrap_or(0.0) as f32,
    }
}
