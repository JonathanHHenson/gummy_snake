use pyo3::prelude::*;
use pyo3::types::PyAny;

use crate::software3d::model::{canvas_mesh_from_data, CanvasMesh3D};
use crate::software3d::types::{MeshPayload, ObjModelData, Transform2D, Vec3d};

pub(crate) fn create_mesh3d_handle(
    vertices: &Bound<'_, PyAny>,
    faces: &Bound<'_, PyAny>,
    normals: &Bound<'_, PyAny>,
    texcoords: &Bound<'_, PyAny>,
) -> PyResult<CanvasMesh3D> {
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
    Ok(canvas_mesh_from_data(ObjModelData {
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

pub(super) fn model_to_mesh_payload(
    model: &ObjModelData,
    transform: Option<Transform2D>,
) -> MeshPayload {
    let vertices = match transform {
        Some((a, b, c, d, e, f)) => {
            let z_scale = (a.hypot(b) + c.hypot(d)) / 2.0;
            model
                .vertices
                .iter()
                .map(|vertex| Vec3d {
                    x: a * vertex.x + c * vertex.y + e,
                    y: b * vertex.x + d * vertex.y - f,
                    z: vertex.z * z_scale,
                })
                .collect()
        }
        None => model.vertices.clone(),
    };
    let texcoords = if model.texcoords.len() == model.vertices.len() {
        model
            .texcoords
            .iter()
            .copied()
            .collect::<Option<Vec<_>>>()
            .unwrap_or_default()
    } else {
        Vec::new()
    };
    MeshPayload {
        vertices,
        faces: model.faces.clone(),
        texcoords,
    }
}
