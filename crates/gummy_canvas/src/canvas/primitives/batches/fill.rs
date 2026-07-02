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
        let ingest_start = std::time::Instant::now();
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
                self.performance_counters.native_command_ingest_time_ms +=
                    ingest_start.elapsed().as_secs_f64() * 1000.0;
                return Ok(());
            }
            let instances = fill_primitive_batch_instances(
                &records,
                matrix,
                self.pixel_density,
                self.physical_width,
                self.physical_height,
            )?
            .expect("fill primitive batching always uses procedural GPU instances");
            self.primitive_batch_cache_key = Some(cache_key);
            self.primitive_batch_cache_record_count = records.len();
            self.primitive_batch_cache_vertices = Arc::new(Vec::new());
            self.primitive_batch_cache_instances = Arc::new(instances.clone());
            self.draw_gpu_primitive_instances(instances, BlendMode::Blend)?;
            self.performance_counters.native_command_ingest_time_ms +=
                ingest_start.elapsed().as_secs_f64() * 1000.0;
            return Ok(());
        }
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        self.prepare_cpu_composite()
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
        let ingest_start = std::time::Instant::now();
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
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        Ok(true)
    }
}
