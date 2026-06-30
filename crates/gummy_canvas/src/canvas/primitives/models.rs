use crate::*;

impl Canvas {
    pub(crate) fn shaded_faces_impl(&mut self, faces: &Bound<'_, PyAny>) -> PyResult<()> {
        self.performance_counters.python_face_payloads += 1;
        let sequence = faces.downcast::<PyList>()?;
        let mut vertices = Vec::new();
        for item in sequence.iter() {
            let dict = item.downcast::<PyDict>()?;
            if dict
                .get_item("texture")?
                .is_some_and(|value| !value.is_none())
            {
                continue;
            }
            let points = dict
                .get_item("points")?
                .ok_or_else(|| PyValueError::new_err("face payload is missing points."))?
                .extract::<Vec<(f64, f64)>>()?;
            if points.len() < 3 {
                continue;
            }
            let color = dict
                .get_item("color")?
                .ok_or_else(|| PyValueError::new_err("face payload is missing color."))?
                .extract::<(f64, f64, f64, f64)>()?;
            let color = Rgba {
                r: (color.0.clamp(0.0, 1.0) * 255.0).round() as u8,
                g: (color.1.clamp(0.0, 1.0) * 255.0).round() as u8,
                b: (color.2.clamp(0.0, 1.0) * 255.0).round() as u8,
                a: (color.3.clamp(0.0, 1.0) * 255.0).round() as u8,
            };
            let first = scale_point(points[0], self.pixel_density);
            for index in 1..points.len() - 1 {
                push_triangle(
                    &mut vertices,
                    first,
                    scale_point(points[index], self.pixel_density),
                    scale_point(points[index + 1], self.pixel_density),
                    color,
                );
            }
        }
        if vertices.is_empty() {
            return Ok(());
        }
        if self.gpu.is_some() && !self.cpu_compositing_active {
            self.draw_gpu_triangles(vertices, BlendMode::Blend)?;
            return Ok(());
        }
        self.draw_shaded_face_vertices_cpu(&vertices)
    }

