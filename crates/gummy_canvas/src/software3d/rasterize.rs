use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes};

pub(crate) fn rasterize_faces_rgba<'py>(
    _py: Python<'py>,
    _width: usize,
    _height: usize,
    _faces: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    Err(PyValueError::new_err(
        "CPU face rasterization is disabled; render models through the GPU canvas path instead.",
    ))
}
