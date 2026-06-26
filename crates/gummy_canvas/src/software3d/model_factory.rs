use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::software3d::model::{canvas_model_from_data, CanvasModel3D};
use crate::software3d::obj::{normalize_obj_model, obj_model_to_dict, parse_obj_text};
use crate::software3d::primitives::{
    box_model_data, cone_model_data, cylinder_model_data, ellipsoid_model_data, plane_model_data,
    sphere_model_data, torus_model_data,
};

pub(crate) fn create_plane_model_handle(
    width: f64,
    height: Option<f64>,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        plane_model_data(width, height)?,
        "primitive:plane",
    ))
}

pub(crate) fn create_box_model_handle(
    width: f64,
    height: Option<f64>,
    depth: Option<f64>,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        box_model_data(width, height, depth)?,
        "primitive:box",
    ))
}

pub(crate) fn create_sphere_model_handle(
    radius: f64,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        sphere_model_data(radius, detail_x, detail_y)?,
        "primitive:sphere",
    ))
}

pub(crate) fn create_ellipsoid_model_handle(
    radius_x: f64,
    radius_y: Option<f64>,
    radius_z: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        ellipsoid_model_data(radius_x, radius_y, radius_z, detail_x, detail_y)?,
        "primitive:ellipsoid",
    ))
}

pub(crate) fn create_cylinder_model_handle(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    bottom_cap: bool,
    top_cap: bool,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        cylinder_model_data(radius, height, detail_x, detail_y, bottom_cap, top_cap)?,
        "primitive:cylinder",
    ))
}

pub(crate) fn create_cone_model_handle(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    cap: bool,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        cone_model_data(radius, height, detail_x, detail_y, cap)?,
        "primitive:cone",
    ))
}

pub(crate) fn create_torus_model_handle(
    radius: f64,
    tube_radius: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<CanvasModel3D> {
    Ok(canvas_model_from_data(
        torus_model_data(radius, tube_radius, detail_x, detail_y)?,
        "primitive:torus",
    ))
}

pub(crate) fn parse_obj_model<'py>(
    py: Python<'py>,
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let parsed = parse_obj_text(text, source)?;
    let parsed = if normalize {
        normalize_obj_model(parsed)
    } else {
        parsed
    };
    obj_model_to_dict(py, &parsed)
}

pub(crate) fn parse_obj_model_handle(
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<CanvasModel3D> {
    let parsed = parse_obj_text(text, source)?;
    let parsed = if normalize {
        normalize_obj_model(parsed)
    } else {
        parsed
    };
    Ok(canvas_model_from_data(parsed, source))
}
