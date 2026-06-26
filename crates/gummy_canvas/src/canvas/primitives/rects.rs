use crate::runtime::style::*;
use crate::*;

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
        ensure_supported_style(&style)?;
        let (a, b, c, d, e, f) = matrix;
        if b.abs() <= f64::EPSILON && c.abs() <= f64::EPSILON {
            let x0 = (a * x + e) * self.pixel_density;
            let y0 = (d * y + f) * self.pixel_density;
            let x1 = (a * (x + width) + e) * self.pixel_density;
            let y1 = (d * (y + height) + f) * self.pixel_density;
            let min_x = x0.min(x1);
            let min_y = y0.min(y1);
            let max_x = x0.max(x1);
            let max_y = y0.max(y1);
            let padding = if style.stroke.is_some() {
                stroke_width(style.stroke_weight, self.pixel_density) / 2.0
            } else {
                0.0
            };
            let bounds = (
                (min_x - padding).floor().max(0.0) as usize,
                (min_y - padding).floor().max(0.0) as usize,
                (max_x + padding)
                    .ceil()
                    .min(self.physical_width as f64)
                    .max(0.0) as usize,
                (max_y + padding)
                    .ceil()
                    .min(self.physical_height as f64)
                    .max(0.0) as usize,
            );
            if style.erasing
                && self.gpu.is_some()
                && !self.cpu_compositing_active
                && style.blend_mode == BLEND_MODE_BLEND
            {
                if let Some(fill) = style.fill {
                    let mut vertices = Vec::with_capacity(6);
                    push_triangle(
                        &mut vertices,
                        (min_x, min_y),
                        (max_x, min_y),
                        (max_x, max_y),
                        fill,
                    );
                    push_triangle(
                        &mut vertices,
                        (min_x, min_y),
                        (max_x, max_y),
                        (min_x, max_y),
                        fill,
                    );
                    self.draw_gpu_erase_triangles(vertices)?;
                    return Ok(());
                }
            }
            if !self.can_queue_gpu_primitives(&style) {
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
                draw_axis_aligned_rect_overlay(
                    &mut overlay,
                    min_x,
                    min_y,
                    max_x,
                    max_y,
                    &style,
                    self.pixel_density,
                );
                self.upload_cpu_pixels()?;
                return Ok(());
            }
        }
        let points = [
            self.transform_point(matrix, x, y),
            self.transform_point(matrix, x + width, y),
            self.transform_point(matrix, x + width, y + height),
            self.transform_point(matrix, x, y + height),
        ];
        self.draw_transformed_polygon(&points, &style, true)
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
        ensure_supported_style(&style)?;
        let points = [
            self.transform_point(matrix, x1, y1),
            self.transform_point(matrix, x2, y2),
            self.transform_point(matrix, x3, y3),
        ];
        self.draw_transformed_polygon(&points, &style, true)
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
        ensure_supported_style(&style)?;
        let points = [
            self.transform_point(matrix, x1, y1),
            self.transform_point(matrix, x2, y2),
            self.transform_point(matrix, x3, y3),
            self.transform_point(matrix, x4, y4),
        ];
        self.draw_transformed_polygon(&points, &style, true)
    }
}

fn draw_axis_aligned_rect_overlay(
    overlay: &mut OverlayRegion<'_>,
    min_x: f64,
    min_y: f64,
    max_x: f64,
    max_y: f64,
    style: &Style,
    pixel_density: f64,
) {
    if let Some(fill) = style.fill {
        let start_x = min_x.floor().max(overlay.min_x as f64) as usize;
        let start_y = min_y.floor().max(overlay.min_y as f64) as usize;
        let end_x = max_x.ceil().min(overlay.max_x() as f64).max(0.0) as usize;
        let end_y = max_y.ceil().min(overlay.max_y() as f64).max(0.0) as usize;
        for y in start_y..end_y {
            for x in start_x..end_x {
                overlay.set_pixel(x, y, fill);
            }
        }
    }
    let Some(stroke) = style.stroke else {
        return;
    };
    let half = (stroke_width(style.stroke_weight, pixel_density) / 2.0).max(0.5);
    let outer_min_x = min_x - half;
    let outer_min_y = min_y - half;
    let outer_max_x = max_x + half;
    let outer_max_y = max_y + half;
    let inner_min_x = min_x + half;
    let inner_min_y = min_y + half;
    let inner_max_x = max_x - half;
    let inner_max_y = max_y - half;
    let start_x = outer_min_x.floor().max(overlay.min_x as f64) as usize;
    let start_y = outer_min_y.floor().max(overlay.min_y as f64) as usize;
    let end_x = outer_max_x.ceil().min(overlay.max_x() as f64).max(0.0) as usize;
    let end_y = outer_max_y.ceil().min(overlay.max_y() as f64).max(0.0) as usize;
    for y in start_y..end_y {
        let sample_y = y as f64 + 0.5;
        for x in start_x..end_x {
            let sample_x = x as f64 + 0.5;
            let inside_inner = inner_min_x < inner_max_x
                && inner_min_y < inner_max_y
                && sample_x >= inner_min_x
                && sample_x < inner_max_x
                && sample_y >= inner_min_y
                && sample_y < inner_max_y;
            if !inside_inner {
                overlay.set_pixel(x, y, stroke);
            }
        }
    }
}
