use gummy_ecs::{SpatialIndexDescriptor, SpatialIndexRegistry};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::parse::{parse_spatial_algorithm, spatial_algorithm_name};

#[pyclass(name = "EcsSpatialIndexRegistry")]
pub(crate) struct PyEcsSpatialIndexRegistry {
    registry: SpatialIndexRegistry,
}

#[pymethods]
impl PyEcsSpatialIndexRegistry {
    #[new]
    fn new() -> Self {
        Self {
            registry: SpatialIndexRegistry::new(),
        }
    }

    #[pyo3(signature = (target_query, dimensions, algorithm, update_policy, name=None))]
    fn intern(
        &mut self,
        target_query: Vec<String>,
        dimensions: u8,
        algorithm: String,
        update_policy: String,
        name: Option<String>,
    ) -> PyResult<u64> {
        if dimensions != 2 && dimensions != 3 {
            return Err(PyValueError::new_err(
                "ECS spatial index dimensions must be 2 or 3",
            ));
        }
        let descriptor = SpatialIndexDescriptor {
            name,
            target_query,
            dimensions,
            algorithm: parse_spatial_algorithm(&algorithm)?,
            update_policy,
        };
        Ok(self.registry.intern(descriptor))
    }

    fn release(&mut self, id: u64) {
        self.registry.release(id);
    }

    fn mark_stale(&mut self, reason: String) {
        self.registry.mark_stale(reason);
    }

    fn len(&self) -> usize {
        self.registry.len()
    }

    fn get<'py>(&self, py: Python<'py>, id: u64) -> PyResult<Option<Bound<'py, PyDict>>> {
        let Some(slot) = self.registry.get(id) else {
            return Ok(None);
        };
        let dict = PyDict::new_bound(py);
        dict.set_item("name", slot.descriptor.name.clone())?;
        dict.set_item("target_query", slot.descriptor.target_query.clone())?;
        dict.set_item("dimensions", slot.descriptor.dimensions)?;
        dict.set_item(
            "algorithm",
            spatial_algorithm_name(&slot.descriptor.algorithm),
        )?;
        dict.set_item("update_policy", slot.descriptor.update_policy.clone())?;
        dict.set_item("ref_count", slot.ref_count)?;
        let stats = PyDict::new_bound(py);
        stats.set_item("builds", slot.stats.builds)?;
        stats.set_item("queries", slot.stats.queries)?;
        stats.set_item("candidate_rows", slot.stats.candidate_rows)?;
        stats.set_item("exact_rows", slot.stats.exact_rows)?;
        stats.set_item("stale", slot.stats.stale)?;
        stats.set_item("stale_reason", slot.stats.stale_reason.clone())?;
        dict.set_item("stats", stats)?;
        Ok(Some(dict))
    }
}
