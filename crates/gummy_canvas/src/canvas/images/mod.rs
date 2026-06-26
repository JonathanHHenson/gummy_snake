use crate::*;

mod batch;
mod helpers;

pub(crate) use batch::{
    BatchCanvasImage, BatchUniqueImage, ImageBatchBuilder, IMAGE_ATLAS_MAX_UNIQUE_IMAGES,
};

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
        let cached = self.ensure_cached_image_for_draw(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
        )?;
        let style = self.cached_style(style)?;
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
        let cached = self.ensure_cached_image_for_draw(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
        )?;
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
    }

    fn ensure_cached_image_for_draw(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
    ) -> PyResult<CachedImage> {
        if self
            .image_cache
            .needs_update(image_key, image_version, image_width, image_height)
        {
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
        self.image_cache
            .get(image_key)
            .cloned()
            .ok_or_else(|| PyValueError::new_err("Cached image is not available."))
    }

    fn cache_canvas_image_payload(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_width: usize,
        image_height: usize,
        image_pixels: &[u8],
    ) {
        if self
            .image_cache
            .needs_update(image_key, image_version, image_width, image_height)
        {
            self.evict_image_cache_if_needed(image_key);
            self.image_cache.insert(
                image_key,
                CachedImage {
                    version: image_version,
                    width: image_width,
                    height: image_height,
                    pixels: image_pixels.to_vec(),
                },
            );
        }
    }

    pub(crate) fn draw_image_batch_records(
        &mut self,
        unique_images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        style: &Style,
        cache_images: bool,
        try_individual_gpu: bool,
    ) -> PyResult<()> {
        for record in records {
            let image = &unique_images[record.unique_index];
            if cache_images {
                self.cache_canvas_image_payload(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    &image.pixels,
                );
            }
            if try_individual_gpu
                && self.try_draw_gpu_image_parts(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    &image.pixels,
                    record.dx,
                    record.dy,
                    record.dw,
                    record.dh,
                    style,
                    record.matrix,
                    record.source,
                )?
            {
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
                style,
                record.matrix,
                record.source,
            )?;
        }
        Ok(())
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
        self.cache_canvas_image_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
        );
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
        self.cache_canvas_image_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
        );
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
        let batch = ImageBatchBuilder::parse_canvas_records(records, matrix)?;
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        self.draw_image_batch_records(&unique_images, &records, &style, true, true)
    }

    pub(crate) fn batch_canvas_images_transformed_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
        style: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        let batch = ImageBatchBuilder::parse_transformed_canvas_records(records)?;
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        self.draw_image_batch_records(&unique_images, &records, &style, false, true)
    }

    pub(crate) fn batch_canvas_image_motion_terms_impl(
        &mut self,
        records: &[u8],
        images: Vec<PyRef<'_, CanvasImage>>,
        frame: u64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        let batch = ImageBatchBuilder::parse_motion_records(records, &images, frame, matrix)?;
        if batch.is_empty() {
            return Ok(());
        }
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        self.draw_image_batch_records(&unique_images, &records, &style, false, false)
    }

    pub(crate) fn try_draw_gpu_image_atlas_batch(
        &mut self,
        images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        style: &Style,
    ) -> PyResult<bool> {
        if images.is_empty()
            || records.is_empty()
            || images.len() > IMAGE_ATLAS_MAX_UNIQUE_IMAGES
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
        if self.texture_cache_versions.version(atlas_key) != Some(atlas_version) {
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
                record.matrix,
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
        self.mark_gpu_output_texture_current();
        Ok(true)
    }
}
