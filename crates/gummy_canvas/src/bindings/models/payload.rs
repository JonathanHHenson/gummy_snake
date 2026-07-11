use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};

use crate::software3d;
use crate::software3d::model::types::{ObjModelData, Vec3d};

pub(crate) fn create_mesh3d_handle(
    vertices: &Bound<'_, PyAny>,
    faces: &Bound<'_, PyAny>,
    normals: &Bound<'_, PyAny>,
    texcoords: &Bound<'_, PyAny>,
) -> PyResult<software3d::CanvasMesh3D> {
    let vertices = vertices
        .extract::<Vec<(f64, f64, f64)>>()?
        .into_iter()
        .map(|(x, y, z)| Vec3d { x, y, z })
        .collect::<Vec<_>>();
    let vertex_count = vertices.len();
    let faces = faces.extract::<Vec<Vec<usize>>>()?;
    let normals = normals
        .extract::<Vec<(f64, f64, f64)>>()?
        .into_iter()
        .map(|(x, y, z)| Some(Vec3d { x, y, z }))
        .collect::<Vec<_>>();
    let texcoords = texcoords
        .extract::<Vec<(f64, f64)>>()?
        .into_iter()
        .map(Some)
        .collect::<Vec<_>>();
    Ok(software3d::canvas_mesh_from_data(ObjModelData {
        vertices,
        faces,
        normals: if normals.len() == vertex_count {
            normals
        } else {
            Vec::new()
        },
        texcoords: if texcoords.len() == vertex_count {
            texcoords
        } else {
            Vec::new()
        },
    }))
}

pub(crate) fn model_to_payload_dict<'py>(
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
