use crate::canvas_state::Canvas;
use crate::images::validate_rgba_buffer;
use crate::raster::{
    clipped_source_rect, image_to_canvas_matrix, matrix_determinant, matrix_transform_point,
    point_to_f32, Matrix,
};
use crate::runtime::style::*;
use crate::types::{Rgba, Style};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;

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
        self.draw_image_pixels_with_style(
            image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_image_pixels_with_style(
        &mut self,
        image_pixels: &[u8],
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Style,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        ensure_supported_style(style)?;
        if dw <= 0.0 || dh <= 0.0 || image_width == 0 || image_height == 0 {
            return Ok(());
        }
        validate_rgba_buffer(image_pixels.len(), image_width, image_height)?;
        let source = source.unwrap_or((0, 0, image_width as i64, image_height as i64));
        let Some((_sx, _sy, sw, sh)) = clipped_source_rect(source, image_width, image_height)
        else {
            return Ok(());
        };
        let image_to_canvas =
            image_to_canvas_matrix(matrix, dx, dy, dw, dh, sw, sh, self.pixel_density);
        if matrix_determinant(image_to_canvas).abs() <= f64::EPSILON {
            return Ok(());
        }
        self.prepare_cpu_composite()
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn try_draw_gpu_image_parts_for_payload(
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
        self.try_draw_gpu_image_parts(
            image_key,
            image_version,
            image_width,
            image_height,
            image_pixels,
            dx,
            dy,
            dw,
            dh,
            &style,
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
        style: &Style,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<bool> {
        if !self.can_queue_gpu_primitives(style) || dw <= 0.0 || dh <= 0.0 {
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
        let texture_version = self.texture_cache_versions.version(image_key);
        if texture_version != Some(image_version) {
            self.evict_texture_cache_if_needed(image_key, image_pixels.len())?;
        } else {
            self.performance_counters.texture_cache_hits += 1;
        }
        if texture_version != Some(image_version) {
            let replaced = {
                let Some(gpu) = self.gpu.as_mut() else {
                    return Ok(false);
                };
                gpu.upload_texture(image_key, image_width, image_height, image_pixels)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to upload image texture: {err}"))
                    })?
            };
            self.record_texture_upload(
                image_key,
                image_version,
                image_pixels.len(),
                false,
                texture_version.is_some(),
                replaced,
            );
        }
        let u0 = sx as f32 / image_width as f32;
        let v0 = sy as f32 / image_height as f32;
        let u1 = (sx + sw) as f32 / image_width as f32;
        let v1 = (sy + sh) as f32 / image_height as f32;
        let tint = style.image_tint.unwrap_or(Rgba {
            r: 255,
            g: 255,
            b: 255,
            a: 255,
        });
        let tint = crate::gpu::GpuColor {
            r: tint.r,
            g: tint.g,
            b: tint.b,
            a: tint.a,
        };
        let vertices = [
            (point_to_f32(corners[0]), [u0, v0], tint),
            (point_to_f32(corners[1]), [u1, v0], tint),
            (point_to_f32(corners[2]), [u1, v1], tint),
            (point_to_f32(corners[0]), [u0, v0], tint),
            (point_to_f32(corners[2]), [u1, v1], tint),
            (point_to_f32(corners[3]), [u0, v1], tint),
        ];
        self.upload_stale_texture(false)?;
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(false);
        };
        gpu.draw_image(image_key, vertices, linear_sampling, style.blend_mode_kind);
        self.record_native_image_draw(style.blend_mode_kind, vertices.len());
        Ok(true)
    }
}
