use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn ellipse_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let parsed_style = self.cached_style(style)?;
        self.ellipse_with_style(x, y, width, height, &parsed_style, matrix)
    }

    pub(crate) fn ellipse_current_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.ellipse_with_style(x, y, width, height, &style, self.current_matrix)
    }

    pub(crate) fn ellipse_with_style(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(parsed_style)?;
        if let Some((cx, cy, rx, ry)) =
            self.axis_aligned_ellipse_geometry(matrix, x, y, width, height)
        {
            let padding = if parsed_style.stroke.is_some() {
                stroke_width(parsed_style.stroke_weight, self.pixel_density) / 2.0
            } else {
                0.0
            };
            let bounds = ellipse_bounds(
                cx,
                cy,
                rx,
                ry,
                padding,
                self.physical_width,
                self.physical_height,
            );
            if parsed_style.erasing
                && self.gpu.is_some()
                && !self.cpu_compositing_active
                && parsed_style.blend_mode == crate::BLEND_MODE_BLEND
            {
                self.draw_gpu_axis_aligned_ellipse(
                    cx,
                    cy,
                    rx,
                    ry,
                    parsed_style,
                    self.pixel_density,
                )?;
                return Ok(());
            }
            if self.can_queue_gpu_primitives(&parsed_style) {
                self.draw_gpu_axis_aligned_ellipse(
                    cx,
                    cy,
                    rx,
                    ry,
                    parsed_style,
                    self.pixel_density,
                )?;
                return Ok(());
            }
            if self.can_draw_gpu_blend_ellipse(parsed_style) {
                self.draw_gpu_blend_ellipse(cx, cy, rx, ry, parsed_style)?;
                return Ok(());
            }
            self.prepare_cpu_composite();
            let Some(mut overlay) = OverlayRegion::from_bounds(
                bounds,
                self.physical_width,
                &mut self.pixels,
                &mut self.present_pixels,
                parsed_style.erasing,
                self.erase_color,
                parsed_style.blend_mode_kind,
                self.clip_masks.last().map(Vec::as_slice),
            ) else {
                return Ok(());
            };
            draw_axis_aligned_ellipse(
                &mut overlay,
                cx,
                cy,
                rx,
                ry,
                parsed_style,
                self.pixel_density,
            );
            self.upload_cpu_pixels()?;
            return Ok(());
        }

        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        let rx = width / 2.0;
        let ry = height / 2.0;
        let points: Vec<Point> = (0..64)
            .map(|index| {
                let t = 2.0 * PI * index as f64 / 64.0;
                (cx + t.cos() * rx, cy + t.sin() * ry)
            })
            .collect();
        self.polygon_with_style(points, parsed_style, matrix, true)
    }

    pub(crate) fn arc_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        mut stop: f64,
        mode: &str,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        let rx = width / 2.0;
        let ry = height / 2.0;
        while stop < start {
            stop += 2.0 * PI;
        }
        let steps = ((stop - start).abs() / (2.0 * PI) * 64.0).floor().max(8.0) as usize;
        let arc_points: Vec<Point> = (0..=steps)
            .map(|index| {
                let t = start + (stop - start) * index as f64 / steps as f64;
                (cx + t.cos() * rx, cy + t.sin() * ry)
            })
            .collect();
        match mode {
            "pie" => {
                let mut points = vec![(cx, cy)];
                points.extend(arc_points);
                self.polygon_impl(points, style, matrix, true)
            }
            "chord" => self.polygon_impl(arc_points, style, matrix, true),
            _ => {
                let parsed_style = self.cached_style(style)?;
                ensure_supported_style(&parsed_style)?;
                let transformed: Vec<Point> = arc_points
                    .iter()
                    .map(|(px, py)| self.transform_point(matrix, *px, *py))
                    .collect();
                let padding = if parsed_style.stroke.is_some() {
                    stroke_width(parsed_style.stroke_weight, self.pixel_density) / 2.0
                } else {
                    0.0
                };
                let bounds = clipped_bounds(
                    &transformed,
                    padding,
                    self.physical_width,
                    self.physical_height,
                );
                if self.can_queue_gpu_polygon(&transformed, &parsed_style, mode != "open") {
                    if parsed_style.fill.is_some() && mode != "open" {
                        self.draw_gpu_polygon(
                            &transformed,
                            &Style {
                                stroke: None,
                                ..parsed_style.clone()
                            },
                            true,
                            self.pixel_density,
                        )?;
                    }
                    if let Some(stroke) = parsed_style.stroke {
                        self.draw_gpu_polyline(
                            &transformed,
                            false,
                            stroke_width(parsed_style.stroke_weight, self.pixel_density),
                            stroke,
                            parsed_style.blend_mode_kind,
                        )?;
                    }
                    return Ok(());
                }
                self.prepare_cpu_composite();
                let Some(mut overlay) = OverlayRegion::from_bounds(
                    bounds,
                    self.physical_width,
                    &mut self.pixels,
                    &mut self.present_pixels,
                    parsed_style.erasing,
                    self.erase_color,
                    parsed_style.blend_mode_kind,
                    self.clip_masks.last().map(Vec::as_slice),
                ) else {
                    return Ok(());
                };
                if parsed_style.fill.is_some() && mode != "open" {
                    draw_polygon_overlay(
                        &mut overlay,
                        &transformed,
                        &Style {
                            stroke: None,
                            ..parsed_style.clone()
                        },
                        true,
                        self.pixel_density,
                    );
                }
                if let Some(stroke) = parsed_style.stroke {
                    draw_polyline_stroke(
                        &mut overlay,
                        &transformed,
                        false,
                        stroke_width(parsed_style.stroke_weight, self.pixel_density),
                        stroke,
                    );
                }
                self.upload_cpu_pixels()?;
                Ok(())
            }
        }
    }
}