    pub(crate) fn draw_model_shaded_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<Vec<f64>>,
    ) -> PyResult<()> {
        if self.gpu.is_some() && !self.cpu_compositing_active && cull_backfaces {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniform = crate::software3d::model_gpu_uniform(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    lights,
                    normal_material,
                    transform.clone(),
                )?;
                self.upload_stale_texture(false)?;
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_model(key, index_count, uniform);
                    self.record_native_model_draw();
                    return Ok(());
                }
            }
        }
        let triangles = crate::software3d::model_handle_shaded_triangles_with_depth(
            model,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
            self.pixel_density,
        )?;
        if triangles.is_empty() {
            return Ok(());
        }
        self.performance_counters.direct_model_draws += 1;
        self.pending_3d_triangles
            .extend(triangles.into_iter().map(|triangle| Pending3dTriangle {
                depth: triangle.depth,
                vertices: triangle.vertices,
            }));
        self.render_dirty = true;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_model_shaded_batch_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transforms: Vec<Vec<f64>>,
    ) -> PyResult<()> {
        if transforms.is_empty() {
            return Ok(());
        }
        if self.gpu.is_some() && !self.cpu_compositing_active && cull_backfaces {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniforms = crate::software3d::model_gpu_uniforms(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    lights,
                    normal_material,
                    transforms.clone(),
                )?;
                self.upload_stale_texture(false)?;
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_model_instances(key, index_count, uniforms);
                    self.record_native_model_batch_draw(transforms.len());
                    return Ok(());
                }
            }
        }
        for transform in transforms {
            self.draw_model_shaded_impl(
                model,
                camera,
                projection,
                viewport_width,
                viewport_height,
                material,
                lights,
                normal_material,
                cull_backfaces,
                Some(transform),
            )?;
        }
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_model_textured_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        image: PyRef<'_, CanvasImage>,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        lights: &Bound<'_, PyAny>,
        normal_material: bool,
        cull_backfaces: bool,
        transform: Option<Vec<f64>>,
    ) -> PyResult<bool> {
        if image.width == 0 || image.height == 0 {
            return Ok(true);
        }
        if self.gpu.is_some() && !self.cpu_compositing_active && cull_backfaces {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniform = crate::software3d::model_gpu_uniform(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    lights,
                    normal_material,
                    transform.clone(),
                )?;
                self.upload_stale_texture(false)?;
                self.ensure_gpu_canvas_image_texture(&image)?;
                let linear_sampling = self.current_style.image_sampling != "nearest";
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_textured_model(key, image.key, index_count, uniform, linear_sampling);
                    self.record_native_model_draw();
                    return Ok(true);
                }
            }
        }
        let triangles = crate::software3d::model_handle_textured_triangles_with_depth(
            model,
            camera,
            projection,
            viewport_width,
            viewport_height,
            material,
            lights,
            normal_material,
            cull_backfaces,
            transform,
            self.pixel_density,
        )?;
        if triangles.is_empty() {
            return Ok(true);
        }
        if self.gpu.is_none() || self.cpu_compositing_active {
            return Ok(false);
        }
        self.upload_stale_texture(false)?;
        self.ensure_gpu_canvas_image_texture(&image)?;
        let linear_sampling = self.current_style.image_sampling != "nearest";
        let blend_mode = self.current_style.blend_mode_kind;
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(false);
        };
        for triangle in triangles {
            let vertices = [
                triangle.vertices[0],
                triangle.vertices[1],
                triangle.vertices[2],
                triangle.vertices[0],
                triangle.vertices[2],
                triangle.vertices[2],
            ];
            gpu.draw_image(image.key, vertices, linear_sampling, blend_mode);
        }
        self.record_native_model_draw();
        Ok(true)
    }

    pub(crate) fn flush_pending_3d_triangles(&mut self) {
        if self.pending_3d_triangles.is_empty() {
            return;
        }
        self.pending_3d_triangles
            .sort_by(|left, right| right.depth.total_cmp(&left.depth));
        let mut vertices = Vec::with_capacity(self.pending_3d_triangles.len() * 3);
        for triangle in self.pending_3d_triangles.drain(..) {
            vertices.extend(triangle.vertices);
        }
        if vertices.is_empty() {
            return;
        }
        if self.gpu.is_some() && !self.cpu_compositing_active {
            let _ = self.draw_gpu_triangles(vertices, BlendMode::Blend);
        } else {
            let _ = self.draw_shaded_face_vertices_cpu(&vertices);
        }
    }

    pub(crate) fn draw_shaded_face_vertices_cpu(
        &mut self,
        vertices: &[([f32; 2], crate::gpu::GpuColor)],
    ) -> PyResult<()> {
        for triangle in vertices.chunks_exact(3) {
            let color = triangle[0].1;
            let style = Style {
                fill: Some(Rgba {
                    r: color.r,
                    g: color.g,
                    b: color.b,
                    a: color.a,
                }),
                stroke: None,
                ..Style::default()
            };
            let points = [
                (triangle[0].0[0] as f64, triangle[0].0[1] as f64),
                (triangle[1].0[0] as f64, triangle[1].0[1] as f64),
                (triangle[2].0[0] as f64, triangle[2].0[1] as f64),
            ];
            self.draw_transformed_polygon(&points, &style, true)?;
        }
        Ok(())
    }

    fn ensure_gpu_canvas_image_texture(&mut self, image: &CanvasImage) -> PyResult<()> {
        let texture_version = self.texture_cache_versions.version(image.key);
        if texture_version == Some(image.version) {
            self.performance_counters.texture_cache_hits += 1;
            return Ok(());
        }
        self.performance_counters.texture_uploads += 1;
        self.evict_texture_cache_if_needed(image.key);
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(());
        };
        gpu.upload_texture(image.key, image.width, image.height, &image.pixels)
            .map_err(|err| {
                PyValueError::new_err(format!("Failed to upload image texture: {err}"))
            })?;
        self.texture_cache_versions.insert(image.key, image.version);
        Ok(())
    }
}

fn scale_point(point: Point, scale: f64) -> Point {
    (point.0 * scale, point.1 * scale)
}
