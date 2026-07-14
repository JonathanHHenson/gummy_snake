use crate::canvas_state::Canvas;
use crate::config::*;
use crate::raster::{stroke_width, Matrix};
use crate::runtime::style::*;
use crate::types::Style;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use std::f64::consts::PI;

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
            if parsed_style.erasing
                && self.gpu.is_some()
                && !self.cpu_compositing_active
                && parsed_style.blend_mode == BLEND_MODE_BLEND
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
            if self.can_queue_gpu_primitives(parsed_style) {
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
            if self.can_draw_gpu_destination_blend_shape(parsed_style) {
                self.draw_gpu_destination_blend_ellipse(cx, cy, rx, ry, parsed_style)?;
                return Ok(());
            }
            return self.prepare_cpu_composite();
        }

        if parsed_style.fill.is_none() && parsed_style.stroke.is_none() {
            return Ok(());
        }
        if parsed_style.erasing {
            if !self.can_queue_gpu_erase(parsed_style) {
                return self.prepare_cpu_composite();
            }
            if parsed_style.fill.is_some() {
                self.draw_gpu_erase_transformed_ellipse(
                    x,
                    y,
                    width,
                    height,
                    matrix,
                    self.pixel_density,
                    0.0,
                )?;
            }
            if parsed_style.stroke.is_some() {
                self.draw_gpu_erase_transformed_ellipse(
                    x,
                    y,
                    width,
                    height,
                    matrix,
                    self.pixel_density,
                    stroke_width(parsed_style.stroke_weight, self.pixel_density),
                )?;
            }
            return Ok(());
        }
        if !self.can_queue_gpu_primitives(parsed_style) {
            return self.prepare_cpu_composite();
        }
        if let Some(fill) = parsed_style.fill {
            self.draw_gpu_transformed_ellipse(
                x,
                y,
                width,
                height,
                matrix,
                self.pixel_density,
                fill,
                0.0,
                parsed_style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = parsed_style.stroke {
            self.draw_gpu_transformed_ellipse(
                x,
                y,
                width,
                height,
                matrix,
                self.pixel_density,
                stroke,
                stroke_width(parsed_style.stroke_weight, self.pixel_density),
                parsed_style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn arc_impl(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        stop: f64,
        mode: &str,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let parsed_style = self.cached_style(style)?;
        self.arc_with_style(
            x,
            y,
            width,
            height,
            start,
            stop,
            mode,
            &parsed_style,
            matrix,
        )
    }

    pub(crate) fn arc_with_style(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        mut stop: f64,
        mode: &str,
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        let rx = width / 2.0;
        let ry = height / 2.0;
        while stop < start {
            stop += 2.0 * PI;
        }
        ensure_supported_style(parsed_style)?;
        if parsed_style.fill.is_none() && parsed_style.stroke.is_none() {
            return Ok(());
        }
        if parsed_style.erasing {
            if !self.can_queue_gpu_erase(parsed_style) {
                return self.prepare_cpu_composite();
            }
            if parsed_style.fill.is_some() {
                self.draw_gpu_erase_arc_fill_with_matrix(
                    (cx, cy),
                    (rx, ry),
                    start,
                    stop,
                    mode,
                    matrix,
                    self.pixel_density,
                )?;
            }
            if parsed_style.stroke.is_some() {
                self.draw_gpu_erase_arc_stroke_with_matrix(
                    (cx, cy),
                    (rx, ry),
                    start,
                    stop,
                    mode,
                    matrix,
                    self.pixel_density,
                    stroke_width(parsed_style.stroke_weight, self.pixel_density),
                )?;
            }
            return Ok(());
        }
        if !self.can_queue_gpu_primitives(parsed_style) {
            return self.prepare_cpu_composite();
        }
        if let Some(fill) = parsed_style.fill {
            self.draw_gpu_arc_fill_with_matrix(
                (cx, cy),
                (rx, ry),
                start,
                stop,
                mode,
                matrix,
                self.pixel_density,
                fill,
                parsed_style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = parsed_style.stroke {
            self.draw_gpu_arc_stroke_with_matrix(
                (cx, cy),
                (rx, ry),
                start,
                stop,
                mode,
                matrix,
                self.pixel_density,
                stroke_width(parsed_style.stroke_weight, self.pixel_density),
                stroke,
                parsed_style.blend_mode_kind,
            )?;
        }
        Ok(())
    }
}
