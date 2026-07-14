use crate::gpu::types::*;
use crate::types::BlendMode;
use wgpu::util::DeviceExt;

impl GpuRenderer {
    pub fn begin_frame(&mut self) {
        self.commands.clear();
        self.clip_textures.truncate(1);
        self.current_clip_id = 0;
        self.clip_stack.clear();
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
        record_primitive_instances(
            &mut self.commands,
            instances,
            blend_mode,
            self.current_clip_id,
        );
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

    pub fn draw_stroke_path(&mut self, records: Vec<StrokePathRecord>, blend_mode: BlendMode) {
        if !records.is_empty() {
            self.commands.push(DrawCommand::StrokePath {
                records,
                blend_mode,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_fill_path(&mut self, records: Vec<StrokePathRecord>, blend_mode: BlendMode) {
        if !records.is_empty() {
            self.commands.push(DrawCommand::FillPath {
                records,
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
        let vertex_buffer =
            self.device_context
                .device()
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some("gummy_canvas model vertices"),
                    contents: bytemuck::cast_slice(vertices),
                    usage: wgpu::BufferUsages::VERTEX,
                });
        let index_buffer =
            self.device_context
                .device()
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some("gummy_canvas model indices"),
                    contents: bytemuck::cast_slice(indices),
                    usage: wgpu::BufferUsages::INDEX,
                });
        let wire_indices = model_wire_indices(indices);
        let wire_index_count = u32::try_from(wire_indices.len())
            .map_err(|_| "model wireframe index count exceeds GPU draw limits".to_owned())?;
        let wire_index_buffer =
            self.device_context
                .device()
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some("gummy_canvas model wireframe indices"),
                    contents: bytemuck::cast_slice(&wire_indices),
                    usage: wgpu::BufferUsages::INDEX,
                });
        self.model_meshes.insert(
            key,
            GpuModelMesh {
                _vertex_buffer: vertex_buffer,
                _index_buffer: index_buffer,
                _wire_index_buffer: wire_index_buffer,
                index_count,
                wire_index_count,
            },
        );
        self.vertex_buffer_allocations += 3;
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

    pub fn draw_model_wireframe(&mut self, key: u64, index_count: u32, uniform: ModelUniform) {
        if index_count > 0 {
            self.commands.push(DrawCommand::ModelWireframe {
                key,
                index_count,
                uniform,
            });
        }
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

    pub fn draw_destination_blend_ellipse(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        self.draw_destination_blend(
            DestinationBlendShape::Ellipse,
            cx,
            cy,
            rx,
            ry,
            color,
            blend_mode,
        );
    }

    pub fn draw_destination_blend_rect(
        &mut self,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        self.draw_destination_blend(
            DestinationBlendShape::Rectangle,
            cx,
            cy,
            rx,
            ry,
            color,
            blend_mode,
        );
    }

    #[allow(clippy::too_many_arguments)]
    fn draw_destination_blend(
        &mut self,
        shape: DestinationBlendShape,
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    ) {
        if rx > 0.0 && ry > 0.0 {
            self.commands.push(DrawCommand::DestinationBlend {
                shape,
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

    pub fn draw_pixel_filter(&mut self, mode: u32, value: f32) {
        if mode > 0 {
            self.commands.push(DrawCommand::PixelFilter { mode, value });
        }
    }

    pub fn draw_erase_primitive_instances(&mut self, instances: Vec<PrimitiveInstance>) {
        if !instances.is_empty() {
            self.commands.push(DrawCommand::ErasePrimitiveInstances {
                instances,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_erase_stroke_path(&mut self, records: Vec<StrokePathRecord>) {
        if !records.is_empty() {
            self.commands.push(DrawCommand::EraseStrokePath {
                records,
                clip_id: self.current_clip_id,
            });
        }
    }

    pub fn draw_erase_fill_path(&mut self, records: Vec<StrokePathRecord>) {
        if !records.is_empty() {
            self.commands.push(DrawCommand::EraseFillPath {
                records,
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

fn record_primitive_instances(
    commands: &mut Vec<DrawCommand>,
    mut instances: Vec<PrimitiveInstance>,
    blend_mode: BlendMode,
    current_clip_id: usize,
) {
    if instances.is_empty() {
        return;
    }
    if let Some(DrawCommand::PrimitiveInstances {
        instances: pending,
        blend_mode: pending_blend,
        clip_id,
    }) = commands.last_mut()
    {
        if *pending_blend == blend_mode && *clip_id == current_clip_id {
            pending.append(&mut instances);
            return;
        }
    }
    commands.push(DrawCommand::PrimitiveInstances {
        instances,
        blend_mode,
        clip_id: current_clip_id,
    });
}

fn model_wire_indices(indices: &[u32]) -> Vec<u32> {
    let mut wire_indices = Vec::with_capacity(indices.len() * 2);
    for triangle in indices.chunks_exact(3) {
        wire_indices.extend_from_slice(&[
            triangle[0],
            triangle[1],
            triangle[1],
            triangle[2],
            triangle[2],
            triangle[0],
        ]);
    }
    wire_indices
}

#[cfg(test)]
mod tests {
    use super::*;

    fn instance(x: f32) -> PrimitiveInstance {
        PrimitiveInstance {
            p0: [x, 0.0],
            p1: [0.0; 2],
            p2: [0.0; 2],
            bounds: [0.0; 4],
            color: [1.0; 4],
            params: [0.0; 4],
        }
    }

    #[test]
    fn adjacent_compatible_primitive_instances_share_one_command() {
        let mut commands = Vec::new();
        record_primitive_instances(&mut commands, vec![instance(1.0)], BlendMode::Blend, 0);
        record_primitive_instances(&mut commands, vec![instance(2.0)], BlendMode::Blend, 0);

        assert_eq!(commands.len(), 1);
        let DrawCommand::PrimitiveInstances { instances, .. } = &commands[0] else {
            panic!("expected a primitive instance command");
        };
        assert_eq!(instances.len(), 2);
        assert_eq!(instances[1].p0[0], 2.0);
    }

    #[test]
    fn primitive_instance_coalescing_preserves_order_and_clip_boundaries() {
        let mut commands = Vec::new();
        record_primitive_instances(&mut commands, vec![instance(1.0)], BlendMode::Blend, 0);
        commands.push(DrawCommand::Clear(GpuColor {
            r: 0,
            g: 0,
            b: 0,
            a: 0,
        }));
        record_primitive_instances(&mut commands, vec![instance(2.0)], BlendMode::Blend, 0);
        record_primitive_instances(&mut commands, vec![instance(3.0)], BlendMode::Blend, 1);

        assert_eq!(commands.len(), 4);
    }
}
