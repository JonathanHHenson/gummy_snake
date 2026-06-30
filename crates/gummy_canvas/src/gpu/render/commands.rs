use crate::gpu::types::*;
use crate::BlendMode;
use wgpu::util::DeviceExt;

impl GpuRenderer {
    pub fn begin_frame(&mut self) {
        self.commands.clear();
        self.clip_textures.truncate(1);
        self.current_clip_id = 0;
    }

    pub fn set_clear_color(&mut self, color: GpuColor) {
        self.clear_color = color;
        self.commands.push(DrawCommand::Clear(color));
    }

    pub fn clear_transparent(&mut self) {
        self.set_clear_color(GpuColor {
            r: 0,
            g: 0,
            b: 0,
            a: 0,
        });
    }

    pub fn draw_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>, blend_mode: BlendMode) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::Triangles {
                vertices,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_retained_triangles(
        &mut self,
        key: u64,
        vertices: std::sync::Arc<Vec<([f32; 2], GpuColor)>>,
        blend_mode: BlendMode,
    ) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::RetainedTriangles {
                retained: RetainedTriangleVertices { key, vertices },
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_primitive_instances(
        &mut self,
        instances: Vec<PrimitiveInstance>,
        blend_mode: BlendMode,
    ) {
        if !instances.is_empty() {
            self.commands.push(DrawCommand::PrimitiveInstances {
                instances,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_retained_primitive_instances(
        &mut self,
        key: u64,
        instances: std::sync::Arc<Vec<PrimitiveInstance>>,
        blend_mode: BlendMode,
    ) {
        if !instances.is_empty() {
            self.commands.push(DrawCommand::RetainedPrimitiveInstances {
                retained: RetainedPrimitiveInstances { key, instances },
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn ensure_model_mesh(
        &mut self,
        key: u64,
        vertices: &[ModelVertex],
        indices: &[u32],
    ) -> Result<u32, String> {
        if let Some(mesh) = self.model_meshes.get(&key) {
            return Ok(mesh.index_count);
        }
        if vertices.is_empty() || indices.is_empty() {
            return Ok(0);
        }
        let index_count = u32::try_from(indices.len())
            .map_err(|_| "model index count exceeds GPU draw limits".to_owned())?;
        let vertex_buffer = self
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("gummy_canvas model vertices"),
                contents: bytemuck::cast_slice(vertices),
                usage: wgpu::BufferUsages::VERTEX,
            });
        let index_buffer = self
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("gummy_canvas model indices"),
                contents: bytemuck::cast_slice(indices),
                usage: wgpu::BufferUsages::INDEX,
            });
        self.model_meshes.insert(
            key,
            GpuModelMesh {
                _vertex_buffer: vertex_buffer,
                _index_buffer: index_buffer,
                index_count,
            },
        );
        self.vertex_buffer_allocations += 2;
        Ok(index_count)
    }

    pub fn draw_model(&mut self, key: u64, index_count: u32, uniform: ModelUniform) {
        if index_count == 0 {
            return;
        }
        if let Some(last) = self.commands.last_mut() {
            match last {
                DrawCommand::Model {
                    key: previous_key,
                    index_count: previous_index_count,
                    uniform: previous_uniform,
                } if *previous_key == key && *previous_index_count == index_count => {
                    let first_uniform = *previous_uniform;
                    *last = DrawCommand::ModelInstances {
                        key,
                        index_count,
                        uniforms: vec![first_uniform, uniform],
                    };
                    return;
                }
                DrawCommand::ModelInstances {
                    key: previous_key,
                    index_count: previous_index_count,
                    uniforms,
                } if *previous_key == key && *previous_index_count == index_count => {
                    uniforms.push(uniform);
                    return;
                }
                _ => {}
            }
        }
        self.commands.push(DrawCommand::Model {
            key,
            index_count,
            uniform,
        });
    }

    pub fn draw_model_instances(
        &mut self,
        key: u64,
        index_count: u32,
        uniforms: Vec<ModelUniform>,
    ) {
        if index_count > 0 && !uniforms.is_empty() {
            self.commands.push(DrawCommand::ModelInstances {
                key,
                index_count,
                uniforms,
            });
        }
    }

    pub fn draw_textured_model(
        &mut self,
        model_key: u64,
        texture_key: u64,
        index_count: u32,
        uniform: ModelUniform,
        linear: bool,
    ) {
        if index_count > 0 {
            self.commands.push(DrawCommand::TexturedModel {
                model_key,
                texture_key,
                index_count,
                uniform,
                linear,
            });
        }
    }

    pub fn draw_filled_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::Ellipse {
                cx,
                cy,
                rx,
                ry,
                color,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_blend_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::BlendEllipse {
                cx,
                cy,
                rx,
                ry,
                color,
                blend_mode,
            });
        }
    }

    pub fn draw_pixel_prefix_mutation(
        &mut self,
        byte_limit: u32,
        stride: u32,
        red_delta: i32,
        green_delta: i32,
    ) {
        if byte_limit > 0 && stride > 0 {
            self.commands.push(DrawCommand::PixelPrefix {
                byte_limit,
                stride,
                red_delta,
                green_delta,
            });
        }
    }

    pub fn draw_erase_triangles(&mut self, vertices: Vec<([f32; 2], GpuColor)>) {
        if !vertices.is_empty() {
            self.commands.push(DrawCommand::EraseTriangles {
                vertices,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_text(
        &mut self,
        text: String,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        font_size: f32,
        line_height: f32,
        color: GpuColor,
    ) {
        if !text.is_empty() && font_size > 0.0 && line_height > 0.0 {
            self.commands.push(DrawCommand::Text {
                text,
                x,
                y,
                width: width.max(1.0),
                height: height.max(line_height).max(1.0),
                font_size,
                line_height,
                color,
            });
        }
    }
}
