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
        let has_path_segments = !state.captured_shape_path_segments().is_empty();
        let has_contours = !state.captured_shape_contours().is_empty();
        let result = if has_path_segments && !has_contours {
            if style.erasing {
                if !self.can_queue_gpu_erase(style) {
                    self.prepare_cpu_composite()
                } else {
                    if close && style.fill.is_some() {
                        self.draw_gpu_erase_path_fill_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            close,
                            matrix,
                            self.pixel_density,
                        )?;
                    }
                    if style.stroke.is_some() {
                        self.draw_gpu_erase_path_segments_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            close,
                            matrix,
                            self.pixel_density,
                            stroke_width(style.stroke_weight, self.pixel_density),
                        )?;
                    }
                    Ok(())
                }
            } else if self.can_queue_gpu_primitives(style) {
                if close {
                    if let Some(fill) = style.fill {
                        self.draw_gpu_path_fill_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            close,
                            matrix,
                            self.pixel_density,
                            fill,
                            style.blend_mode_kind,
                        )?;
                    }
                }
                if let Some(stroke) = style.stroke {
                    self.draw_gpu_path_segments_with_matrix(
                        state.captured_shape_path_segments(),
                        state.captured_shape_vertices(),
                        close,
                        matrix,
                        self.pixel_density,
                        stroke_width(style.stroke_weight, self.pixel_density),
                        stroke,
                        style.blend_mode_kind,
                    )?;
                }
                Ok(())
            } else {
                self.prepare_cpu_composite()
            }
        } else if has_path_segments && has_contours && close && style.fill.is_some() {
            Err(PyValueError::new_err(
                "Filled captured paths with contours require a GPU contour-fill implementation; CPU path tessellation is disabled.",
            ))
        } else if state.captured_shape_contours().is_empty() {
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
        let _ = (contours, matrix);
        Err(PyValueError::new_err(
            "CPU clip-mask rasterization is disabled; begin_clip() requires a GPU mask/stencil implementation.",
        ))
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
