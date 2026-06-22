use pyo3::prelude::*;
use pyo3::types::PyDict;

#[derive(Clone, Debug, Default)]
pub(crate) struct PerformanceCounters {
    pub(crate) gpu_draws: u64,
    pub(crate) cpu_fallbacks: u64,
    pub(crate) pixel_readbacks: u64,
    pub(crate) pixel_uploads: u64,
    pub(crate) image_cache_hits: u64,
    pub(crate) image_cache_misses: u64,
    pub(crate) texture_cache_hits: u64,
    pub(crate) texture_uploads: u64,
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
}

impl PerformanceCounters {
    pub(crate) fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("gpu_draws", self.gpu_draws)?;
        dict.set_item("cpu_fallbacks", self.cpu_fallbacks)?;
        dict.set_item("pixel_readbacks", self.pixel_readbacks)?;
        dict.set_item("pixel_uploads", self.pixel_uploads)?;
        dict.set_item("image_cache_hits", self.image_cache_hits)?;
        dict.set_item("image_cache_misses", self.image_cache_misses)?;
        dict.set_item("texture_cache_hits", self.texture_cache_hits)?;
        dict.set_item("texture_uploads", self.texture_uploads)?;
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
        dict.set_item("direct_shape_finalizations", self.direct_shape_finalizations)?;
        dict.set_item("shape_buffer_extractions", self.shape_buffer_extractions)?;
        dict.set_item("pixel_payload_copies", self.pixel_payload_copies)?;
        Ok(dict)
    }
}
