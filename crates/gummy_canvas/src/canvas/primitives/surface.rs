use crate::*;

impl Canvas {
    pub(crate) fn background_impl(&mut self, rgba: (u8, u8, u8, u8)) {
        self.pending_3d_triangles.clear();
        self.erase_color = Rgba::from_tuple(rgba);
        let color = self.erase_color.as_array();
        if !self.clip_masks.is_empty() {
            if self.gpu.is_some() && !self.cpu_compositing_active {
                let fill = Rgba::from_tuple(rgba);
                let width = self.physical_width as f64;
                let height = self.physical_height as f64;
                let mut vertices = Vec::with_capacity(6);
                push_triangle(
                    &mut vertices,
                    (0.0, 0.0),
                    (width, 0.0),
                    (width, height),
                    fill,
                );
                push_triangle(
                    &mut vertices,
                    (0.0, 0.0),
                    (width, height),
                    (0.0, height),
                    fill,
                );
                let _ = self.draw_gpu_triangles(vertices, BlendMode::Blend);
                return;
            }
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            let (min_x, min_y, max_x, max_y) = self.clip_bounds.last().copied().unwrap_or((
                0,
                0,
                self.physical_width,
                self.physical_height,
            ));
            let packed = rgba_to_present_pixel(&color);
            for y in min_y..max_y {
                for x in min_x..max_x {
                    let index = y * self.physical_width + x;
                    if !mask[index] {
                        continue;
                    }
                    let offset = index * 4;
                    self.pixels[offset..offset + 4].copy_from_slice(&color);
                    self.present_pixels[index] = packed;
                }
            }
            return;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.set_clear_color(crate::raster::gpu_color(Rgba::from_tuple(rgba)));
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        } else {
            let packed = rgba_to_present_pixel(&color);
            fill_rgba_buffer(&mut self.pixels, &color);
            self.present_pixels.fill(packed);
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
        }
    }

    pub(crate) fn clear_impl(&mut self) {
        self.pending_3d_triangles.clear();
        if !self.clip_masks.is_empty() {
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            let (min_x, min_y, max_x, max_y) = self.clip_bounds.last().copied().unwrap_or((
                0,
                0,
                self.physical_width,
                self.physical_height,
            ));
            for y in min_y..max_y {
                for x in min_x..max_x {
                    let index = y * self.physical_width + x;
                    if !mask[index] {
                        continue;
                    }
                    let offset = index * 4;
                    self.pixels[offset..offset + 4].fill(0);
                    self.present_pixels[index] = 0;
                }
            }
            return;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.clear_transparent();
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        } else {
            self.pixels.fill(0);
            self.present_pixels.fill(0);
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
        }
    }
}
