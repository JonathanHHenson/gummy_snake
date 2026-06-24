use crate::*;

mod helpers;

struct BatchCanvasImage {
    unique_index: usize,
    dx: f64,
    dy: f64,
    dw: f64,
    dh: f64,
    source: Option<(i64, i64, i64, i64)>,
}

struct BatchUniqueImage {
    key: u64,
    version: u64,
    width: usize,
    height: usize,
    pixels: Vec<u8>,
}

const MOTION_SPRITE_RECORD_SIZE: usize = 16;

impl Canvas {
    pub(crate) fn draw_image_impl(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_image_pixels(
            &image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_image_current_impl(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        self.draw_image_pixels_with_style(
            &image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    pub(crate) fn draw_cached_image_impl(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let needs_upload = self
            .image_cache
            .get(&image_key)
            .map(|cached| {
                cached.version != image_version
                    || cached.width != image_width
                    || cached.height != image_height
            })
            .unwrap_or(true);
        if needs_upload {
            self.performance_counters.image_cache_misses += 1;
            let pixels = image_pixels.ok_or_else(|| {
                PyValueError::new_err(
                    "Image pixels are required the first time an image/version is drawn.",
                )
            })?;
            validate_rgba_buffer(pixels.len(), image_width, image_height)?;
            self.evict_image_cache_if_needed(image_key);
            self.image_cache.insert(
                image_key,
                CachedImage {
                    version: image_version,
                    width: image_width,
                    height: image_height,
                    pixels,
                },
            );
        } else {
            self.performance_counters.image_cache_hits += 1;
        }
        if let Some(cached) = self.image_cache.get(&image_key).cloned() {
            if self.try_draw_gpu_image(image_key, &cached, dx, dy, dw, dh, style, matrix, source)? {
                return Ok(());
            }
        }
        let cached = self
            .image_cache
            .get(&image_key)
            .ok_or_else(|| PyValueError::new_err("Cached image is not available."))?
            .clone();
        self.draw_image_pixels(
            &cached.pixels,
            cached.width,
            cached.height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_cached_image_current_impl(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        let needs_upload = self
            .image_cache
            .get(&image_key)
            .map(|cached| {
                cached.version != image_version
                    || cached.width != image_width
                    || cached.height != image_height
            })
            .unwrap_or(true);
        if needs_upload {
            self.performance_counters.image_cache_misses += 1;
            let pixels = image_pixels.ok_or_else(|| {
                PyValueError::new_err(
                    "Image pixels are required the first time an image/version is drawn.",
                )
            })?;
            validate_rgba_buffer(pixels.len(), image_width, image_height)?;
            self.evict_image_cache_if_needed(image_key);
            self.image_cache.insert(
                image_key,
                CachedImage {
                    version: image_version,
                    width: image_width,
                    height: image_height,
                    pixels,
                },
            );
        } else {
            self.performance_counters.image_cache_hits += 1;
        }
        if let Some(cached) = self.image_cache.get(&image_key).cloned() {
            if self.try_draw_gpu_image_parts(
                image_key,
                cached.version,
                cached.width,
                cached.height,
                &cached.pixels,
                dx,
                dy,
                dw,
                dh,
                &style,
                matrix,
                source,
            )? {
                return Ok(());
            }
            self.draw_image_pixels_with_style(
                &cached.pixels,
                cached.width,
                cached.height,
                dx,
                dy,
                dw,
                dh,
                &style,
                matrix,
                source,
            )
        } else {
            Err(PyValueError::new_err("Cached image is not available."))
        }
    }

    pub(crate) fn draw_canvas_image_impl(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let needs_cache = self
            .image_cache
            .get(&image.key)
            .map(|cached| {
                cached.version != image.version
                    || cached.width != image.width
                    || cached.height != image.height
            })
            .unwrap_or(true);
        if needs_cache {
            self.evict_image_cache_if_needed(image.key);
            self.image_cache.insert(
                image.key,
                CachedImage {
                    version: image.version,
                    width: image.width,
                    height: image.height,
                    pixels: image.pixels.clone(),
                },
            );
        }
        if self.try_draw_gpu_image_parts_for_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels(
            &image.pixels,
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_canvas_image_current_impl(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        let needs_cache = self
            .image_cache
            .get(&image.key)
            .map(|cached| {
                cached.version != image.version
                    || cached.width != image.width
                    || cached.height != image.height
            })
            .unwrap_or(true);
        if needs_cache {
            self.evict_image_cache_if_needed(image.key);
            self.image_cache.insert(
                image.key,
                CachedImage {
                    version: image.version,
                    width: image.width,
                    height: image.height,
                    pixels: image.pixels.clone(),
                },
            );
        }
        if self.try_draw_gpu_image_parts(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels_with_style(
            &image.pixels,
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    pub(crate) fn batch_canvas_images_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        let sequence = records.downcast::<PyList>()?;
        let mut unique_images = Vec::<BatchUniqueImage>::new();
        let mut unique_indices = HashMap::<(u64, u64), usize>::new();
        let mut parsed_records = Vec::<BatchCanvasImage>::with_capacity(sequence.len());
        for item in sequence.iter() {
            let record = item.downcast::<PyTuple>()?;
            if record.len() != 6 {
                return Err(PyValueError::new_err(
                    "Image batch records must contain image, dx, dy, dw, dh, and source.",
                ));
            }
            let image = record.get_item(0)?.extract::<PyRef<'_, CanvasImage>>()?;
            let dx = record.get_item(1)?.extract::<f64>()?;
            let dy = record.get_item(2)?.extract::<f64>()?;
            let dw = record.get_item(3)?.extract::<f64>()?;
            let dh = record.get_item(4)?.extract::<f64>()?;
            let source = record
                .get_item(5)?
                .extract::<Option<(i64, i64, i64, i64)>>()?;
            let unique_key = (image.key, image.version);
            let unique_index = if let Some(index) = unique_indices.get(&unique_key) {
                *index
            } else {
                let index = unique_images.len();
                unique_images.push(BatchUniqueImage {
                    key: image.key,
                    version: image.version,
                    width: image.width,
                    height: image.height,
                    pixels: image.pixels.clone(),
                });
                unique_indices.insert(unique_key, index);
                index
            };
            parsed_records.push(BatchCanvasImage {
                unique_index,
                dx,
                dy,
                dw,
                dh,
                source,
            });
        }
        if self.try_draw_gpu_image_atlas_batch(&unique_images, &parsed_records, &style, matrix)? {
            return Ok(());
        }
        for record in parsed_records {
            let image = &unique_images[record.unique_index];
            let needs_cache = self
                .image_cache
                .get(&image.key)
                .map(|cached| {
                    cached.version != image.version
                        || cached.width != image.width
                        || cached.height != image.height
                })
                .unwrap_or(true);
            if needs_cache {
                self.evict_image_cache_if_needed(image.key);
                self.image_cache.insert(
                    image.key,
                    CachedImage {
                        version: image.version,
                        width: image.width,
                        height: image.height,
                        pixels: image.pixels.clone(),
                    },
                );
            }
            if self.try_draw_gpu_image_parts(
                image.key,
                image.version,
                image.width,
                image.height,
                &image.pixels,
                record.dx,
                record.dy,
                record.dw,
                record.dh,
                &style,
                matrix,
                record.source,
            )? {
                continue;
            }
            self.draw_image_pixels_with_style(
                &image.pixels,
                image.width,
                image.height,
                record.dx,
                record.dy,
                record.dw,
                record.dh,
                &style,
                matrix,
                record.source,
            )?;
        }
        Ok(())
    }

    pub(crate) fn batch_canvas_image_motion_terms_impl(
        &mut self,
        records: &[u8],
        images: Vec<PyRef<'_, CanvasImage>>,
        frame: u64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        if records.len() % MOTION_SPRITE_RECORD_SIZE != 0 {
            return Err(PyValueError::new_err(
                "Compact sprite records must be 16-byte little-endian records.",
            ));
        }
        let style = self.cached_style(style)?;
        let unique_images = images
            .iter()
            .map(|image| BatchUniqueImage {
                key: image.key,
                version: image.version,
                width: image.width,
                height: image.height,
                pixels: image.pixels.clone(),
            })
            .collect::<Vec<_>>();
        let mut parsed_records = Vec::with_capacity(records.len() / MOTION_SPRITE_RECORD_SIZE);
        for record in records.chunks_exact(MOTION_SPRITE_RECORD_SIZE) {
            let image_index =
                u32::from_le_bytes([record[0], record[1], record[2], record[3]]) as usize;
            if image_index >= unique_images.len() {
                return Err(PyValueError::new_err(
                    "Compact sprite record references an out-of-range image index.",
                ));
            }
            let base_x = f32::from_le_bytes([record[4], record[5], record[6], record[7]]) as f64;
            let y = f32::from_le_bytes([record[8], record[9], record[10], record[11]]) as f64;
            let size = f32::from_le_bytes([record[12], record[13], record[14], record[15]]) as f64;
            if size <= 0.0 {
                continue;
            }
            let x = 10.0 + (base_x + frame as f64).rem_euclid(700.0) - size / 2.0;
            parsed_records.push(BatchCanvasImage {
                unique_index: image_index,
                dx: x,
                dy: y - size / 2.0,
                dw: size,
                dh: size,
                source: None,
            });
        }
        if parsed_records.is_empty() {
            return Ok(());
        }
        if self.try_draw_gpu_image_atlas_batch(&unique_images, &parsed_records, &style, matrix)? {
            return Ok(());
        }
        for record in parsed_records {
            let image = &unique_images[record.unique_index];
            self.draw_image_pixels_with_style(
                &image.pixels,
                image.width,
                image.height,
                record.dx,
                record.dy,
                record.dw,
                record.dh,
                &style,
                matrix,
                None,
            )?;
        }
        Ok(())
    }

    fn try_draw_gpu_image_atlas_batch(
        &mut self,
        images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<bool> {
        if images.is_empty()
            || records.is_empty()
            || images.len() > 64
            || !self.can_queue_gpu_primitives(style)
            || self.gpu.is_none()
        {
            return Ok(false);
        }
        let atlas_width = images.iter().map(|image| image.width).sum::<usize>();
        let atlas_height = images.iter().map(|image| image.height).max().unwrap_or(0);
        if atlas_width == 0 || atlas_height == 0 {
            return Ok(false);
        }
        let mut atlas_key = 0xA71A_5000_0000_0000u64;
        let mut atlas_version = 0xA71A_0F00_0000_0000u64;
        for image in images {
            atlas_key = atlas_key
                .wrapping_mul(1_099_511_628_211)
                .wrapping_add(image.key);
            atlas_version = atlas_version
                .wrapping_mul(1_099_511_628_211)
                .wrapping_add(image.version)
                .wrapping_add((image.width as u64) << 32)
                .wrapping_add(image.height as u64);
        }
        let mut atlas_x_offsets = Vec::with_capacity(images.len());
        let mut next_x = 0usize;
        for image in images {
            atlas_x_offsets.push(next_x);
            next_x += image.width;
        }
        if self.texture_cache_versions.get(&atlas_key).copied() != Some(atlas_version) {
            self.performance_counters.texture_uploads += 1;
            let mut atlas_pixels = vec![0u8; atlas_width * atlas_height * 4];
            for (image, x_offset) in images.iter().zip(atlas_x_offsets.iter().copied()) {
                for y in 0..image.height {
                    let src_start = y * image.width * 4;
                    let src_end = src_start + image.width * 4;
                    let dst_start = (y * atlas_width + x_offset) * 4;
                    let dst_end = dst_start + image.width * 4;
                    atlas_pixels[dst_start..dst_end]
                        .copy_from_slice(&image.pixels[src_start..src_end]);
                }
            }
            self.evict_texture_cache_if_needed(atlas_key);
            self.upload_stale_texture(false)?;
            let Some(gpu) = self.gpu.as_mut() else {
                return Ok(false);
            };
            gpu.upload_texture(atlas_key, atlas_width, atlas_height, &atlas_pixels)
                .map_err(|err| {
                    PyValueError::new_err(format!("Failed to upload image atlas texture: {err}"))
                })?;
            self.texture_cache_versions.insert(atlas_key, atlas_version);
        } else {
            self.performance_counters.texture_cache_hits += records.len() as u64;
            self.upload_stale_texture(false)?;
        }
        let linear_sampling = style.image_sampling != "nearest";
        let tint = style.image_tint.unwrap_or(Rgba {
            r: 255,
            g: 255,
            b: 255,
            a: 255,
        });
        let tint = crate::gpu::GpuColor {
            r: tint.r,
            g: tint.g,
            b: tint.b,
            a: tint.a,
        };
        let mut batch_vertices = Vec::with_capacity(records.len() * 6);
        for record in records {
            if record.dw <= 0.0 || record.dh <= 0.0 {
                continue;
            }
            let image = &images[record.unique_index];
            let source = record
                .source
                .unwrap_or((0, 0, image.width as i64, image.height as i64));
            let Some((sx, sy, sw, sh)) = clipped_source_rect(source, image.width, image.height)
            else {
                continue;
            };
            let image_to_canvas = image_to_canvas_matrix(
                matrix,
                record.dx,
                record.dy,
                record.dw,
                record.dh,
                sw,
                sh,
                self.pixel_density,
            );
            if matrix_determinant(image_to_canvas).abs() <= f64::EPSILON {
                continue;
            }
            let corners = [
                matrix_transform_point(image_to_canvas, 0.0, 0.0),
                matrix_transform_point(image_to_canvas, sw as f64, 0.0),
                matrix_transform_point(image_to_canvas, sw as f64, sh as f64),
                matrix_transform_point(image_to_canvas, 0.0, sh as f64),
            ];
            let atlas_x = atlas_x_offsets[record.unique_index];
            let u0 = (atlas_x + sx) as f32 / atlas_width as f32;
            let v0 = sy as f32 / atlas_height as f32;
            let u1 = (atlas_x + sx + sw) as f32 / atlas_width as f32;
            let v1 = (sy + sh) as f32 / atlas_height as f32;
            let tint = tint.as_float();
            batch_vertices.extend([
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[0]),
                    uv: [u0, v0],
                    tint,
                },
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[1]),
                    uv: [u1, v0],
                    tint,
                },
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[2]),
                    uv: [u1, v1],
                    tint,
                },
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[0]),
                    uv: [u0, v0],
                    tint,
                },
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[2]),
                    uv: [u1, v1],
                    tint,
                },
                crate::gpu::ImageVertex {
                    position: point_to_f32(corners[3]),
                    uv: [u0, v1],
                    tint,
                },
            ]);
            self.performance_counters.gpu_draws += 1;
        }
        if batch_vertices.is_empty() {
            return Ok(false);
        }
        let Some(gpu) = self.gpu.as_mut() else {
            return Ok(false);
        };
        gpu.draw_image_batch(
            atlas_key,
            batch_vertices,
            linear_sampling,
            style.blend_mode_kind,
        );
        self.render_dirty = true;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
        self.texture_stale = false;
        Ok(true)
    }
}
