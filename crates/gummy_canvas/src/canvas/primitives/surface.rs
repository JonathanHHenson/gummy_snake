use crate::*;

impl Canvas {
    pub(crate) fn background_impl(&mut self, rgba: (u8, u8, u8, u8)) -> PyResult<()> {
        self.pending_3d_triangles.clear();
        self.erase_color = Rgba::from_tuple(rgba);
        if !self.clip_masks.is_empty() {
            if self.gpu.is_some() && !self.cpu_compositing_active {
                self.draw_gpu_transformed_rect(
                    0.0,
                    0.0,
                    self.physical_width as f64,
                    self.physical_height as f64,
                    (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                    1.0,
                    Rgba::from_tuple(rgba),
                    BlendMode::Blend,
                )?;
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.set_clear_color(crate::raster::gpu_color(Rgba::from_tuple(rgba)));
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
            Ok(())
        } else {
            self.prepare_cpu_composite()
        }
    }

    pub(crate) fn clear_impl(&mut self) -> PyResult<()> {
        self.pending_3d_triangles.clear();
        if !self.clip_masks.is_empty() {
            if self.gpu.is_some() && !self.cpu_compositing_active {
                self.draw_gpu_erase_transformed_rect(
                    0.0,
                    0.0,
                    self.physical_width as f64,
                    self.physical_height as f64,
                    (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                    1.0,
                )?;
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.clear_transparent();
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
            Ok(())
        } else {
            self.prepare_cpu_composite()
        }
    }
}
