use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn background_impl(&mut self, rgba: (u8, u8, u8, u8)) {
        let color = Rgba::from_tuple(rgba).as_array();
        if !self.clip_masks.is_empty() {
            if self.gpu.is_some() && !self.cpu_compositing_active {
                let fill = Rgba::from_tuple(rgba);
                let width = self.physical_width as f64;
                let height = self.physical_height as f64;
                let mut vertices = Vec::with_capacity(6);
                push_triangle(
                    &mut vertices,
                    (0.0, 0.0),
                    (width, 0.0),
                    (width, height),
                    fill,
                );
                push_triangle(
                    &mut vertices,
                    (0.0, 0.0),
                    (width, height),
                    (0.0, height),
                    fill,
                );
                let _ = self.draw_gpu_triangles(vertices);
                return;
            }
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            let (min_x, min_y, max_x, max_y) = self.clip_bounds.last().copied().unwrap_or((
                0,
                0,
                self.physical_width,
                self.physical_height,
            ));
            let packed = rgba_to_present_pixel(&color);
            for y in min_y..max_y {
                for x in min_x..max_x {
                    let index = y * self.physical_width + x;
                    if !mask[index] {
                        continue;
                    }
                    let offset = index * 4;
                    self.pixels[offset..offset + 4].copy_from_slice(&color);
                    self.present_pixels[index] = packed;
                }
            }
            return;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.set_clear_color(crate::raster::gpu_color(Rgba::from_tuple(rgba)));
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        } else {
            let packed = rgba_to_present_pixel(&color);
            fill_rgba_buffer(&mut self.pixels, &color);
            self.present_pixels.fill(packed);
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
        }
    }

    pub(crate) fn clear_impl(&mut self) {
        if !self.clip_masks.is_empty() {
            if self.render_dirty && self.offscreen_dirty {
                self.render_gpu_frame(true);
            }
            let mask = self.clip_masks.last().expect("clip mask is active");
            let (min_x, min_y, max_x, max_y) = self.clip_bounds.last().copied().unwrap_or((
                0,
                0,
                self.physical_width,
                self.physical_height,
            ));
            for y in min_y..max_y {
                for x in min_x..max_x {
                    let index = y * self.physical_width + x;
                    if !mask[index] {
                        continue;
                    }
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
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
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

    pub(crate) fn line_current_impl(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
    ) -> PyResult<()> {
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
                    self.draw_gpu_even_odd_spans(bounds, &rings, fill)?;
                }
            }
            if let Some(stroke) = style.stroke {
                let width = stroke_width(style.stroke_weight, self.pixel_density);
                self.draw_gpu_polyline(&transformed_outer, close, width, stroke)?;
                for contour in &transformed_contours {
                    self.draw_gpu_polyline(contour, true, width, stroke)?;
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
        let parent_bounds = self.clip_bounds.last().copied();
        let mut mask = vec![false; self.physical_width * self.physical_height];
        let mut bounds_points = transformed_outer.clone();
        for contour in &transformed_contours {
            bounds_points.extend(contour.iter().copied());
        }
        let mut bounds = clipped_bounds(
            &bounds_points,
            0.0,
            self.physical_width,
            self.physical_height,
        );
        if let Some((p_min_x, p_min_y, p_max_x, p_max_y)) = parent_bounds {
            bounds.0 = bounds.0.max(p_min_x);
            bounds.1 = bounds.1.max(p_min_y);
            bounds.2 = bounds.2.min(p_max_x);
            bounds.3 = bounds.3.min(p_max_y);
        }
        let mut rings = Vec::with_capacity(1 + transformed_contours.len());
        rings.push(transformed_outer.as_slice());
        for contour in &transformed_contours {
            rings.push(contour.as_slice());
        }
        rasterize_even_odd_mask(
            &mut mask,
            self.physical_width,
            bounds,
            &rings,
            parent.map(Vec::as_slice),
        );
        self.clip_masks.push(mask);
        self.clip_bounds.push(bounds);
        self.upload_current_clip_mask();
        Ok(())
    }

    pub(crate) fn end_clip_impl(&mut self) -> PyResult<()> {
        self.clip_masks
            .pop()
            .ok_or_else(|| PyValueError::new_err("end_clip() called without an active clip."))?;
        self.clip_bounds.pop();
        self.upload_current_clip_mask();
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

    pub(crate) fn shaded_faces_impl(&mut self, faces: &Bound<'_, PyAny>) -> PyResult<()> {
        let sequence = faces.downcast::<PyList>()?;
        let mut vertices = Vec::new();
        for item in sequence.iter() {
            let dict = item.downcast::<PyDict>()?;
            if dict.get_item("texture")?.is_some_and(|value| !value.is_none()) {
                continue;
            }
            let points = dict
                .get_item("points")?
                .ok_or_else(|| PyValueError::new_err("face payload is missing points."))?
                .extract::<Vec<(f64, f64)>>()?;
            if points.len() < 3 {
                continue;
            }
            let color = dict
                .get_item("color")?
                .ok_or_else(|| PyValueError::new_err("face payload is missing color."))?
                .extract::<(f64, f64, f64, f64)>()?;
            let color = Rgba {
                r: (color.0.clamp(0.0, 1.0) * 255.0).round() as u8,
                g: (color.1.clamp(0.0, 1.0) * 255.0).round() as u8,
                b: (color.2.clamp(0.0, 1.0) * 255.0).round() as u8,
                a: (color.3.clamp(0.0, 1.0) * 255.0).round() as u8,
            };
            let first = scale_point(points[0], self.pixel_density);
            for index in 1..points.len() - 1 {
                push_triangle(
                    &mut vertices,
                    first,
                    scale_point(points[index], self.pixel_density),
                    scale_point(points[index + 1], self.pixel_density),
                    color,
                );
            }
        }
        if vertices.is_empty() {
            return Ok(());
        }
        if self.gpu.is_some() && !self.cpu_compositing_active {
            self.draw_gpu_triangles(vertices)?;
            return Ok(());
        }
        let style = Style {
            fill: Some(Rgba {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            }),
            stroke: None,
            ..Style::default()
        };
        for triangle in vertices.chunks_exact(3) {
            let points = [
                (triangle[0].0[0] as f64, triangle[0].0[1] as f64),
                (triangle[1].0[0] as f64, triangle[1].0[1] as f64),
                (triangle[2].0[0] as f64, triangle[2].0[1] as f64),
            ];
            self.draw_transformed_polygon(&points, &style, true)?;
        }
        Ok(())
    }
}

impl Canvas {
    fn upload_current_clip_mask(&mut self) {
        let Some(gpu) = self.gpu.as_mut() else {
            return;
        };
        let Some(mask) = self.clip_masks.last() else {
            gpu.clear_clip_mask();
            return;
        };
        let bounds = self.clip_bounds.last().copied().unwrap_or((
            0,
            0,
            self.physical_width,
            self.physical_height,
        ));
        let width = bounds.2.saturating_sub(bounds.0).max(1);
        let height = bounds.3.saturating_sub(bounds.1).max(1);
        let mut rgba = vec![0_u8; width * height * 4];
        for y in bounds.1..bounds.3 {
            let source_row = y * self.physical_width;
            let dest_row = (y - bounds.1) * width;
            for x in bounds.0..bounds.2 {
                if mask[source_row + x] {
                    let offset = (dest_row + x - bounds.0) * 4;
                    rgba[offset..offset + 4].fill(255);
                }
            }
        }
        gpu.set_clip_mask(bounds.0, bounds.1, width, height, &rgba);
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

fn scale_point(point: Point, scale: f64) -> Point {
    (point.0 * scale, point.1 * scale)
}
