use pyo3::prelude::*;
use pyo3::types::PyAny;

use crate::software3d::model::{canvas_mesh_from_data, CanvasMesh3D};
use crate::software3d::types::{MeshPayload, ObjModelData, Transform3D, Vec3d};

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
    transform: Option<Transform3D>,
) -> MeshPayload {
    let vertices = match transform {
        Some(matrix) => model
            .vertices
            .iter()
            .map(|vertex| transform_vertex(matrix, *vertex))
            .collect(),
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

fn transform_vertex(matrix: Transform3D, vertex: Vec3d) -> Vec3d {
    let x =
        matrix[0][0] * vertex.x + matrix[1][0] * vertex.y + matrix[2][0] * vertex.z + matrix[3][0];
    let y =
        matrix[0][1] * vertex.x + matrix[1][1] * vertex.y + matrix[2][1] * vertex.z + matrix[3][1];
    let z =
        matrix[0][2] * vertex.x + matrix[1][2] * vertex.y + matrix[2][2] * vertex.z + matrix[3][2];
    let w =
        matrix[0][3] * vertex.x + matrix[1][3] * vertex.y + matrix[2][3] * vertex.z + matrix[3][3];
    if w.abs() > 1.0e-12 && (w - 1.0).abs() > 1.0e-12 {
        Vec3d {
            x: x / w,
            y: y / w,
            z: z / w,
        }
    } else {
        Vec3d { x, y, z }
    }
}
