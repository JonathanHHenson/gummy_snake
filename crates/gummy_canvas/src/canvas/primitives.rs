use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn background_impl(&mut self, rgba: (u8, u8, u8, u8)) {
        self.pending_3d_triangles.clear();
        self.erase_color = Rgba::from_tuple(rgba);
        let color = self.erase_color.as_array();
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
                let _ = self.draw_gpu_triangles(vertices, BlendMode::Blend);
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
        self.pending_3d_triangles.clear();
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

    pub(crate) fn draw_captured_shape_current_impl(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
        close: bool,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        let result = if state.captured_shape_contours().is_empty() {
            self.polygon_with_style(
                state.captured_shape_vertices().to_vec(),
                &style,
                matrix,
                close,
            )
        } else {
            self.complex_polygon_with_style(
                state.captured_shape_vertices().to_vec(),
                state.captured_shape_contours().to_vec(),
                &style,
                matrix,
                close,
            )
        };
        if result.is_ok() {
            self.performance_counters.direct_shape_finalizations += 1;
            state.reset_captured_shape();
        }
        result
    }

    pub(crate) fn begin_clip_captured_current_impl(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
    ) -> PyResult<()> {
        let result = self.begin_clip_impl(
            state.captured_shape_vertices().to_vec(),
            state.captured_shape_contours().to_vec(),
            self.current_matrix,
        );
        if result.is_ok() {
            self.performance_counters.direct_shape_finalizations += 1;
            state.reset_captured_shape();
        }
        result
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

    pub(crate) fn shaded_faces_impl(&mut self, faces: &Bound<'_, PyAny>) -> PyResult<()> {
        self.performance_counters.python_face_payloads += 1;
        let sequence = faces.downcast::<PyList>()?;
        let mut vertices = Vec::new();
        for item in sequence.iter() {
            let dict = item.downcast::<PyDict>()?;
            if dict
                .get_item("texture")?
                .is_some_and(|value| !value.is_none())
            {
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
            self.draw_gpu_triangles(vertices, BlendMode::Blend)?;
            return Ok(());
        }
        self.draw_shaded_face_vertices_cpu(&vertices)
    }

    pub(crate) fn draw_model_shaded_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<(f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        if self.gpu.is_some() && !self.cpu_compositing_active && cull_backfaces {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniform = crate::software3d::model_gpu_uniform(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    lights,
                    normal_material,
                    transform,
                )?;
                self.upload_stale_texture(false)?;
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_model(key, index_count, uniform);
                    self.performance_counters.direct_model_draws += 1;
                    self.performance_counters.gpu_draws += 1;
                    self.render_dirty = true;
                    self.offscreen_dirty = true;
                    self.pixels_stale = true;
                    self.texture_stale = false;
                    return Ok(());
                }
            }
        }
        let triangles = crate::software3d::model_handle_shaded_triangles_with_depth(
            model,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
            self.pixel_density,
        )?;
        if triangles.is_empty() {
            return Ok(());
        }
        self.performance_counters.direct_model_draws += 1;
        self.pending_3d_triangles
            .extend(triangles.into_iter().map(|triangle| Pending3dTriangle {
                depth: triangle.depth,
                vertices: triangle.vertices,
            }));
        self.render_dirty = true;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_model_textured_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        image: PyRef<'_, CanvasImage>,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<(f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<bool> {
        if image.width == 0 || image.height == 0 {
            return Ok(true);
        }
        if self.gpu.is_some() && !self.cpu_compositing_active && cull_backfaces {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniform = crate::software3d::model_gpu_uniform(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    lights,
                    normal_material,
                    transform,
                )?;
                self.upload_stale_texture(false)?;
                self.ensure_gpu_canvas_image_texture(&image)?;
                let linear_sampling = self.current_style.image_sampling != "nearest";
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_textured_model(key, image.key, index_count, uniform, linear_sampling);
                    self.performance_counters.direct_model_draws += 1;
                    self.performance_counters.gpu_draws += 1;
                    self.render_dirty = true;
                    self.offscreen_dirty = true;
                    self.pixels_stale = true;
                    self.texture_stale = false;
                    return Ok(true);
                }
            }
        }
        let triangles = crate::software3d::model_handle_textured_triangles_with_depth(
            model,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
            self.pixel_density,
        )?;
        if triangles.is_empty() {
            return Ok(true);
        }
        if self.gpu.is_none() || self.cpu_compositing_active {
            return Ok(false);
        }
        self.upload_stale_texture(false)?;
        self.ensure_gpu_canvas_image_texture(&image)?;
        let linear_sampling = self.current_style.image_sampling != "nearest";
        let blend_mode = self.current_style.blend_mode_kind;
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(false);
        };
        for triangle in triangles {
            let vertices = [
                triangle.vertices[0],
                triangle.vertices[1],
                triangle.vertices[2],
                triangle.vertices[0],
                triangle.vertices[2],
                triangle.vertices[2],
            ];
            gpu.draw_image(image.key, vertices, linear_sampling, blend_mode);
        }
        self.performance_counters.direct_model_draws += 1;
        self.performance_counters.gpu_draws += 1;
        self.render_dirty = true;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
        self.texture_stale = false;
        Ok(true)
    }

    pub(crate) fn flush_pending_3d_triangles(&mut self) {
        if self.pending_3d_triangles.is_empty() {
            return;
        }
        self.pending_3d_triangles
            .sort_by(|left, right| right.depth.total_cmp(&left.depth));
        let mut vertices = Vec::with_capacity(self.pending_3d_triangles.len() * 3);
        for triangle in self.pending_3d_triangles.drain(..) {
            vertices.extend(triangle.vertices);
        }
        if vertices.is_empty() {
            return;
        }
        if self.gpu.is_some() && !self.cpu_compositing_active {
            let _ = self.draw_gpu_triangles(vertices, BlendMode::Blend);
        } else {
            let _ = self.draw_shaded_face_vertices_cpu(&vertices);
        }
    }

    pub(crate) fn draw_shaded_face_vertices_cpu(
        &mut self,
        vertices: &[([f32; 2], crate::gpu::GpuColor)],
    ) -> PyResult<()> {
        for triangle in vertices.chunks_exact(3) {
            let color = triangle[0].1;
            let style = Style {
                fill: Some(Rgba {
                    r: color.r,
                    g: color.g,
                    b: color.b,
                    a: color.a,
                }),
                stroke: None,
                ..Style::default()
            };
            let points = [
                (triangle[0].0[0] as f64, triangle[0].0[1] as f64),
                (triangle[1].0[0] as f64, triangle[1].0[1] as f64),
                (triangle[2].0[0] as f64, triangle[2].0[1] as f64),
            ];
            self.draw_transformed_polygon(&points, &style, true)?;
        }
        Ok(())
    }

    fn ensure_gpu_canvas_image_texture(&mut self, image: &CanvasImage) -> PyResult<()> {
        let texture_version = self.texture_cache_versions.get(&image.key).copied();
        if texture_version == Some(image.version) {
            self.performance_counters.texture_cache_hits += 1;
            return Ok(());
        }
        self.performance_counters.texture_uploads += 1;
        self.evict_texture_cache_if_needed(image.key);
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(());
        };
        gpu.upload_texture(image.key, image.width, image.height, &image.pixels)
            .map_err(|err| {
                PyValueError::new_err(format!("Failed to upload image texture: {err}"))
            })?;
        self.texture_cache_versions.insert(image.key, image.version);
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
