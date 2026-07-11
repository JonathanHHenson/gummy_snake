use crate::prelude::*;

impl Canvas {
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
}
