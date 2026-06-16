use pyo3::prelude::*;

#[pyfunction]
fn health_check() -> &'static str {
    "rust-canvas"
}

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_check_reports_canvas_backend() {
        assert_eq!(health_check(), "rust-canvas");
    }
}
