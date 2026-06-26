use super::super::{PRIMITIVE_BATCH_ELLIPSE, PRIMITIVE_BATCH_RECT, PRIMITIVE_BATCH_TRIANGLE};
use super::helpers::{fill_primitive_batch_cache_key, fill_primitive_batch_instances};
use crate::*;
use std::sync::Arc;

impl Canvas {
    pub(crate) fn batch_fill_primitives_impl(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8)>,
        matrix: Matrix,
    ) -> PyResult<()> {
        if records.is_empty() {
            return Ok(());
        }
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += records.len() as u64;
        if self.gpu.is_some() && !self.cpu_compositing_active {
            let cache_key = fill_primitive_batch_cache_key(
                &records,
                matrix,
                self.pixel_density,
                self.physical_width,
                self.physical_height,
            );
            if self.primitive_batch_cache_key == Some(cache_key) {
                if !self.primitive_batch_cache_instances.is_empty() {
                    self.draw_gpu_retained_primitive_instances(
                        cache_key,
                        self.primitive_batch_cache_instances.clone(),
                        BlendMode::Blend,
                    )?;
                } else {
                    self.draw_gpu_retained_triangles(
                        cache_key,
                        self.primitive_batch_cache_vertices.clone(),
                        BlendMode::Blend,
                    )?;
                }
                return Ok(());
            }
            if let Some(instances) = fill_primitive_batch_instances(
                &records,
                matrix,
                self.pixel_density,
                self.physical_width,
                self.physical_height,
            )? {
                self.primitive_batch_cache_key = Some(cache_key);
                self.primitive_batch_cache_record_count = records.len();
                self.primitive_batch_cache_vertices = Arc::new(Vec::new());
                self.primitive_batch_cache_instances = Arc::new(instances.clone());
                self.draw_gpu_primitive_instances(instances, BlendMode::Blend)?;
                return Ok(());
            }
            let mut vertices = Vec::with_capacity(records.len() * 6);
            for (kind, a, b, c, d, e, f, r, g, blue, alpha) in &records {
                let color = Rgba {
                    r: *r,
                    g: *g,
                    b: *blue,
                    a: *alpha,
                };
                match *kind {
                    PRIMITIVE_BATCH_RECT => {
                        let points = [
                            self.transform_point(matrix, *a, *b),
                            self.transform_point(matrix, *a + *c, *b),
                            self.transform_point(matrix, *a + *c, *b + *d),
                            self.transform_point(matrix, *a, *b + *d),
                        ];
                        push_triangle(&mut vertices, points[0], points[1], points[2], color);
                        push_triangle(&mut vertices, points[0], points[2], points[3], color);
                    }
                    PRIMITIVE_BATCH_TRIANGLE => {
                        push_triangle(
                            &mut vertices,
                            self.transform_point(matrix, *a, *b),
                            self.transform_point(matrix, *c, *d),
                            self.transform_point(matrix, *e, *f),
                            color,
                        );
                    }
                    PRIMITIVE_BATCH_ELLIPSE => {
                        let cx = *a + *c / 2.0;
                        let cy = *b + *d / 2.0;
                        let rx = *c / 2.0;
                        let ry = *d / 2.0;
                        let center = self.transform_point(matrix, cx, cy);
                        for index in 0..64 {
                            let t0 = 2.0 * PI * index as f64 / 64.0;
                            let t1 = 2.0 * PI * (index + 1) as f64 / 64.0;
                            push_triangle(
                                &mut vertices,
                                center,
                                self.transform_point(
                                    matrix,
                                    cx + t0.cos() * rx,
                                    cy + t0.sin() * ry,
                                ),
                                self.transform_point(
                                    matrix,
                                    cx + t1.cos() * rx,
                                    cy + t1.sin() * ry,
                                ),
                                color,
                            );
                        }
                    }
                    _ => {
                        return Err(PyValueError::new_err(format!(
                            "Unknown primitive batch record kind {kind}."
                        )));
                    }
                }
            }
            self.primitive_batch_cache_key = Some(cache_key);
            self.primitive_batch_cache_record_count = records.len();
            self.primitive_batch_cache_vertices = Arc::new(vertices.clone());
            self.primitive_batch_cache_instances = Arc::new(Vec::new());
            self.draw_gpu_triangles(vertices, BlendMode::Blend)?;
            return Ok(());
        }
        let mut style = self.current_style.clone();
        style.stroke = None;
        style.erasing = false;
        style.blend_mode = BLEND_MODE_BLEND.to_string();
        style.blend_mode_kind = BlendMode::Blend;
        for (kind, a, b, c, d, e, f, r, g, blue, alpha) in records {
            style.fill = Some(Rgba {
                r,
                g,
                b: blue,
                a: alpha,
            });
            match kind {
                PRIMITIVE_BATCH_RECT => self.rect_with_style(a, b, c, d, &style, matrix)?,
                PRIMITIVE_BATCH_TRIANGLE => {
                    self.triangle_with_style(a, b, c, d, e, f, &style, matrix)?
                }
                PRIMITIVE_BATCH_ELLIPSE => self.ellipse_with_style(a, b, c, d, &style, matrix)?,
                _ => {
                    return Err(PyValueError::new_err(format!(
                        "Unknown primitive batch record kind {kind}."
                    )));
                }
            }
        }
        Ok(())
    }

    pub(crate) fn replay_fill_primitive_batch_impl(&mut self) -> PyResult<bool> {
        if self.primitive_batch_cache_vertices.is_empty()
            && self.primitive_batch_cache_instances.is_empty()
        {
            return Ok(false);
        }
        if self.gpu.is_none() || self.cpu_compositing_active {
            return Ok(false);
        }
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records +=
            self.primitive_batch_cache_record_count as u64;
        let Some(cache_key) = self.primitive_batch_cache_key else {
            return Ok(false);
        };
        if !self.primitive_batch_cache_instances.is_empty() {
            self.draw_gpu_retained_primitive_instances(
                cache_key,
                self.primitive_batch_cache_instances.clone(),
                BlendMode::Blend,
            )?;
        } else {
            self.draw_gpu_retained_triangles(
                cache_key,
                self.primitive_batch_cache_vertices.clone(),
                BlendMode::Blend,
            )?;
        }
        Ok(true)
    }
}
