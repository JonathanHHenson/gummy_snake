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
        if points.is_empty() {
            return Ok(());
        }
        let transformed: Vec<Point> = points
            .iter()
            .map(|(x, y)| self.transform_point(matrix, *x, *y))
            .collect();
        self.draw_transformed_polygon(&transformed, &style, close)
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
        if outer.is_empty() {
            return Ok(());
        }
        let transformed_outer: Vec<Point> = outer
            .iter()
            .map(|(x, y)| self.transform_point(matrix, *x, *y))
            .collect();
        let transformed_contours: Vec<Vec<Point>> = contours
            .iter()
            .map(|contour| {
                contour
                    .iter()
                    .map(|(x, y)| self.transform_point(matrix, *x, *y))
                    .collect()
            })
            .collect();
        let mut bounds_points = transformed_outer.clone();
        for contour in &transformed_contours {
            bounds_points.extend(contour.iter().copied());
        }
        let padding = if style.stroke.is_some() {
            stroke_width(style.stroke_weight, self.pixel_density) / 2.0
        } else {
            0.0
        };
        let bounds = clipped_bounds(
            &bounds_points,
            padding,
            self.physical_width,
            self.physical_height,
        );
        if self.can_queue_gpu_primitives(&style) {
            if close && transformed_outer.len() >= 3 {
                if let Some(fill) = style.fill {
                    let mut rings = Vec::with_capacity(1 + transformed_contours.len());
                    rings.push(transformed_outer.as_slice());
                    for contour in &transformed_contours {
                        rings.push(contour.as_slice());
                    }
                    self.draw_gpu_even_odd_spans(bounds, &rings, fill, style.blend_mode_kind)?;
                }
            }
            if let Some(stroke) = style.stroke {
                let width = stroke_width(style.stroke_weight, self.pixel_density);
                self.draw_gpu_polyline(
                    &transformed_outer,
                    close,
                    width,
                    stroke,
                    style.blend_mode_kind,
                )?;
                for contour in &transformed_contours {
                    self.draw_gpu_polyline(contour, true, width, stroke, style.blend_mode_kind)?;
                }
            }
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
        if close && transformed_outer.len() >= 3 {
            if let Some(fill) = style.fill {
                let mut rings = Vec::with_capacity(1 + transformed_contours.len());
                rings.push(transformed_outer.as_slice());
                for contour in &transformed_contours {
                    rings.push(contour.as_slice());
                }
                fill_even_odd_polygon(&mut overlay, &rings, fill);
            }
        }
        if let Some(stroke) = style.stroke {
            let width = stroke_width(style.stroke_weight, self.pixel_density);
            draw_polyline_stroke(&mut overlay, &transformed_outer, close, width, stroke);
            for contour in &transformed_contours {
                draw_polyline_stroke(&mut overlay, contour, true, width, stroke);
            }
        }
        self.upload_cpu_pixels()?;
        Ok(())
    }
}
