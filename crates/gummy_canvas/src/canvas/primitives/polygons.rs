use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn polygon_impl(
        &mut self,
        points: Vec<(f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.polygon_with_style(points, &style, matrix, close)
    }

    pub(crate) fn polygon_current_impl(
        &mut self,
        points: Vec<(f64, f64)>,
        close: bool,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.polygon_with_style(points, &style, self.current_matrix, close)
    }

    pub(crate) fn polygon_with_style(
        &mut self,
        points: Vec<(f64, f64)>,
        style: &Style,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        ensure_supported_style(&style)?;
        if points.is_empty() || (style.fill.is_none() && style.stroke.is_none()) {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if close && points.len() >= 3 && style.fill.is_some() {
                if polygon_is_convex(&points) {
                    self.draw_gpu_erase_transformed_polygon_fill(
                        &points,
                        matrix,
                        self.pixel_density,
                    )?;
                } else {
                    self.draw_gpu_erase_complex_polygon_fill_with_matrix(
                        &points,
                        &[],
                        matrix,
                        self.pixel_density,
                    )?;
                }
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_polyline_with_matrix(
                    &points,
                    close,
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
        if close && points.len() >= 3 {
            if let Some(fill) = style.fill {
                if polygon_is_convex(&points) {
                    self.draw_gpu_transformed_polygon_fill(
                        &points,
                        matrix,
                        self.pixel_density,
                        fill,
                        style.blend_mode_kind,
                    )?;
                } else {
                    self.draw_gpu_complex_polygon_fill_with_matrix(
                        &points,
                        &[],
                        matrix,
                        self.pixel_density,
                        fill,
                        style.blend_mode_kind,
                    )?;
                }
            }
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline_with_matrix(
                &points,
                close,
                matrix,
                self.pixel_density,
                stroke_width(style.stroke_weight, self.pixel_density),
                stroke,
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn complex_polygon_impl(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.complex_polygon_with_style(outer, contours, &style, matrix, close)
    }

    pub(crate) fn complex_polygon_current_impl(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        close: bool,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.complex_polygon_with_style(outer, contours, &style, self.current_matrix, close)
    }

    pub(crate) fn complex_polygon_with_style(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        style: &Style,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        ensure_supported_style(&style)?;
        if outer.is_empty() || (style.fill.is_none() && style.stroke.is_none()) {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if close && style.fill.is_some() {
                self.draw_gpu_erase_complex_polygon_fill_with_matrix(
                    &outer,
                    &contours,
                    matrix,
                    self.pixel_density,
                )?;
            }
            if style.stroke.is_some() {
                let width = stroke_width(style.stroke_weight, self.pixel_density);
                self.draw_gpu_erase_polyline_with_matrix(
                    &outer,
                    close,
                    matrix,
                    self.pixel_density,
                    width,
                )?;
                for contour in &contours {
                    self.draw_gpu_erase_polyline_with_matrix(
                        contour,
                        true,
                        matrix,
                        self.pixel_density,
                        width,
                    )?;
                }
            }
            return Ok(());
        }
        if !self.can_queue_gpu_primitives(style) {
            return self.prepare_cpu_composite();
        }
        if close {
            if let Some(fill) = style.fill {
                self.draw_gpu_complex_polygon_fill_with_matrix(
                    &outer,
                    &contours,
                    matrix,
                    self.pixel_density,
                    fill,
                    style.blend_mode_kind,
                )?;
            }
        }
        if let Some(stroke) = style.stroke {
            let width = stroke_width(style.stroke_weight, self.pixel_density);
            self.draw_gpu_polyline_with_matrix(
                &outer,
                close,
                matrix,
                self.pixel_density,
                width,
                stroke,
                style.blend_mode_kind,
            )?;
            for contour in &contours {
                self.draw_gpu_polyline_with_matrix(
                    contour,
                    true,
                    matrix,
                    self.pixel_density,
                    width,
                    stroke,
                    style.blend_mode_kind,
                )?;
            }
        }
        Ok(())
    }
}
