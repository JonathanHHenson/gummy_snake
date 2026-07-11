use crate::prelude::*;

impl Canvas {
    pub(crate) fn shaded_faces_impl(&mut self, faces: &Bound<'_, PyAny>) -> PyResult<()> {
        self.performance_counters.python_face_payloads += 1;
        let sequence = faces.downcast::<PyList>()?;
        if sequence.is_empty() {
            return Ok(());
        }
        Err(PyValueError::new_err(
            "CPU projected-face payload drawing is disabled; render models through the retained GPU model path instead.",
        ))
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
        Err(PyValueError::new_err(
            "CPU 3D model projection fallback is disabled; model drawing requires the retained GPU model path.",
        ))
    }

    pub(crate) fn draw_model_wireframe_impl(
        &mut self,
        model: &crate::software3d::CanvasModel3D,
        camera: &Bound<'_, PyAny>,
        projection: &Bound<'_, PyAny>,
        viewport_width: f64,
        viewport_height: f64,
        material: &Bound<'_, PyAny>,
        transform: Option<Vec<f64>>,
    ) -> PyResult<()> {
        if self.gpu.is_some() && !self.cpu_compositing_active {
            let (key, vertices, indices) = crate::software3d::model_gpu_buffers(model);
            if !vertices.is_empty() && !indices.is_empty() {
                let uniform = crate::software3d::model_gpu_uniform(
                    camera,
                    projection,
                    viewport_width,
                    viewport_height,
                    material,
                    &PyList::empty_bound(camera.py()),
                    false,
                    transform.clone(),
                )?;
                self.upload_stale_texture(false)?;
                if let Some(gpu) = self.gpu.as_mut() {
                    let index_count = gpu
                        .ensure_model_mesh(key, vertices, indices)
                        .map_err(PyValueError::new_err)?;
                    gpu.draw_model_wireframe(key, index_count, uniform);
                    self.record_native_model_draw();
                    return Ok(());
                }
            }
        }
        Err(PyValueError::new_err(
            "CPU 3D model wireframe fallback is disabled; model strokes require the retained GPU model path.",
        ))
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
        Err(PyValueError::new_err(
            "CPU 3D model batch projection fallback is disabled; model drawing requires the retained GPU model path.",
        ))
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
        Err(PyValueError::new_err(
            "CPU textured-model projection fallback is disabled; textured model drawing requires the retained GPU model path.",
        ))
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
            self.gpu_error = Some(
                "CPU 3D triangle fallback is disabled; pending 3D triangles require GPU rendering."
                    .to_string(),
            );
        }
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
