use crate::canvas_state::Canvas;
use crate::raster::{stroke_width, Matrix};
use crate::types::{Rgba, Style};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;

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
        } else if has_path_segments && has_contours {
            if style.erasing {
                if !self.can_queue_gpu_erase(style) {
                    self.prepare_cpu_composite()
                } else {
                    if close && style.fill.is_some() {
                        self.draw_gpu_erase_complex_path_fill_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            state.captured_shape_contours(),
                            close,
                            matrix,
                            self.pixel_density,
                        )?;
                    }
                    if style.stroke.is_some() {
                        let width = stroke_width(style.stroke_weight, self.pixel_density);
                        self.draw_gpu_erase_path_segments_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            close,
                            matrix,
                            self.pixel_density,
                            width,
                        )?;
                        for contour in state.captured_shape_contours() {
                            self.draw_gpu_erase_polyline_with_matrix(
                                contour,
                                true,
                                matrix,
                                self.pixel_density,
                                width,
                            )?;
                        }
                    }
                    Ok(())
                }
            } else if self.can_queue_gpu_primitives(style) {
                if close {
                    if let Some(fill) = style.fill {
                        self.draw_gpu_complex_path_fill_with_matrix(
                            state.captured_shape_path_segments(),
                            state.captured_shape_vertices(),
                            state.captured_shape_contours(),
                            close,
                            matrix,
                            self.pixel_density,
                            fill,
                            style.blend_mode_kind,
                        )?;
                    }
                }
                if let Some(stroke) = style.stroke {
                    let width = stroke_width(style.stroke_weight, self.pixel_density);
                    self.draw_gpu_path_segments_with_matrix(
                        state.captured_shape_path_segments(),
                        state.captured_shape_vertices(),
                        close,
                        matrix,
                        self.pixel_density,
                        width,
                        stroke,
                        style.blend_mode_kind,
                    )?;
                    for contour in state.captured_shape_contours() {
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
            } else {
                self.prepare_cpu_composite()
            }
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
        let result = self.begin_clip_captured_with_segments_impl(state, matrix);
        if result.is_ok() {
            self.performance_counters.direct_shape_finalizations += 1;
            state.reset_captured_shape();
        }
        result
    }

    fn begin_clip_captured_with_segments_impl(
        &mut self,
        state: &crate::sketch_state::SketchContextState,
        matrix: Matrix,
    ) -> PyResult<()> {
        let outer = state.captured_shape_vertices();
        if outer.len() < 3 {
            return Err(PyValueError::new_err(
                "begin_clip() requires at least three vertices.",
            ));
        }
        let records = self.gpu_complex_path_fill_records(
            state.captured_shape_path_segments(),
            outer,
            state.captured_shape_contours(),
            true,
            matrix,
            self.pixel_density,
            Rgba {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            },
        );
        self.push_gpu_clip_path(records)
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
        let records = self.gpu_complex_polygon_fill_records(
            &outer,
            &contours,
            matrix,
            self.pixel_density,
            Rgba {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            },
        );
        self.push_gpu_clip_path(records)
    }

    fn push_gpu_clip_path(&mut self, records: Vec<crate::gpu::StrokePathRecord>) -> PyResult<()> {
        let Some(gpu) = self.gpu.as_mut() else {
            return self.prepare_cpu_composite();
        };
        gpu.push_clip_path(&records)
            .map_err(PyValueError::new_err)?;
        self.clip_masks.push(Vec::new());
        self.clip_bounds
            .push((0, 0, self.physical_width, self.physical_height));
        Ok(())
    }

    pub(crate) fn end_clip_impl(&mut self) -> PyResult<()> {
        self.clip_masks
            .pop()
            .ok_or_else(|| PyValueError::new_err("end_clip() called without an active clip."))?;
        self.clip_bounds.pop();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.pop_clip_path();
        }
        Ok(())
    }
}
