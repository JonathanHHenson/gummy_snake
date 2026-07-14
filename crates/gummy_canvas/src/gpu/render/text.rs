use crate::gpu::types::*;

impl GpuRenderer {
    pub(super) fn encode_text_pass(
        &mut self,
        encoder: &mut wgpu::CommandEncoder,
        commands: &[DrawCommand],
    ) {
        if !self.prepare_text_areas(commands) {
            return;
        }
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("gummy_canvas glyphon text pass"),
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &self.texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Load,
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        let _ = self
            .text_renderer
            .render(&self.text_atlas, &self.text_viewport, &mut pass);
        drop(pass);
    }

    fn prepare_text_areas(&mut self, commands: &[DrawCommand]) -> bool {
        self.text_viewport.update(
            self.device_context.queue(),
            glyphon::Resolution {
                width: self.texture_size.width,
                height: self.texture_size.height,
            },
        );
        let mut text_keys = Vec::new();
        let mut areas = Vec::new();
        for command in commands {
            let DrawCommand::Text {
                text,
                x,
                y,
                width,
                height,
                font_size,
                line_height,
                color,
            } = command
            else {
                continue;
            };
            let key = format!("{font_size:.2}|{line_height:.2}|{width:.2}|{height:.2}|{text}");
            if !self.text_buffers.contains_key(&key) {
                let mut buffer = glyphon::Buffer::new(
                    &mut self.text_font_system,
                    glyphon::Metrics::new(*font_size, *line_height),
                );
                buffer.set_size(&mut self.text_font_system, Some(*width), Some(*height));
                buffer.set_text(
                    &mut self.text_font_system,
                    text,
                    &glyphon::Attrs::new().family(glyphon::Family::SansSerif),
                    glyphon::Shaping::Advanced,
                );
                buffer.shape_until_scroll(&mut self.text_font_system, false);
                self.text_buffers.insert(key.clone(), buffer);
            }
            text_keys.push((key, *x, *y, *color));
        }
        for (key, x, y, color) in &text_keys {
            let Some(buffer) = self.text_buffers.get(key) else {
                continue;
            };
            areas.push(glyphon::TextArea {
                buffer,
                left: *x,
                top: *y,
                scale: 1.0,
                bounds: glyphon::TextBounds {
                    left: 0,
                    top: 0,
                    right: self.texture_size.width as i32,
                    bottom: self.texture_size.height as i32,
                },
                default_color: glyphon::Color::rgba(color.r, color.g, color.b, color.a),
                custom_glyphs: &[],
            });
        }
        if areas.is_empty() {
            return false;
        }
        self.text_renderer
            .prepare(
                self.device_context.device(),
                self.device_context.queue(),
                &mut self.text_font_system,
                &mut self.text_atlas,
                &self.text_viewport,
                areas,
                &mut self.text_swash_cache,
            )
            .is_ok()
    }
}
