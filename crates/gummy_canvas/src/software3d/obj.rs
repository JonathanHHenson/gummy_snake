use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::software3d::types::{ObjModelData, Vec3d};

pub(super) use crate::software3d::obj_export::{save_obj_model, save_stl_model};
pub(super) use crate::software3d::obj_parse::parse_obj_text;

pub(super) fn normalize_obj_model(mut model: ObjModelData) -> ObjModelData {
    if model.vertices.is_empty() {
        return model;
    }
    let mut min_x = f64::INFINITY;
    let mut min_y = f64::INFINITY;
    let mut min_z = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    let mut max_z = f64::NEG_INFINITY;
    for vertex in &model.vertices {
        min_x = min_x.min(vertex.x);
        min_y = min_y.min(vertex.y);
        min_z = min_z.min(vertex.z);
        max_x = max_x.max(vertex.x);
        max_y = max_y.max(vertex.y);
        max_z = max_z.max(vertex.z);
    }
    let span = (max_x - min_x).max(max_y - min_y).max(max_z - min_z);
    if span <= 0.0 {
        return model;
    }
    let center = Vec3d {
        x: (min_x + max_x) / 2.0,
        y: (min_y + max_y) / 2.0,
        z: (min_z + max_z) / 2.0,
    };
    let scale = 2.0 / span;
    for vertex in &mut model.vertices {
        vertex.x = (vertex.x - center.x) * scale;
        vertex.y = (vertex.y - center.y) * scale;
        vertex.z = (vertex.z - center.z) * scale;
    }
    model
}

pub(super) fn obj_model_to_dict<'py>(
    py: Python<'py>,
    model: &ObjModelData,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item(
        "vertices",
        model
            .vertices
            .iter()
            .map(|vertex| (vertex.x, vertex.y, vertex.z))
            .collect::<Vec<_>>(),
    )?;
    dict.set_item("faces", model.faces.clone())?;
    if model.texcoords.iter().all(Option::is_some) {
        dict.set_item(
            "texcoords",
            model
                .texcoords
                .iter()
                .filter_map(|value| *value)
                .collect::<Vec<_>>(),
        )?;
    } else {
        dict.set_item("texcoords", Vec::<(f64, f64)>::new())?;
    }
    if model.normals.iter().all(Option::is_some) {
        dict.set_item(
            "normals",
            model
                .normals
                .iter()
                .filter_map(|value| *value)
                .map(|normal| (normal.x, normal.y, normal.z))
                .collect::<Vec<_>>(),
        )?;
    } else {
        dict.set_item("normals", Vec::<(f64, f64, f64)>::new())?;
    }
    Ok(dict)
}
