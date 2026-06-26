use crate::*;

impl Canvas {
    pub(crate) fn draw_gpu_polygon(
        &mut self,
        points: &[Point],
        style: &Style,
        close: bool,
        pixel_density: f64,
    ) -> PyResult<()> {
        if style.erasing {
            return Ok(());
        }
        if close && points.len() >= 3 {
            if let Some(fill) = style.fill {
                let mut vertices = Vec::with_capacity((points.len() - 2) * 3);
                for index in 1..points.len() - 1 {
                    push_triangle(
                        &mut vertices,
                        points[0],
                        points[index],
                        points[index + 1],
                        fill,
                    );
                }
                self.draw_gpu_triangles(vertices, style.blend_mode_kind)?;
            }
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline(
                points,
                close,
                stroke_width(style.stroke_weight, pixel_density),
                stroke,
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_polyline(
        &mut self,
        points: &[Point],
        close: bool,
        stroke_width: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if points.len() < 2 {
            return Ok(());
        }
        for pair in points.windows(2) {
            self.draw_gpu_segment(pair[0], pair[1], stroke_width, color, blend_mode)?;
        }
        if close {
            self.draw_gpu_segment(
                *points.last().expect("non-empty points"),
                points[0],
                stroke_width,
                color,
                blend_mode,
            )?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_even_odd_spans(
        &mut self,
        bounds: (usize, usize, usize, usize),
        rings: &[&[Point]],
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        let mut vertices = Vec::new();
        for_even_odd_spans(bounds, rings, |y, start, end| {
            let y0 = y as f64;
            let y1 = y0 + 1.0;
            let x0 = start as f64;
            let x1 = end as f64;
            push_triangle(&mut vertices, (x0, y0), (x1, y0), (x1, y1), color);
            push_triangle(&mut vertices, (x0, y0), (x1, y1), (x0, y1), color);
        });
        self.draw_gpu_triangles(vertices, blend_mode)
    }

    pub(crate) fn draw_gpu_segment(
        &mut self,
        p1: Point,
        p2: Point,
        stroke_width: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        let dx = p2.0 - p1.0;
        let dy = p2.1 - p1.1;
        let length = (dx * dx + dy * dy).sqrt();
        if length <= f64::EPSILON {
            self.draw_gpu_disc(p1.0, p1.1, (stroke_width / 2.0).max(0.5), color, blend_mode)?;
            return Ok(());
        }
        let half = (stroke_width / 2.0).max(0.5);
        let nx = -dy / length * half;
        let ny = dx / length * half;
        let a = (p1.0 + nx, p1.1 + ny);
        let b = (p1.0 - nx, p1.1 - ny);
        let c = (p2.0 - nx, p2.1 - ny);
        let d = (p2.0 + nx, p2.1 + ny);
        let mut vertices = Vec::with_capacity(6);
        push_triangle(&mut vertices, a, b, c, color);
        push_triangle(&mut vertices, a, c, d, color);
        self.draw_gpu_triangles(vertices, blend_mode)
    }

    pub(crate) fn draw_gpu_disc(
        &mut self,
        cx: f64,
        cy: f64,
        radius: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if radius <= 0.0 {
            return Ok(());
        }
        let steps = 24usize;
        let mut vertices = Vec::with_capacity(steps * 3);
        for index in 0..steps {
            let a = 2.0 * PI * index as f64 / steps as f64;
            let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
            push_triangle(
                &mut vertices,
                (cx, cy),
                (cx + a.cos() * radius, cy + a.sin() * radius),
                (cx + b.cos() * radius, cy + b.sin() * radius),
                color,
            );
        }
        self.draw_gpu_triangles(vertices, blend_mode)
    }

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
        if let Some(fill) = style.fill {
            if style.stroke.is_none() {
                if style.erasing {
                    let steps = 64usize;
                    let mut vertices = Vec::with_capacity(steps * 3);
                    for index in 0..steps {
                        let a = 2.0 * PI * index as f64 / steps as f64;
                        let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
                        push_triangle(
                            &mut vertices,
                            (cx, cy),
                            (cx + a.cos() * rx, cy + a.sin() * ry),
                            (cx + b.cos() * rx, cy + b.sin() * ry),
                            fill,
                        );
                    }
                    self.draw_gpu_erase_triangles(vertices)?;
                    return Ok(());
                }
                self.draw_gpu_filled_ellipse(cx, cy, rx, ry, fill, style.blend_mode_kind)?;
                return Ok(());
            }
            let steps = 64usize;
            let mut vertices = Vec::with_capacity(steps * 3);
            for index in 0..steps {
                let a = 2.0 * PI * index as f64 / steps as f64;
                let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
                push_triangle(
                    &mut vertices,
                    (cx, cy),
                    (cx + a.cos() * rx, cy + a.sin() * ry),
                    (cx + b.cos() * rx, cy + b.sin() * ry),
                    fill,
                );
            }
            if style.erasing {
                self.draw_gpu_erase_triangles(vertices)?;
            } else {
                self.draw_gpu_triangles(vertices, style.blend_mode_kind)?;
            }
        }
        if let Some(stroke) = style.stroke {
            let half_width = (stroke_width(style.stroke_weight, pixel_density) / 2.0).max(0.5);
            let outer_rx = rx + half_width;
            let outer_ry = ry + half_width;
            let inner_rx = (rx - half_width).max(0.0);
            let inner_ry = (ry - half_width).max(0.0);
            let steps = 64usize;
            let mut vertices = Vec::with_capacity(steps * 6);
            for index in 0..steps {
                let a = 2.0 * PI * index as f64 / steps as f64;
                let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
                let outer_a = (cx + a.cos() * outer_rx, cy + a.sin() * outer_ry);
                let inner_a = (cx + a.cos() * inner_rx, cy + a.sin() * inner_ry);
                let inner_b = (cx + b.cos() * inner_rx, cy + b.sin() * inner_ry);
                let outer_b = (cx + b.cos() * outer_rx, cy + b.sin() * outer_ry);
                push_triangle(&mut vertices, outer_a, inner_a, inner_b, stroke);
                push_triangle(&mut vertices, outer_a, inner_b, outer_b, stroke);
            }
            if style.erasing {
                self.draw_gpu_erase_triangles(vertices)?;
            } else {
                self.draw_gpu_triangles(vertices, style.blend_mode_kind)?;
            }
        }
        Ok(())
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
            self.record_native_region_effect_draw();
        }
        Ok(())
    }
}
