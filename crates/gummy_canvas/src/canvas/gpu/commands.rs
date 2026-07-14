use crate::canvas_state::Canvas;
use crate::types::{BlendMode, Rgba};
use pyo3::prelude::*;

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

    pub(crate) fn draw_gpu_stroke_path(
        &mut self,
        records: Vec<crate::gpu::StrokePathRecord>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_stroke_path(records, blend_mode);
            self.record_native_primitive_instance_draw(blend_mode);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_fill_path(
        &mut self,
        records: Vec<crate::gpu::StrokePathRecord>,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_fill_path(records, blend_mode);
            self.record_native_primitive_instance_draw(blend_mode);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_erase_primitive_instances(
        &mut self,
        mut instances: Vec<crate::gpu::PrimitiveInstance>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        let erase_color = crate::gpu::GpuColor {
            r: self.erase_color.r,
            g: self.erase_color.g,
            b: self.erase_color.b,
            a: 255,
        }
        .as_float();
        if let Some(gpu) = self.gpu.as_mut() {
            for instance in &mut instances {
                instance.color = erase_color;
            }
            let instance_count = instances.len();
            gpu.draw_erase_primitive_instances(instances);
            self.record_native_erase_draw(instance_count * 6);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_erase_stroke_path(
        &mut self,
        mut records: Vec<crate::gpu::StrokePathRecord>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        let erase_color = crate::gpu::GpuColor {
            r: self.erase_color.r,
            g: self.erase_color.g,
            b: self.erase_color.b,
            a: 255,
        }
        .as_float();
        if let Some(gpu) = self.gpu.as_mut() {
            if records.len() > 2 {
                records[2] = erase_color;
            }
            gpu.draw_erase_stroke_path(records);
            self.record_native_erase_draw(6);
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_erase_fill_path(
        &mut self,
        mut records: Vec<crate::gpu::StrokePathRecord>,
    ) -> PyResult<()> {
        self.upload_stale_texture(false)?;
        let erase_color = crate::gpu::GpuColor {
            r: self.erase_color.r,
            g: self.erase_color.g,
            b: self.erase_color.b,
            a: 255,
        }
        .as_float();
        if let Some(gpu) = self.gpu.as_mut() {
            if records.len() > 2 {
                records[2] = erase_color;
            }
            gpu.draw_erase_fill_path(records);
            self.record_native_erase_draw(6);
        }
        Ok(())
    }
}
