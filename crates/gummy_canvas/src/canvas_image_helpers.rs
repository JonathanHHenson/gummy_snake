use super::*;
use crate::runtime_style::*;

impl Canvas {
    pub(crate) fn draw_image_pixels(
        &mut self,
        image_pixels: &[u8],
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        ensure_supported_style(&style)?;
        if dw <= 0.0 || dh <= 0.0 || image_width == 0 || image_height == 0 {
            return Ok(());
        }
        validate_rgba_buffer(image_pixels.len(), image_width, image_height)?;
        let source = source.unwrap_or((0, 0, image_width as i64, image_height as i64));
        let Some((sx, sy, sw, sh)) = clipped_source_rect(source, image_width, image_height) else {
            return Ok(());
        };
        let image_to_canvas =
            image_to_canvas_matrix(matrix, dx, dy, dw, dh, sw, sh, self.pixel_density);
        if matrix_determinant(image_to_canvas).abs() <= f64::EPSILON {
            return Ok(());
        }
        if let Some((dest_x, dest_y, dest_w, dest_h)) = axis_aligned_image_destination(
            image_to_canvas,
            sw,
            sh,
            self.physical_width,
            self.physical_height,
        ) {
            self.prepare_cpu_composite();
            blit_scaled_region(
                &mut self.pixels,
                &mut self.present_pixels,
                self.physical_width,
                image_pixels,
                image_width,
                sx,
                sy,
                sw,
                sh,
                dest_x,
                dest_y,
                dest_w,
                dest_h,
                style.erasing,
                &style.blend_mode,
                &style.image_sampling,
            );
            self.upload_cpu_pixels()?;
            return Ok(());
        }
        let Some((dest_x, dest_y, dest_w, dest_h)) = affine_bounds(
            image_to_canvas,
            sw,
            sh,
            self.physical_width,
            self.physical_height,
        ) else {
            return Ok(());
        };
        let canvas_to_image = matrix_inverse(image_to_canvas).ok_or_else(|| {
            PyValueError::new_err("Image transform is not invertible for gummy_canvas.")
        })?;
        self.prepare_cpu_composite();
        blit_affine_region(
            &mut self.pixels,
            &mut self.present_pixels,
            self.physical_width,
            image_pixels,
            image_width,
            sx,
            sy,
            sw,
            sh,
            dest_x,
            dest_y,
            dest_w,
            dest_h,
            canvas_to_image,
            style.erasing,
            &style.blend_mode,
            &style.image_sampling,
        );
        self.upload_cpu_pixels()?;
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn try_draw_gpu_image(
        &mut self,
        image_key: u64,
        image: &CachedImage,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<bool> {
        self.try_draw_gpu_image_parts(
            image_key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn try_draw_gpu_image_parts(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_width: usize,
        image_height: usize,
        image_pixels: &[u8],
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<bool> {
        let style = self.cached_style(style)?;
        if !self.can_queue_gpu_primitives(&style) || dw <= 0.0 || dh <= 0.0 {
            return Ok(false);
        }
        let linear_sampling = style.image_sampling != "nearest";
        let source = source.unwrap_or((0, 0, image_width as i64, image_height as i64));
        let Some((sx, sy, sw, sh)) = clipped_source_rect(source, image_width, image_height) else {
            return Ok(true);
        };
        let image_to_canvas =
            image_to_canvas_matrix(matrix, dx, dy, dw, dh, sw, sh, self.pixel_density);
        if matrix_determinant(image_to_canvas).abs() <= f64::EPSILON {
            return Ok(true);
        }
        let corners = [
            matrix_transform_point(image_to_canvas, 0.0, 0.0),
            matrix_transform_point(image_to_canvas, sw as f64, 0.0),
            matrix_transform_point(image_to_canvas, sw as f64, sh as f64),
            matrix_transform_point(image_to_canvas, 0.0, sh as f64),
        ];
        let texture_version = self.texture_cache_versions.get(&image_key).copied();
        if texture_version != Some(image_version) {
            self.performance_counters.texture_uploads += 1;
            self.evict_texture_cache_if_needed(image_key);
        } else {
            self.performance_counters.texture_cache_hits += 1;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            if texture_version != Some(image_version) {
                gpu.upload_texture(image_key, image_width, image_height, image_pixels)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to upload image texture: {err}"))
                    })?;
                self.texture_cache_versions.insert(image_key, image_version);
            }
            let u0 = sx as f32 / image_width as f32;
            let v0 = sy as f32 / image_height as f32;
            let u1 = (sx + sw) as f32 / image_width as f32;
            let v1 = (sy + sh) as f32 / image_height as f32;
            let vertices = [
                (point_to_f32(corners[0]), [u0, v0]),
                (point_to_f32(corners[1]), [u1, v0]),
                (point_to_f32(corners[2]), [u1, v1]),
                (point_to_f32(corners[0]), [u0, v0]),
                (point_to_f32(corners[2]), [u1, v1]),
                (point_to_f32(corners[3]), [u0, v1]),
            ];
            self.upload_stale_texture(false)?;
            let Some(gpu) = self.gpu.as_mut() else {
                return Ok(false);
            };
            gpu.draw_image(image_key, vertices, linear_sampling);
            self.performance_counters.gpu_draws += 1;
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
            self.texture_stale = false;
            return Ok(true);
        }
        Ok(false)
    }

    pub(crate) fn transform_point(&self, matrix: Matrix, x: f64, y: f64) -> Point {
        let (a, b, c, d, e, f) = matrix;
        (
            (a * x + c * y + e) * self.pixel_density,
            (b * x + d * y + f) * self.pixel_density,
        )
    }
}
