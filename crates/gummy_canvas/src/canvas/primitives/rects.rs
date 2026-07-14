use crate::prelude::*;
use crate::runtime::style::*;

impl Canvas {
    pub(crate) fn rect_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.rect_with_style(x, y, width, height, &style, matrix)
    }

    pub(crate) fn rect_current_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.rect_with_style(x, y, width, height, &style, self.current_matrix)
    }

    pub(crate) fn rect_with_style(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(style)?;
        if style.fill.is_none() && style.stroke.is_none() {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if style.fill.is_some() {
                self.draw_gpu_erase_transformed_rect(
                    x,
                    y,
                    width,
                    height,
                    matrix,
                    self.pixel_density,
                )?;
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_polyline_with_matrix(
                    &[
                        (x, y),
                        (x + width, y),
                        (x + width, y + height),
                        (x, y + height),
                    ],
                    true,
                    matrix,
                    self.pixel_density,
                    stroke_width(style.stroke_weight, self.pixel_density),
                )?;
            }
            return Ok(());
        }
        if let Some((cx, cy, rx, ry)) =
            self.axis_aligned_ellipse_geometry(matrix, x, y, width, height)
        {
            if self.can_draw_gpu_destination_blend_shape(style) {
                self.draw_gpu_destination_blend_rect(cx, cy, rx, ry, style)?;
                return Ok(());
            }
        }
        if !self.can_queue_gpu_primitives(style) {
            return self.prepare_cpu_composite();
        }
        if let Some(fill) = style.fill {
            self.draw_gpu_transformed_rect(
                x,
                y,
                width,
                height,
                matrix,
                self.pixel_density,
                fill,
                style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline_with_matrix(
                &[
                    (x, y),
                    (x + width, y),
                    (x + width, y + height),
                    (x, y + height),
                ],
                true,
                matrix,
                self.pixel_density,
                stroke_width(style.stroke_weight, self.pixel_density),
                stroke,
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn triangle_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.triangle_with_style(x1, y1, x2, y2, x3, y3, &style, matrix)
    }

    pub(crate) fn triangle_current_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.triangle_with_style(x1, y1, x2, y2, x3, y3, &style, self.current_matrix)
    }

    pub(crate) fn triangle_with_style(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(style)?;
        if style.fill.is_none() && style.stroke.is_none() {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if style.fill.is_some() {
                self.draw_gpu_erase_transformed_triangle(
                    (x1, y1),
                    (x2, y2),
                    (x3, y3),
                    matrix,
                    self.pixel_density,
                )?;
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_polyline_with_matrix(
                    &[(x1, y1), (x2, y2), (x3, y3)],
                    true,
                    matrix,
                    self.pixel_density,
                    stroke_width(style.stroke_weight, self.pixel_density),
                )?;
            }
            return Ok(());
        }
        if !self.can_queue_gpu_primitives(style) {
            return self.prepare_cpu_composite();
        }
        if let Some(fill) = style.fill {
            self.draw_gpu_transformed_triangle(
                (x1, y1),
                (x2, y2),
                (x3, y3),
                matrix,
                self.pixel_density,
                fill,
                style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline_with_matrix(
                &[(x1, y1), (x2, y2), (x3, y3)],
                true,
                matrix,
                self.pixel_density,
                stroke_width(style.stroke_weight, self.pixel_density),
                stroke,
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn quad_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.quad_with_style(x1, y1, x2, y2, x3, y3, x4, y4, &style, matrix)
    }

    pub(crate) fn quad_current_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.quad_with_style(x1, y1, x2, y2, x3, y3, x4, y4, &style, self.current_matrix)
    }

    pub(crate) fn quad_with_style(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(style)?;
        if style.fill.is_none() && style.stroke.is_none() {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if style.fill.is_some() {
                self.draw_gpu_erase_transformed_triangle(
                    (x1, y1),
                    (x2, y2),
                    (x3, y3),
                    matrix,
                    self.pixel_density,
                )?;
                self.draw_gpu_erase_transformed_triangle(
                    (x1, y1),
                    (x3, y3),
                    (x4, y4),
                    matrix,
                    self.pixel_density,
                )?;
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_polyline_with_matrix(
                    &[(x1, y1), (x2, y2), (x3, y3), (x4, y4)],
                    true,
                    matrix,
                    self.pixel_density,
                    stroke_width(style.stroke_weight, self.pixel_density),
                )?;
            }
            return Ok(());
        }
        if !self.can_queue_gpu_primitives(style) {
            return self.prepare_cpu_composite();
        }
        if let Some(fill) = style.fill {
            self.draw_gpu_transformed_triangle(
                (x1, y1),
                (x2, y2),
                (x3, y3),
                matrix,
                self.pixel_density,
                fill,
                style.blend_mode_kind,
            )?;
            self.draw_gpu_transformed_triangle(
                (x1, y1),
                (x3, y3),
                (x4, y4),
                matrix,
                self.pixel_density,
                fill,
                style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline_with_matrix(
                &[(x1, y1), (x2, y2), (x3, y3), (x4, y4)],
                true,
                matrix,
                self.pixel_density,
                stroke_width(style.stroke_weight, self.pixel_density),
                stroke,
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }
}
