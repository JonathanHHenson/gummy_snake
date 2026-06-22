use crate::*;

impl Canvas {
    pub(crate) fn prepare_cpu_composite(&mut self) {
        self.performance_counters.cpu_fallbacks += 1;
        let pending_clear = if self.offscreen_dirty && self.pixels_stale {
            self.gpu.as_ref().and_then(|gpu| gpu.only_pending_clear())
        } else {
            None
        };
        if let Some(color) = pending_clear {
            let rgba = [color.r, color.g, color.b, color.a];
            let packed = rgba_to_present_pixel(&rgba);
            fill_rgba_buffer(&mut self.pixels, &rgba);
            self.present_pixels.fill(packed);
            if let Some(gpu) = self.gpu.as_mut() {
                gpu.begin_frame();
            }
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.pixels_stale = false;
            self.texture_stale = true;
            self.cpu_compositing_active = true;
            return;
        }
        if self.offscreen_dirty && self.pixels_stale && self.materialize_gpu_primitives_on_cpu() {
            self.cpu_compositing_active = true;
            return;
        }
        if self.offscreen_dirty && self.pixels_stale {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.cpu_compositing_active = true;
    }

    pub(crate) fn upload_cpu_pixels(&mut self) -> PyResult<()> {
        self.performance_counters.pixel_uploads += 1;
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
        if readback && self.materialize_gpu_primitives_on_cpu() {
            self.performance_counters.gpu_frames_rendered += 1;
            self.performance_counters.pixel_readbacks += 1;
            return;
        }
        if self.gpu.is_none() {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
            return;
        }
        if readback {
            let readback_result = self
                .gpu
                .as_mut()
                .expect("checked above")
                .render_and_read_pixels();
            match readback_result {
                Ok(pixels) => {
                    self.performance_counters.gpu_frames_rendered += 1;
                    self.performance_counters.pixel_readbacks += 1;
                    self.pixels = pixels;
                    self.sync_present_pixels_from_rgba();
                    if let Some(gpu) = self.gpu.as_mut() {
                        gpu.begin_frame();
                    }
                    self.render_dirty = false;
                    self.offscreen_dirty = false;
                    self.pixels_stale = false;
                    self.texture_stale = false;
                }
                Err(err) => {
                    self.gpu_error = Some(err);
                    if let Some(gpu) = self.gpu.as_mut() {
                        gpu.begin_frame();
                    }
                    self.render_dirty = false;
                    self.offscreen_dirty = false;
                    self.pixels_stale = false;
                    self.texture_stale = false;
                }
            }
            return;
        }
        let Some(gpu) = self.gpu.as_mut() else {
            return;
        };
        gpu.render();
        self.performance_counters.gpu_frames_rendered += 1;
        gpu.begin_frame();
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = true;
        self.texture_stale = false;
    }

    pub(crate) fn read_gpu_pixels(&mut self) {
        if self.materialize_gpu_primitives_on_cpu() {
            self.performance_counters.pixel_readbacks += 1;
            return;
        }
        let Some(gpu) = self.gpu.as_mut() else {
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

    fn materialize_gpu_primitives_on_cpu(&mut self) -> bool {
        let Some(gpu) = self.gpu.as_ref() else {
            return false;
        };
        let commands = gpu.pending_commands().to_vec();
        if commands.is_empty() {
            return false;
        }
        if !self.replay_gpu_commands_on_cpu(&commands) {
            return false;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = true;
        true
    }

    fn replay_gpu_commands_on_cpu(&mut self, commands: &[crate::gpu::DrawCommand]) -> bool {
        for command in commands {
            match command {
                crate::gpu::DrawCommand::Clear(color) => {
                    let rgba = [color.r, color.g, color.b, color.a];
                    fill_rgba_buffer(&mut self.pixels, &rgba);
                    self.present_pixels.fill(rgba_to_present_pixel(&rgba));
                }
                crate::gpu::DrawCommand::Triangles { vertices, clip_id } => {
                    if *clip_id != 0 {
                        return false;
                    }
                    for triangle in vertices.chunks_exact(3) {
                        let points = [
                            (triangle[0].0[0] as f64, triangle[0].0[1] as f64),
                            (triangle[1].0[0] as f64, triangle[1].0[1] as f64),
                            (triangle[2].0[0] as f64, triangle[2].0[1] as f64),
                        ];
                        self.replay_triangle_on_cpu(&points, triangle[0].1, false);
                    }
                }
                crate::gpu::DrawCommand::Ellipse {
                    cx,
                    cy,
                    rx,
                    ry,
                    color,
                    clip_id,
                } => {
                    if *clip_id != 0 {
                        return false;
                    }
                    self.replay_ellipse_on_cpu(
                        (*cx).into(),
                        (*cy).into(),
                        (*rx).into(),
                        (*ry).into(),
                        *color,
                    );
                }
                crate::gpu::DrawCommand::EraseTriangles { vertices, clip_id } => {
                    if *clip_id != 0 {
                        return false;
                    }
                    for triangle in vertices.chunks_exact(3) {
                        let points = [
                            (triangle[0].0[0] as f64, triangle[0].0[1] as f64),
                            (triangle[1].0[0] as f64, triangle[1].0[1] as f64),
                            (triangle[2].0[0] as f64, triangle[2].0[1] as f64),
                        ];
                        self.replay_triangle_on_cpu(&points, triangle[0].1, true);
                    }
                }
                crate::gpu::DrawCommand::Image {
                    key: _,
                    vertices: _,
                    linear: _,
                    clip_id: _,
                } => {
                    return false;
                }
            }
        }
        true
    }

    fn replay_triangle_on_cpu(
        &mut self,
        points: &[Point; 3],
        color: crate::gpu::GpuColor,
        erasing: bool,
    ) {
        let bounds = clipped_bounds(points, 0.0, self.physical_width, self.physical_height);
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            erasing,
            BlendMode::Blend,
            None,
        ) else {
            return;
        };
        let color = Rgba::from_tuple((color.r, color.g, color.b, color.a));
        fill_even_odd_polygon(&mut overlay, &[points], color);
    }

    fn replay_ellipse_on_cpu(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        color: crate::gpu::GpuColor,
    ) {
        let bounds = ellipse_bounds(
            cx,
            cy,
            rx,
            ry,
            0.0,
            self.physical_width,
            self.physical_height,
        );
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            false,
            BlendMode::Blend,
            None,
        ) else {
            return;
        };
        let color = Rgba::from_tuple((color.r, color.g, color.b, color.a));
        fill_axis_aligned_ellipse(&mut overlay, cx, cy, rx, ry, color);
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

    pub(crate) fn draw_gpu_even_odd_spans(
        &mut self,
        bounds: (usize, usize, usize, usize),
        rings: &[&[Point]],
        color: Rgba,
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
        self.draw_gpu_triangles(vertices)
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
            if style.stroke.is_none() {
                self.draw_gpu_filled_ellipse(cx, cy, rx, ry, fill)?;
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

    pub(crate) fn draw_gpu_filled_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        color: Rgba,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_filled_ellipse(
                cx as f32,
                cy as f32,
                rx as f32,
                ry as f32,
                crate::raster::gpu_color(color),
            );
            self.performance_counters.gpu_draws += 1;
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
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

    pub(crate) fn draw_gpu_erase_triangles(
        &mut self,
        vertices: Vec<([f32; 2], crate::gpu::GpuColor)>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_erase_triangles(vertices);
            self.performance_counters.gpu_draws += 1;
            self.render_dirty = true;
            self.offscreen_dirty = true;
            self.pixels_stale = true;
        }
        Ok(())
    }
}
