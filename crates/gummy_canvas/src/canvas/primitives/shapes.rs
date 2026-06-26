use crate::*;

impl Canvas {
    pub(crate) fn draw_captured_shape_current_impl(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
        close: bool,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.draw_captured_shape_with_style(state, &style, self.current_matrix, close)
    }

    pub(crate) fn draw_captured_shape_impl(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.draw_captured_shape_with_style(state, &style, matrix, close)
    }

    fn draw_captured_shape_with_style(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
        style: &Style,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let result = if state.captured_shape_contours().is_empty() {
            self.polygon_with_style(
                state.captured_shape_vertices().to_vec(),
                style,
                matrix,
                close,
            )
        } else {
            self.complex_polygon_with_style(
                state.captured_shape_vertices().to_vec(),
                state.captured_shape_contours().to_vec(),
                style,
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
        self.begin_clip_captured_impl(state, self.current_matrix)
    }

    pub(crate) fn begin_clip_captured_impl(
        &mut self,
        state: &mut crate::sketch_state::SketchContextState,
        matrix: Matrix,
    ) -> PyResult<()> {
        let result = self.begin_clip_impl(
            state.captured_shape_vertices().to_vec(),
            state.captured_shape_contours().to_vec(),
            matrix,
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
}
