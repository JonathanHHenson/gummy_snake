use crate::*;
use image::codecs::gif::{GifEncoder, Repeat};
use image::{Delay, Frame, RgbaImage};
use std::fs::File;
use std::io::BufWriter;

impl Canvas {
    pub(crate) fn filter_pixels_impl(&mut self, _mode: &str, _value: Option<f64>) -> PyResult<()> {
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
    }
}
