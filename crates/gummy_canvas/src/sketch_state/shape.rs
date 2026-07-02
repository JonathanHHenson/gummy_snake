use super::{CapturedPathSegment, SketchContextState};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyList;

impl SketchContextState {
    pub(super) fn begin_shape_capture_impl(&mut self, kind: Option<String>) -> PyResult<()> {
        if self.shape_active {
            return Err(PyRuntimeError::new_err("begin_shape() cannot be nested."));
        }
        self.shape_active = true;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.shape_path_segments.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = kind;
        Ok(())
    }

    pub(super) fn reset_shape_capture_impl(&mut self) {
        self.shape_active = false;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.shape_path_segments.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = None;
    }

    pub(super) fn add_vertex_impl(&mut self, x: f64, y: f64) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            self.contour_vertices.push((x, y));
        } else {
            if let Some(from) = self.shape_vertices.last().copied() {
                self.shape_path_segments
                    .push(CapturedPathSegment::Line { from, to: (x, y) });
            }
            self.shape_vertices.push((x, y));
        }
        Ok(())
    }

    pub(super) fn extend_vertices_impl(&mut self, vertices: Vec<(f64, f64)>) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            self.contour_vertices.extend(vertices);
        } else {
            for (x, y) in vertices {
                if let Some(from) = self.shape_vertices.last().copied() {
                    self.shape_path_segments
                        .push(CapturedPathSegment::Line { from, to: (x, y) });
                }
                self.shape_vertices.push((x, y));
            }
        }
        Ok(())
    }

    pub(super) fn add_quadratic_vertex_impl(
        &mut self,
        cx: f64,
        cy: f64,
        x: f64,
        y: f64,
    ) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "quadratic_vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            return Err(PyRuntimeError::new_err(
                "quadratic_vertex() is not supported inside begin_contour().",
            ));
        }
        let Some(from) = self.shape_vertices.last().copied() else {
            return Err(PyRuntimeError::new_err(
                "quadratic_vertex() requires an initial vertex().",
            ));
        };
        self.shape_path_segments
            .push(CapturedPathSegment::Quadratic {
                from,
                control: (cx, cy),
                to: (x, y),
            });
        self.shape_vertices.push((x, y));
        Ok(())
    }

    pub(super) fn add_cubic_vertex_impl(
        &mut self,
        x2: f64,
        y2: f64,
        x3: f64,
        y3: f64,
        x4: f64,
        y4: f64,
    ) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "bezier_vertex() must be called between begin_shape() and end_shape().",
            ));
        }
        if self.contour_active {
            return Err(PyRuntimeError::new_err(
                "bezier_vertex() is not supported inside begin_contour().",
            ));
        }
        let Some(from) = self.shape_vertices.last().copied() else {
            return Err(PyRuntimeError::new_err(
                "bezier_vertex() requires an initial vertex().",
            ));
        };
        self.shape_path_segments.push(CapturedPathSegment::Cubic {
            from,
            control1: (x2, y2),
            control2: (x3, y3),
            to: (x4, y4),
        });
        self.shape_vertices.push((x4, y4));
        Ok(())
    }

    pub(super) fn active_vertices_impl<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyList>> {
        let source = if self.contour_active {
            &self.contour_vertices
        } else {
            &self.shape_vertices
        };
        Ok(PyList::new_bound(py, source.iter().copied()))
    }

    pub(super) fn shape_vertices_impl<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        Ok(PyList::new_bound(py, self.shape_vertices.iter().copied()))
    }

    pub(super) fn shape_contours_impl<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let result = PyList::empty_bound(py);
        for contour in &self.shape_contours {
            result.append(PyList::new_bound(py, contour.iter().copied()))?;
        }
        Ok(result)
    }

    pub(super) fn shape_vertex_count_impl(&self) -> usize {
        self.shape_vertices.len()
    }

    pub(super) fn contour_vertex_count_impl(&self) -> usize {
        self.contour_vertices.len()
    }

    pub(super) fn begin_contour_capture_impl(&mut self) -> PyResult<()> {
        if !self.shape_active {
            return Err(PyRuntimeError::new_err(
                "begin_contour() requires begin_shape().",
            ));
        }
        if self.contour_active {
            return Err(PyRuntimeError::new_err("begin_contour() cannot be nested."));
        }
        if self.shape_kind.is_some() {
            return Err(PyRuntimeError::new_err(
                "begin_contour() is supported only for freeform begin_shape() paths.",
            ));
        }
        if self.shape_vertices.len() < 3 {
            return Err(PyRuntimeError::new_err(
                "begin_contour() requires at least three outer shape vertices first.",
            ));
        }
        self.contour_active = true;
        self.contour_vertices.clear();
        Ok(())
    }

    pub(super) fn end_contour_capture_impl(&mut self) -> PyResult<()> {
        if !self.shape_active || !self.contour_active {
            return Err(PyRuntimeError::new_err(
                "end_contour() requires begin_contour().",
            ));
        }
        if self.contour_vertices.len() < 3 {
            return Err(PyRuntimeError::new_err(
                "end_contour() requires at least three vertices.",
            ));
        }
        self.shape_contours.push(self.contour_vertices.clone());
        self.contour_vertices.clear();
        self.contour_active = false;
        Ok(())
    }

    pub(super) fn reset_contour_capture_impl(&mut self) {
        self.contour_vertices.clear();
        self.contour_active = false;
    }

    pub(crate) fn captured_shape_vertices(&self) -> &[(f64, f64)] {
        &self.shape_vertices
    }

    pub(crate) fn captured_shape_contours(&self) -> &[Vec<(f64, f64)>] {
        &self.shape_contours
    }

    pub(crate) fn captured_shape_path_segments(&self) -> &[CapturedPathSegment] {
        &self.shape_path_segments
    }

    pub(crate) fn reset_captured_shape(&mut self) {
        self.shape_active = false;
        self.shape_vertices.clear();
        self.shape_contours.clear();
        self.shape_path_segments.clear();
        self.contour_active = false;
        self.contour_vertices.clear();
        self.shape_kind = None;
    }
}
