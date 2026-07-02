use crate::gpu::types::*;

pub(super) fn aligned_stroke_path_record_offset(record_offset: usize) -> usize {
    record_offset.div_ceil(STROKE_PATH_RECORD_ALIGNMENT) * STROKE_PATH_RECORD_ALIGNMENT
}

impl GpuRenderer {
    pub(super) fn ensure_render_vertex_buffers(&mut self) {
        let mut primitive_vertices = 0usize;
        let mut procedural_instances = 0usize;
        let mut stroke_path_records = 0usize;
        let mut image_vertices = 0usize;
        for command in &self.commands {
            match command {
                DrawCommand::Triangles { vertices, .. } => {
                    primitive_vertices += vertices.len();
                }
                DrawCommand::RetainedTriangles {
                    retained: RetainedTriangleVertices { vertices, .. },
                    ..
                } => {
                    primitive_vertices += vertices.len();
                }
                DrawCommand::PrimitiveInstances { instances, .. } => {
                    procedural_instances += instances.len();
                }
                DrawCommand::RetainedPrimitiveInstances {
                    retained: RetainedPrimitiveInstances { instances, .. },
                    ..
                } => {
                    procedural_instances += instances.len();
                }
                DrawCommand::StrokePath { records, .. } | DrawCommand::FillPath { records, .. } => {
                    stroke_path_records = aligned_stroke_path_record_offset(stroke_path_records);
                    stroke_path_records += records.len();
                }
                DrawCommand::BlendEllipse { .. } => {}
                DrawCommand::PixelPrefix { .. } => {}
                DrawCommand::ErasePrimitiveInstances { instances, .. } => {
                    procedural_instances += instances.len();
                }
                DrawCommand::EraseStrokePath { records, .. }
                | DrawCommand::EraseFillPath { records, .. } => {
                    stroke_path_records = aligned_stroke_path_record_offset(stroke_path_records);
                    stroke_path_records += records.len();
                }
                DrawCommand::Image { .. } => {
                    image_vertices += 6;
                }
                DrawCommand::ImageBatch { vertices, .. } => {
                    image_vertices += vertices.len();
                }
                DrawCommand::Model { .. }
                | DrawCommand::ModelWireframe { .. }
                | DrawCommand::ModelInstances { .. }
                | DrawCommand::TexturedModel { .. } => {}
                DrawCommand::Text { .. } => {}
                DrawCommand::Clear(_) => {}
            }
        }
        self.ensure_primitive_vertex_capacity(primitive_vertices);
        self.ensure_procedural_primitive_capacity(procedural_instances);
        self.ensure_stroke_path_record_capacity(stroke_path_records);
        self.ensure_image_vertex_capacity(image_vertices);
        let model_uniforms = self
            .commands
            .iter()
            .map(|command| match command {
                DrawCommand::Model { .. }
                | DrawCommand::ModelWireframe { .. }
                | DrawCommand::TexturedModel { .. } => 1,
                DrawCommand::ModelInstances { uniforms, .. } => uniforms.len(),
                _ => 0,
            })
            .sum();
        self.ensure_model_uniform_capacity(model_uniforms);
    }

    fn ensure_model_uniform_capacity(&mut self, required: usize) {
        if required == 0 || self.model_uniform_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.model_uniform_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas model uniforms"),
            size: (capacity * std::mem::size_of::<ModelUniform>()) as u64,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        self.model_uniform_bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gummy_canvas model uniform bind group"),
            layout: &self.model_bind_group_layout,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: self.model_uniform_buffer.as_entire_binding(),
            }],
        });
        self.model_uniform_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_primitive_vertex_capacity(&mut self, required: usize) {
        if required == 0 || self.primitive_vertex_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.primitive_vertex_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable primitive vertices"),
            size: (capacity * std::mem::size_of::<Vertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.primitive_vertex_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_procedural_primitive_capacity(&mut self, required: usize) {
        if required == 0 || self.procedural_primitive_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.procedural_primitive_buffer =
            Some(self.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("gummy_canvas reusable procedural primitive instances"),
                size: (capacity * std::mem::size_of::<PrimitiveInstance>()) as u64,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }));
        self.procedural_primitive_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_stroke_path_record_capacity(&mut self, required: usize) {
        if required == 0 || self.stroke_path_record_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.stroke_path_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable stroke path records"),
            size: (capacity * std::mem::size_of::<StrokePathRecord>()) as u64,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.stroke_path_record_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }

    fn ensure_image_vertex_capacity(&mut self, required: usize) {
        if required == 0 || self.image_vertex_capacity >= required {
            return;
        }
        let capacity = required.next_power_of_two();
        self.image_vertex_buffer = Some(self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("gummy_canvas reusable image vertices"),
            size: (capacity * std::mem::size_of::<ImageVertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        }));
        self.image_vertex_capacity = capacity;
        self.vertex_buffer_allocations += 1;
    }
}
