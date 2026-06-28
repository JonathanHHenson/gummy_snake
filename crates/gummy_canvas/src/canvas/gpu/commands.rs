use crate::*;

impl Canvas {
    pub(crate) fn draw_gpu_text(
        &mut self,
        text: &str,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        font_size: f64,
        line_height: f64,
        color: Rgba,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_text(
                text.to_string(),
                x as f32,
                y as f32,
                width as f32,
                height as f32,
                font_size as f32,
                line_height as f32,
                crate::raster::gpu_color(color),
            );
            self.record_native_text_draw();
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
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_filled_ellipse(
                cx as f32,
                cy as f32,
                rx as f32,
                ry as f32,
                crate::raster::gpu_color(color),
                blend_mode,
            );
            self.record_native_ellipse_draw(blend_mode);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_triangles(
        &mut self,
        vertices: Vec<([f32; 2], crate::gpu::GpuColor)>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            let vertex_count = vertices.len();
            gpu.draw_triangles(vertices, blend_mode);
            self.record_native_triangle_draw(blend_mode, vertex_count);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_retained_triangles(
        &mut self,
        key: u64,
        vertices: std::sync::Arc<Vec<([f32; 2], crate::gpu::GpuColor)>>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            let vertex_count = vertices.len();
            gpu.draw_retained_triangles(key, vertices, blend_mode);
            self.record_native_triangle_draw(blend_mode, vertex_count);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_primitive_instances(
        &mut self,
        instances: Vec<crate::gpu::PrimitiveInstance>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_primitive_instances(instances, blend_mode);
            self.record_native_primitive_instance_draw(blend_mode);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_retained_primitive_instances(
        &mut self,
        key: u64,
        instances: std::sync::Arc<Vec<crate::gpu::PrimitiveInstance>>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_retained_primitive_instances(key, instances, blend_mode);
            self.record_native_primitive_instance_draw(blend_mode);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_erase_triangles(
        &mut self,
        mut vertices: Vec<([f32; 2], crate::gpu::GpuColor)>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            for (_, color) in &mut vertices {
                color.r = self.erase_color.r;
                color.g = self.erase_color.g;
                color.b = self.erase_color.b;
                color.a = 255;
            }
            let vertex_count = vertices.len();
            gpu.draw_erase_triangles(vertices);
            self.record_native_erase_draw(vertex_count);
        }
        Ok(())
    }
}
