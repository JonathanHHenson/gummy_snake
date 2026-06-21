use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn background_impl(&mut self, rgba: (u8, u8, u8, u8)) {
        let color = Rgba::from_tuple(rgba).as_array();
        if !self.clip_masks.is_empty() {
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            let packed = rgba_to_present_pixel(&color);
            for (index, visible) in mask.iter().copied().enumerate() {
                if visible {
                    let offset = index * 4;
                    self.pixels[offset..offset + 4].copy_from_slice(&color);
                    self.present_pixels[index] = packed;
                }
            }
            return;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.set_clear_color(gpu_color(Rgba::from_tuple(rgba)));
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        } else {
            let packed = rgba_to_present_pixel(&color);
            fill_rgba_buffer(&mut self.pixels, &color);
            self.present_pixels.fill(packed);
        }
    }

    pub(crate) fn clear_impl(&mut self) {
        if !self.clip_masks.is_empty() {
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            for (index, visible) in mask.iter().copied().enumerate() {
                if visible {
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
        }
    }

    pub(crate) fn point_impl(
        &mut self,
        x: f64,
        y: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
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
            self.draw_gpu_disc(tx, ty, radius, color)?;
            return Ok(());
        }
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            &style.blend_mode,
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
            self.draw_gpu_segment(p1, p2, radius * 2.0, stroke)?;
            return Ok(());
        }
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            &style.blend_mode,
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
                self.draw_gpu_segment(p1, p2, radius * 2.0, stroke)?;
                continue;
            }
            self.prepare_cpu_composite();
            let Some(mut overlay) = OverlayRegion::from_bounds(
                bounds,
                self.physical_width,
                &mut self.pixels,
                &mut self.present_pixels,
                style.erasing,
                &style.blend_mode,
                self.clip_masks.last().map(Vec::as_slice),
            ) else {
                continue;
            };
            stroke_segment(&mut overlay, p1, p2, radius * 2.0, stroke);
            self.upload_cpu_pixels()?;
        }
        Ok(())
    }

    pub(crate) fn polygon_impl(
        &mut self,
        points: Vec<(f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
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
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            &style.blend_mode,
            self.clip_masks.last().map(Vec::as_slice),
        ) else {
            return Ok(());
        };
        if close && transformed_outer.len() >= 3 {
            if let Some(fill) = style.fill {
                for y in overlay.min_y..overlay.max_y() {
                    for x in overlay.min_x..overlay.max_x() {
                        let sample = (x as f64 + 0.5, y as f64 + 0.5);
                        let inside_outer = point_in_polygon(sample, &transformed_outer);
                        let inside_hole = transformed_contours
                            .iter()
                            .any(|contour| contour.len() >= 3 && point_in_polygon(sample, contour));
                        if inside_outer && !inside_hole {
                            overlay.set_pixel(x, y, fill);
                        }
                    }
                }
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

    pub(crate) fn begin_clip_impl(
        &mut self,
        outer: Vec<(f64, f64)>,
        contours: Vec<Vec<(f64, f64)>>,
        matrix: Matrix,
    ) -> PyResult<()> {
        if outer.len() < 3 {
            return Err(PyValueError::new_err(
                "begin_clip() requires at least three vertices.",
            ));
        }
        if self.render_dirty && self.offscreen_dirty {
            self.render_gpu_frame(true);
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
        let parent = self.clip_masks.last();
        let mut mask = vec![false; self.physical_width * self.physical_height];
        for y in 0..self.physical_height {
            for x in 0..self.physical_width {
                let index = y * self.physical_width + x;
                if parent.is_some_and(|parent_mask| !parent_mask[index]) {
                    continue;
                }
                let sample = (x as f64 + 0.5, y as f64 + 0.5);
                let inside_outer = point_in_polygon(sample, &transformed_outer);
                let inside_hole = transformed_contours
                    .iter()
                    .any(|contour| contour.len() >= 3 && point_in_polygon(sample, contour));
                mask[index] = inside_outer && !inside_hole;
            }
        }
        self.clip_masks.push(mask);
        Ok(())
    }

    pub(crate) fn end_clip_impl(&mut self) -> PyResult<()> {
        self.clip_masks
            .pop()
            .ok_or_else(|| PyValueError::new_err("end_clip() called without an active clip."))?;
        Ok(())
    }

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
        ensure_supported_style(&style)?;
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
