use super::types::{MeshPayload, ObjModelData, Transform3D, Vec3d};

use super::CanvasMesh3D;

pub(crate) fn canvas_mesh_from_data(model: ObjModelData) -> CanvasMesh3D {
    CanvasMesh3D { mesh: model }
}

pub(crate) fn model_to_mesh_payload(
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
