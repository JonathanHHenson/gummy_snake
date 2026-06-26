use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn point_impl(
        &mut self,
        x: f64,
        y: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.point_with_style(x, y, &style, matrix)
    }

    pub(crate) fn point_current_impl(&mut self, x: f64, y: f64) -> PyResult<()> {
        let style = self.current_style.clone();
        self.point_with_style(x, y, &style, self.current_matrix)
    }

    pub(crate) fn point_with_style(
        &mut self,
        x: f64,
        y: f64,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(&style)?;
        let color = match style.stroke.or(style.fill) {
            Some(color) => color,
            None => return Ok(()),
        };
        let (tx, ty) = self.transform_point(matrix, x, y);
        let radius = (style.stroke_weight * self.pixel_density / 2.0).max(0.5);
        let bounds = clipped_bounds(
            &[(tx, ty)],
            radius,
            self.physical_width,
            self.physical_height,
        );
        if self.can_queue_gpu_primitives(&style) {
            self.draw_gpu_disc(tx, ty, radius, color, style.blend_mode_kind)?;
            return Ok(());
        }
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            self.erase_color,
            style.blend_mode_kind,
            self.clip_masks.last().map(Vec::as_slice),
        ) else {
            return Ok(());
        };
        fill_disc(&mut overlay, tx, ty, radius, color);
        self.upload_cpu_pixels()?;
        Ok(())
    }

    pub(crate) fn line_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.line_with_style(x1, y1, x2, y2, &style, matrix)
    }

    pub(crate) fn line_current_impl(&mut self, x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<()> {
        let style = self.current_style.clone();
        self.line_with_style(x1, y1, x2, y2, &style, self.current_matrix)
    }

    pub(crate) fn line_with_style(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(&style)?;
        let stroke = match style.stroke {
            Some(color) => color,
            None => return Ok(()),
        };
        let p1 = self.transform_point(matrix, x1, y1);
        let p2 = self.transform_point(matrix, x2, y2);
        let radius = stroke_width(style.stroke_weight, self.pixel_density) / 2.0;
        let bounds = clipped_bounds(&[p1, p2], radius, self.physical_width, self.physical_height);
        if self.can_queue_gpu_primitives(&style) {
            self.draw_gpu_segment(p1, p2, radius * 2.0, stroke, style.blend_mode_kind)?;
            return Ok(());
        }
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            self.erase_color,
            style.blend_mode_kind,
            self.clip_masks.last().map(Vec::as_slice),
        ) else {
            return Ok(());
        };
        stroke_segment(&mut overlay, p1, p2, radius * 2.0, stroke);
        self.upload_cpu_pixels()?;
        Ok(())
    }

    pub(crate) fn batch_lines_impl(
        &mut self,
        lines: Vec<(f64, f64, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.batch_lines_with_style(lines, &style, matrix)
    }

    pub(crate) fn batch_lines_current_impl(
        &mut self,
        lines: Vec<(f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.batch_lines_with_style(lines, &style, self.current_matrix)
    }

    pub(crate) fn batch_lines_with_style(
        &mut self,
        lines: Vec<(f64, f64, f64, f64)>,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(&style)?;
        let Some(stroke) = style.stroke else {
            return Ok(());
        };
        let radius = stroke_width(style.stroke_weight, self.pixel_density) / 2.0;
        for (x1, y1, x2, y2) in lines {
            let p1 = self.transform_point(matrix, x1, y1);
            let p2 = self.transform_point(matrix, x2, y2);
            let bounds =
                clipped_bounds(&[p1, p2], radius, self.physical_width, self.physical_height);
            if self.can_queue_gpu_primitives(&style) {
                self.draw_gpu_segment(p1, p2, radius * 2.0, stroke, style.blend_mode_kind)?;
                continue;
            }
            self.prepare_cpu_composite();
            let Some(mut overlay) = OverlayRegion::from_bounds(
                bounds,
                self.physical_width,
                &mut self.pixels,
                &mut self.present_pixels,
                style.erasing,
                self.erase_color,
                style.blend_mode_kind,
                self.clip_masks.last().map(Vec::as_slice),
            ) else {
                continue;
            };
            stroke_segment(&mut overlay, p1, p2, radius * 2.0, stroke);
            self.upload_cpu_pixels()?;
        }
        Ok(())
    }
}
