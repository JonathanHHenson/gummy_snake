use crate::*;

use super::instances::{
    transformed_ellipse_instance, transformed_polygon_fill_instances, transformed_rect_instance,
    transformed_triangle_instance,
};

impl Canvas {
    pub(crate) fn draw_gpu_axis_aligned_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        style: &Style,
        pixel_density: f64,
    ) -> PyResult<()> {
        if rx <= 0.0 || ry <= 0.0 {
            return Ok(());
        }
        let (x, y, width, height) = (cx - rx, cy - ry, rx * 2.0, ry * 2.0);
        let matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0);
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if style.fill.is_some() {
                self.draw_gpu_erase_transformed_ellipse(x, y, width, height, matrix, 1.0, 0.0)?;
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_transformed_ellipse(
                    x,
                    y,
                    width,
                    height,
                    matrix,
                    1.0,
                    stroke_width(style.stroke_weight, pixel_density),
                )?;
            }
            return Ok(());
        }
        if let Some(fill) = style.fill {
            self.draw_gpu_transformed_ellipse(
                x,
                y,
                width,
                height,
                matrix,
                1.0,
                fill,
                0.0,
                style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_transformed_ellipse(
                x,
                y,
                width,
                height,
                matrix,
                1.0,
                stroke,
                stroke_width(style.stroke_weight, pixel_density),
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_transformed_rect(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_primitive_instances(
            vec![transformed_rect_instance(
                (x, y),
                (x + width, y + height),
                matrix,
                pixel_density,
                color,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_transformed_triangle(
        &mut self,
        p0: Point,
        p1: Point,
        p2: Point,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.draw_gpu_primitive_instances(
            vec![transformed_triangle_instance(
                p0,
                p1,
                p2,
                matrix,
                pixel_density,
                color,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_erase_transformed_rect(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_erase_primitive_instances(vec![transformed_rect_instance(
            (x, y),
            (x + width, y + height),
            matrix,
            pixel_density,
            self.erase_color,
        )])
    }

    pub(crate) fn draw_gpu_erase_transformed_triangle(
        &mut self,
        p0: Point,
        p1: Point,
        p2: Point,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        self.draw_gpu_erase_primitive_instances(vec![transformed_triangle_instance(
            p0,
            p1,
            p2,
            matrix,
            pixel_density,
            self.erase_color,
        )])
    }

    pub(crate) fn draw_gpu_transformed_polygon_fill(
        &mut self,
        points: &[Point],
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if points.len() < 3 {
            return Ok(());
        }
        self.draw_gpu_primitive_instances(
            transformed_polygon_fill_instances(points, matrix, pixel_density, color),
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_erase_transformed_polygon_fill(
        &mut self,
        points: &[Point],
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if points.len() < 3 {
            return Ok(());
        }
        self.draw_gpu_erase_primitive_instances(transformed_polygon_fill_instances(
            points,
            matrix,
            pixel_density,
            self.erase_color,
        ))
    }

    pub(crate) fn draw_gpu_transformed_ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        stroke_width: f64,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_primitive_instances(
            vec![transformed_ellipse_instance(
                (x, y),
                (x + width, y + height),
                matrix,
                pixel_density,
                color,
                stroke_width,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_erase_transformed_ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_erase_primitive_instances(vec![transformed_ellipse_instance(
            (x, y),
            (x + width, y + height),
            matrix,
            pixel_density,
            self.erase_color,
            stroke_width,
        )])
    }

    pub(crate) fn can_draw_gpu_blend_ellipse(&self, style: &Style) -> bool {
        self.gpu.is_some()
            && !style.erasing
            && style.stroke.is_none()
            && style.fill.is_some()
            && matches!(
                style.blend_mode_kind,
                BlendMode::Multiply
                    | BlendMode::Screen
                    | BlendMode::Difference
                    | BlendMode::Exclusion
                    | BlendMode::Darkest
                    | BlendMode::Lightest
            )
            && self.clip_masks.is_empty()
    }

    pub(crate) fn can_draw_gpu_text(&self, style: &Style, matrix: Matrix) -> bool {
        self.gpu.is_some()
            && self.runtime.is_none()
            && !self.cpu_compositing_active
            && self.clip_masks.is_empty()
            && !style.erasing
            && style.fill.is_some()
            && style.stroke.is_none()
            && style.blend_mode_kind == BlendMode::Blend
            && style.text_font_path.is_none()
            && matrix == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            && self
                .gpu
                .as_ref()
                .is_none_or(|gpu| gpu.can_append_glyphon_text_command())
    }

    pub(crate) fn draw_gpu_blend_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        style: &Style,
    ) -> PyResult<()> {
        let Some(fill) = style.fill else {
            return Ok(());
        };
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_blend_ellipse(
                cx as f32,
                cy as f32,
                rx as f32,
                ry as f32,
                crate::raster::gpu_color(fill),
                style.blend_mode_kind,
            );
            self.record_native_region_effect_draw(true);
        }
        Ok(())
    }
}
