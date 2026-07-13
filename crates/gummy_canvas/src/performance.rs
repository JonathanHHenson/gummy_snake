use pyo3::prelude::*;
use pyo3::types::PyDict;

#[derive(Clone, Debug, Default)]
pub(crate) struct PerformanceCounters {
    pub(crate) gpu_draws: u64,
    pub(crate) gpu_blend_commands: u64,
    pub(crate) gpu_region_effect_passes: u64,
    pub(crate) cpu_fallbacks: u64,
    pub(crate) pixel_readbacks: u64,
    pub(crate) pixel_uploads: u64,
    pub(crate) gpu_pixel_readbacks: u64,
    pub(crate) pixel_bytes_created: u64,
    pub(crate) pixel_noop_upload_skips: u64,
    pub(crate) pixel_full_uploads: u64,
    pub(crate) pixel_region_uploads: u64,
    pub(crate) image_cache_hits: u64,
    pub(crate) image_cache_misses: u64,
    pub(crate) image_source_clones_avoided: u64,
    pub(crate) image_source_clone_bytes_avoided: u64,
    pub(crate) image_cache_resident_bytes: u64,
    pub(crate) image_cache_peak_bytes: u64,
    pub(crate) image_cache_evictions: u64,
    pub(crate) image_cache_evicted_bytes: u64,
    pub(crate) texture_cache_hits: u64,
    pub(crate) texture_uploads: u64,
    pub(crate) texture_upload_bytes: u64,
    pub(crate) texture_dirty_uploads: u64,
    pub(crate) texture_resident_bytes: u64,
    pub(crate) texture_peak_bytes: u64,
    pub(crate) texture_cache_evictions: u64,
    pub(crate) texture_destructions: u64,
    pub(crate) image_atlas_resident_bytes: u64,
    pub(crate) image_atlas_peak_bytes: u64,
    pub(crate) image_atlas_evictions: u64,
    pub(crate) image_atlas_destructions: u64,
    pub(crate) text_cache_hits: u64,
    pub(crate) text_cache_misses: u64,
    pub(crate) text_cache_evictions: u64,
    pub(crate) text_measurements: u64,
    pub(crate) bridge_calls: u64,
    pub(crate) frames_presented: u64,
    pub(crate) gpu_frames_rendered: u64,
    pub(crate) event_polls: u64,
    pub(crate) direct_model_draws: u64,
    pub(crate) python_face_payloads: u64,
    pub(crate) direct_shape_finalizations: u64,
    pub(crate) shape_buffer_extractions: u64,
    pub(crate) pixel_payload_copies: u64,
    pub(crate) native_draw_commands: u64,
    pub(crate) native_triangle_commands: u64,
    pub(crate) native_ellipse_commands: u64,
    pub(crate) native_image_commands: u64,
    pub(crate) native_text_commands: u64,
    pub(crate) native_model_commands: u64,
    pub(crate) native_erase_commands: u64,
    pub(crate) native_region_effect_commands: u64,
    pub(crate) native_primitive_instance_commands: u64,
    pub(crate) native_staged_primitive_vertices: u64,
    pub(crate) native_staged_image_vertices: u64,
    pub(crate) native_primitive_records: u64,
    pub(crate) native_primitive_batches: u64,
    pub(crate) packed_primitive_records: u64,
    pub(crate) packed_primitive_bytes: u64,
    pub(crate) native_command_ingest_time_ms: f64,
    pub(crate) gpu_encode_time_ms: f64,
    pub(crate) gpu_present_time_ms: f64,
}

