use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::types::Vec3d;

pub(super) fn validate_positive(values: &[(&str, f64)], message: &str) -> PyResult<()> {
    if values.iter().any(|(_, value)| *value <= 0.0) {
        return Err(PyValueError::new_err(message.to_owned()));
    }
    Ok(())
}

pub(super) fn empty_normals(count: usize) -> Vec<Option<Vec3d>> {
    vec![None; count]
}

pub(super) fn some_texcoords(texcoords: Vec<(f64, f64)>) -> Vec<Option<(f64, f64)>> {
    texcoords.into_iter().map(Some).collect()
}
