use crate::*;

impl Canvas {
    pub(crate) fn prepare_cpu_composite(&mut self) {
        self.performance_counters.cpu_fallbacks += 1;
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
    }

    pub(crate) fn upload_cpu_pixels(&mut self) -> PyResult<()> {
        self.performance_counters.pixel_uploads += 1;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = true;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = true;
        Ok(())
    }

    pub(crate) fn upload_stale_texture(&mut self, consume_mirrored_commands: bool) -> PyResult<()> {
        if !self.texture_stale {
            return Ok(());
        }
        if let Some(gpu) = self.gpu.as_mut() {
            self.performance_counters.pixel_uploads += 1;
            gpu.upload_pixels(&self.pixels)
                .map_err(|err| PyValueError::new_err(format!("Failed to upload pixels: {err}")))?;
            if consume_mirrored_commands {
                gpu.begin_frame();
            }
        }
        self.texture_stale = false;
        if consume_mirrored_commands {
            self.offscreen_dirty = false;
            self.pixels_stale = false;
        }
        Ok(())
    }

    pub(crate) fn render_gpu_frame(&mut self, readback: bool) {
        if self.upload_stale_texture(false).is_err() {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
            return;
        }
        let Some(gpu) = self.gpu.as_mut() else {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
            return;
        };
        gpu.render();
        self.performance_counters.gpu_frames_rendered += 1;
        gpu.begin_frame();
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = true;
        self.texture_stale = false;
        if readback {
            self.read_gpu_pixels();
        }
    }

    pub(crate) fn read_gpu_pixels(&mut self) {
        let Some(gpu) = self.gpu.as_ref() else {
            self.pixels_stale = false;
            return;
        };
        match gpu.read_pixels() {
            Ok(pixels) => {
                self.performance_counters.pixel_readbacks += 1;
                self.pixels = pixels;
                self.sync_present_pixels_from_rgba();
                self.pixels_stale = false;
            }
            Err(err) => {
                self.gpu_error = Some(err);
                self.pixels_stale = false;
            }
        }
    }

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
                self.draw_gpu_triangles(vertices)?;
            }
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline(
                points,
                close,
                stroke_width(style.stroke_weight, pixel_density),
                stroke,
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
    ) -> PyResult<()> {
        if points.len() < 2 {
            return Ok(());
        }
        for pair in points.windows(2) {
            self.draw_gpu_segment(pair[0], pair[1], stroke_width, color)?;
        }
        if close {
            self.draw_gpu_segment(
                *points.last().expect("non-empty points"),
                points[0],
                stroke_width,
                color,
            )?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_segment(
        &mut self,
        p1: Point,
        p2: Point,
        stroke_width: f64,
        color: Rgba,
    ) -> PyResult<()> {
        let dx = p2.0 - p1.0;
        let dy = p2.1 - p1.1;
        let length = (dx * dx + dy * dy).sqrt();
        if length <= f64::EPSILON {
            self.draw_gpu_disc(p1.0, p1.1, (stroke_width / 2.0).max(0.5), color)?;
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
        self.draw_gpu_triangles(vertices)
    }

    pub(crate) fn draw_gpu_disc(
        &mut self,
        cx: f64,
        cy: f64,
        radius: f64,
        color: Rgba,
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
        self.draw_gpu_triangles(vertices)
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
        if style.erasing || rx <= 0.0 || ry <= 0.0 {
            return Ok(());
        }
        if let Some(fill) = style.fill {
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
            self.draw_gpu_triangles(vertices)?;
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
            self.draw_gpu_triangles(vertices)?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_triangles(
        &mut self,
        vertices: Vec<([f32; 2], crate::gpu::GpuColor)>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_triangles(vertices);
            self.performance_counters.gpu_draws += 1;
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        }
        Ok(())
    }
}