impl PerformanceCounters {
    pub(crate) fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("gpu_draws", self.gpu_draws)?;
        dict.set_item("gpu_blend_commands", self.gpu_blend_commands)?;
        dict.set_item("gpu_region_effect_passes", self.gpu_region_effect_passes)?;
        dict.set_item("cpu_fallbacks", self.cpu_fallbacks)?;
        dict.set_item("pixel_readbacks", self.pixel_readbacks)?;
        dict.set_item("pixel_uploads", self.pixel_uploads)?;
        dict.set_item("gpu_pixel_readbacks", self.gpu_pixel_readbacks)?;
        dict.set_item("pixel_bytes_created", self.pixel_bytes_created)?;
        dict.set_item("pixel_noop_upload_skips", self.pixel_noop_upload_skips)?;
        dict.set_item("pixel_full_uploads", self.pixel_full_uploads)?;
        dict.set_item("pixel_region_uploads", self.pixel_region_uploads)?;
        dict.set_item("image_cache_hits", self.image_cache_hits)?;
        dict.set_item("image_cache_misses", self.image_cache_misses)?;
        dict.set_item(
            "image_source_clones_avoided",
            self.image_source_clones_avoided,
        )?;
        dict.set_item(
            "image_source_clone_bytes_avoided",
            self.image_source_clone_bytes_avoided,
        )?;
        dict.set_item(
            "image_cache_resident_bytes",
            self.image_cache_resident_bytes,
        )?;
        dict.set_item("image_cache_peak_bytes", self.image_cache_peak_bytes)?;
        dict.set_item("image_cache_evictions", self.image_cache_evictions)?;
        dict.set_item("image_cache_evicted_bytes", self.image_cache_evicted_bytes)?;
        dict.set_item("texture_cache_hits", self.texture_cache_hits)?;
        dict.set_item("texture_uploads", self.texture_uploads)?;
        dict.set_item("texture_upload_bytes", self.texture_upload_bytes)?;
        dict.set_item("texture_dirty_uploads", self.texture_dirty_uploads)?;
        dict.set_item("texture_resident_bytes", self.texture_resident_bytes)?;
        dict.set_item("texture_peak_bytes", self.texture_peak_bytes)?;
        dict.set_item("texture_cache_evictions", self.texture_cache_evictions)?;
        dict.set_item("texture_destructions", self.texture_destructions)?;
        dict.set_item(
            "image_atlas_resident_bytes",
            self.image_atlas_resident_bytes,
        )?;
        dict.set_item("image_atlas_peak_bytes", self.image_atlas_peak_bytes)?;
        dict.set_item("image_atlas_evictions", self.image_atlas_evictions)?;
        dict.set_item("image_atlas_destructions", self.image_atlas_destructions)?;
        dict.set_item("text_cache_hits", self.text_cache_hits)?;
        dict.set_item("text_cache_misses", self.text_cache_misses)?;
        dict.set_item("text_cache_evictions", self.text_cache_evictions)?;
        dict.set_item("text_measurements", self.text_measurements)?;
        dict.set_item("bridge_calls", self.bridge_calls)?;
        dict.set_item("frames_presented", self.frames_presented)?;
        dict.set_item("gpu_frames_rendered", self.gpu_frames_rendered)?;
        dict.set_item("event_polls", self.event_polls)?;
        dict.set_item("direct_model_draws", self.direct_model_draws)?;
        dict.set_item("python_face_payloads", self.python_face_payloads)?;
        dict.set_item(
            "direct_shape_finalizations",
            self.direct_shape_finalizations,
        )?;
        dict.set_item("shape_buffer_extractions", self.shape_buffer_extractions)?;
        dict.set_item("pixel_payload_copies", self.pixel_payload_copies)?;
        dict.set_item("native_draw_commands", self.native_draw_commands)?;
        dict.set_item("native_triangle_commands", self.native_triangle_commands)?;
        dict.set_item("native_ellipse_commands", self.native_ellipse_commands)?;
        dict.set_item("native_image_commands", self.native_image_commands)?;
        dict.set_item("native_text_commands", self.native_text_commands)?;
        dict.set_item("native_model_commands", self.native_model_commands)?;
        dict.set_item("native_erase_commands", self.native_erase_commands)?;
        dict.set_item(
            "native_region_effect_commands",
            self.native_region_effect_commands,
        )?;
        dict.set_item(
            "native_primitive_instance_commands",
            self.native_primitive_instance_commands,
        )?;
        dict.set_item(
            "native_staged_primitive_vertices",
            self.native_staged_primitive_vertices,
        )?;
        dict.set_item(
            "native_staged_image_vertices",
            self.native_staged_image_vertices,
        )?;
        dict.set_item("native_primitive_records", self.native_primitive_records)?;
        dict.set_item("native_primitive_batches", self.native_primitive_batches)?;
        dict.set_item("packed_primitive_records", self.packed_primitive_records)?;
        dict.set_item("packed_primitive_bytes", self.packed_primitive_bytes)?;
        dict.set_item(
            "native_command_ingest_time_ms",
            self.native_command_ingest_time_ms,
        )?;
        dict.set_item("gpu_encode_time_ms", self.gpu_encode_time_ms)?;
        dict.set_item("gpu_present_time_ms", self.gpu_present_time_ms)?;
        Ok(dict)
    }
}
