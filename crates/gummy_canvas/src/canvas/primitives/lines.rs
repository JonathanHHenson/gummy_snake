use crate::prelude::*;
use crate::runtime::style::*;

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
        ensure_supported_style(style)?;
        let color = match style.stroke.or(style.fill) {
            Some(color) => color,
            None => return Ok(()),
        };
        let stroke_width = stroke_width(style.stroke_weight, self.pixel_density);
        if style.erasing {
            if self.can_queue_gpu_erase(style) {
                self.draw_gpu_erase_polyline_with_matrix(
                    &[(x, y), (x, y)],
                    false,
                    matrix,
                    self.pixel_density,
                    stroke_width,
                )?;
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }
        if self.can_queue_gpu_primitives(style) {
            self.draw_gpu_polyline_with_matrix(
                &[(x, y), (x, y)],
                false,
                matrix,
                self.pixel_density,
                stroke_width,
                color,
                style.blend_mode_kind,
            )?;
            return Ok(());
        }
        self.prepare_cpu_composite()
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
        ensure_supported_style(style)?;
        let stroke = match style.stroke {
            Some(color) => color,
            None => return Ok(()),
        };
        let width = stroke_width(style.stroke_weight, self.pixel_density);
        if style.erasing {
            if self.can_queue_gpu_erase(style) {
                self.draw_gpu_erase_polyline_with_matrix(
                    &[(x1, y1), (x2, y2)],
                    false,
                    matrix,
                    self.pixel_density,
                    width,
                )?;
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }
        if self.can_queue_gpu_primitives(style) {
            self.draw_gpu_polyline_with_matrix(
                &[(x1, y1), (x2, y2)],
                false,
                matrix,
                self.pixel_density,
                width,
                stroke,
                style.blend_mode_kind,
            )?;
            return Ok(());
        }
        self.prepare_cpu_composite()
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
        ensure_supported_style(style)?;
        let Some(stroke) = style.stroke else {
            return Ok(());
        };
        let width = stroke_width(style.stroke_weight, self.pixel_density);
        if style.erasing {
            if self.can_queue_gpu_erase(style) {
                for (x1, y1, x2, y2) in lines {
                    self.draw_gpu_erase_polyline_with_matrix(
                        &[(x1, y1), (x2, y2)],
                        false,
                        matrix,
                        self.pixel_density,
                        width,
                    )?;
                }
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }
        if self.can_queue_gpu_primitives(style) {
            for (x1, y1, x2, y2) in lines {
                self.draw_gpu_polyline_with_matrix(
                    &[(x1, y1), (x2, y2)],
                    false,
                    matrix,
                    self.pixel_density,
                    width,
                    stroke,
                    style.blend_mode_kind,
                )?;
            }
            return Ok(());
        }
        self.prepare_cpu_composite()
    }
}
