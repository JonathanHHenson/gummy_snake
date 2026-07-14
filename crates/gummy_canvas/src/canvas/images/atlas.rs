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

        let mut placements = Vec::with_capacity(images.len());
        for image in images {
            let placement = self
                .gpu
                .as_mut()
                .expect("GPU availability checked before atlas placement")
                .place_persistent_atlas_image(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    image.pixels.as_slice(),
                )
                .map_err(|error| {
                    PyValueError::new_err(format!(
                        "Persistent image-atlas placement failed: {error}"
                    ))
                })?;
            let Some(placement) = placement else {
                self.update_texture_cache_byte_counters();
                return Ok(false);
            };
            if placement.uploaded {
                let uploaded_bytes = (image.width + 2) * (image.height + 2) * 4;
                self.performance_counters.texture_uploads += 1;
                self.performance_counters.texture_upload_bytes += uploaded_bytes as u64;
                self.performance_counters.texture_dirty_uploads += u64::from(image.version > 0);
            } else {
                self.performance_counters.texture_cache_hits += 1;
            }
            placements.push(placement);
        }

        self.update_texture_cache_byte_counters();

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
        }
        .as_float();
        let mut ordered_batches: Vec<(u64, Vec<crate::gpu::ImageVertex>)> = Vec::new();
        for record in records {
            if record.dw <= 0.0 || record.dh <= 0.0 {
                continue;
            }
            let image = &images[record.unique_index];
            let placement = placements[record.unique_index];
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
            let u0 = (placement.x + sx) as f32 / placement.page_width as f32;
            let v0 = (placement.y + sy) as f32 / placement.page_height as f32;
            let u1 = (placement.x + sx + sw) as f32 / placement.page_width as f32;
            let v1 = (placement.y + sy + sh) as f32 / placement.page_height as f32;
            if ordered_batches
                .last()
                .is_none_or(|(texture_key, _)| *texture_key != placement.texture_key)
            {
                ordered_batches.push((placement.texture_key, Vec::new()));
            }
            let vertices = &mut ordered_batches
                .last_mut()
                .expect("ordered atlas batch was just created")
                .1;
            vertices.extend([
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
        if ordered_batches.is_empty() {
            return Ok(false);
        }
        let gpu = self
            .gpu
            .as_mut()
            .expect("GPU availability checked before atlas draws");
        for (texture_key, vertices) in ordered_batches {
            let vertex_count = vertices.len();
            gpu.draw_image_batch(
                texture_key,
                vertices,
                linear_sampling,
                style.blend_mode_kind,
            );
            self.performance_counters.native_draw_commands += 1;
            self.performance_counters.native_image_commands += 1;
            self.performance_counters.native_staged_image_vertices += vertex_count as u64;
        }
        if style.blend_mode_kind != BlendMode::Blend {
            self.performance_counters.gpu_blend_commands += 1;
        }
        self.mark_gpu_output_texture_current();
        Ok(true)
    }
}
