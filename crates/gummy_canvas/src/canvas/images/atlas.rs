use super::{BatchCanvasImage, BatchUniqueImage, IMAGE_ATLAS_MAX_UNIQUE_IMAGES};
use crate::prelude::*;

impl Canvas {
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
        let texture_version = self.texture_cache_versions.version(atlas_key);
        if texture_version != Some(atlas_version) {
            let atlas_bytes = atlas_width
                .checked_mul(atlas_height)
                .and_then(|value| value.checked_mul(4))
                .ok_or_else(|| PyValueError::new_err("Image atlas dimensions are too large."))?;
            let mut atlas_pixels = vec![0u8; atlas_bytes];
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
            self.evict_texture_cache_if_needed(atlas_key, atlas_bytes)?;
            self.upload_stale_texture(false)?;
            let replaced = {
                let Some(gpu) = self.gpu.as_mut() else {
                    return Ok(false);
                };
                gpu.upload_texture(atlas_key, atlas_width, atlas_height, &atlas_pixels)
                    .map_err(|err| {
                        PyValueError::new_err(format!(
                            "Failed to upload image atlas texture: {err}"
                        ))
                    })?
            };
            self.record_texture_upload(
                atlas_key,
                atlas_version,
                atlas_bytes,
                true,
                texture_version.is_some(),
                replaced,
            );
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
        let vertex_count = batch_vertices.len();
        gpu.draw_image_batch(
            atlas_key,
            batch_vertices,
            linear_sampling,
            style.blend_mode_kind,
        );
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_image_commands += 1;
        self.performance_counters.native_staged_image_vertices += vertex_count as u64;
        if style.blend_mode_kind != BlendMode::Blend {
            self.performance_counters.gpu_blend_commands += 1;
        }
        self.mark_gpu_output_texture_current();
        Ok(true)
    }
}
