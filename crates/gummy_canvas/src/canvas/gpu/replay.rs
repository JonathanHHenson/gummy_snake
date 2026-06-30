use crate::*;

impl Canvas {
    pub(super) fn replay_gpu_commands_on_cpu(
        &mut self,
        commands: &[crate::gpu::DrawCommand],
    ) -> bool {
        for command in commands {
            match command {
                crate::gpu::DrawCommand::Clear(color) => {
                    let rgba = [color.r, color.g, color.b, color.a];
                    fill_rgba_buffer(&mut self.pixels, &rgba);
                    self.present_pixels.fill(rgba_to_present_pixel(&rgba));
                }
                crate::gpu::DrawCommand::Triangles {
                    vertices,
                    blend_mode: _,
                    clip_id,
                } => {
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
                crate::gpu::DrawCommand::RetainedTriangles {
                    retained: crate::gpu::RetainedTriangleVertices { vertices, .. },
                    blend_mode: _,
                    clip_id,
                } => {
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
                crate::gpu::DrawCommand::PrimitiveInstances { .. }
                | crate::gpu::DrawCommand::RetainedPrimitiveInstances { .. } => {
                    return false;
                }
                crate::gpu::DrawCommand::Ellipse {
                    cx,
                    cy,
                    rx,
                    ry,
                    color,
                    blend_mode: _,
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
                crate::gpu::DrawCommand::BlendEllipse { .. } => {
                    return false;
                }
                crate::gpu::DrawCommand::PixelPrefix { .. } => {
                    return false;
                }
                crate::gpu::DrawCommand::Model { .. }
                | crate::gpu::DrawCommand::ModelInstances { .. }
                | crate::gpu::DrawCommand::TexturedModel { .. } => {
                    return false;
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
                crate::gpu::DrawCommand::Image { .. }
                | crate::gpu::DrawCommand::ImageBatch { .. } => {
                    return false;
                }
                crate::gpu::DrawCommand::Text { .. } => {
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
            self.erase_color,
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
            self.erase_color,
            BlendMode::Blend,
            None,
        ) else {
            return;
        };
        let color = Rgba::from_tuple((color.r, color.g, color.b, color.a));
        fill_axis_aligned_ellipse(&mut overlay, cx, cy, rx, ry, color);
    }
}
