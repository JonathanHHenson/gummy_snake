use pyo3::prelude::*;

use super::math::{cross_3d, dot_3d, normalize_3d, sub_3d, triangle_normal};
use crate::software3d::model::types::{
    CameraPayload, LightKindPayload, LightPayload, MaterialPayload, ObjModelData,
    ProjectionPayload, Transform3D,
};
use crate::software3d::CanvasModel3D;

pub(crate) fn pack_model_gpu_triangles(
    model: &ObjModelData,
) -> (Vec<crate::gpu::ModelVertex>, Vec<u32>) {
    let triangle_count = model
        .faces
        .iter()
        .map(|face| face.len().saturating_sub(2))
        .sum::<usize>();
    let mut vertices = Vec::with_capacity(triangle_count * 3);
    let mut indices = Vec::with_capacity(triangle_count * 3);
    for face in &model.faces {
        if face.len() < 3 {
            continue;
        }
        let Some(first) = model.vertices.get(face[0]).copied() else {
            continue;
        };
        for index in 1..face.len() - 1 {
            let Some(second) = model.vertices.get(face[index]).copied() else {
                continue;
            };
            let Some(third) = model.vertices.get(face[index + 1]).copied() else {
                continue;
            };
            let normal = triangle_normal(first, second, third);
            for vertex_index in [face[0], face[index], face[index + 1]] {
                let Some(position) = model.vertices.get(vertex_index).copied() else {
                    continue;
                };
                let normal = model
                    .normals
                    .get(vertex_index)
                    .and_then(|normal| *normal)
                    .unwrap_or(normal);
                let uv = model
                    .texcoords
                    .get(vertex_index)
                    .and_then(|texcoord| *texcoord)
                    .unwrap_or((0.0, 0.0));
                vertices.push(crate::gpu::ModelVertex {
                    position: [position.x as f32, position.y as f32, position.z as f32],
                    normal: [normal.x as f32, normal.y as f32, normal.z as f32],
                    uv: [uv.0 as f32, (1.0 - uv.1) as f32],
                });
                indices.push((vertices.len() - 1) as u32);
            }
        }
    }
    (vertices, indices)
}

pub(crate) fn model_gpu_buffers(
    model: &CanvasModel3D,
) -> (u64, &[crate::gpu::ModelVertex], &[u32]) {
    (model.gpu_key, &model.gpu_vertices, &model.gpu_indices)
}

pub(crate) fn model_gpu_uniform_from_payloads(
    camera: &CameraPayload,
    projection: &ProjectionPayload,
    viewport_width: f64,
    viewport_height: f64,
    material: &MaterialPayload,
    lights: &[LightPayload],
    normal_material: bool,
    transform: Option<Transform3D>,
) -> PyResult<crate::gpu::ModelUniform> {
    let model = transform_to_model_matrix(transform);
    let view = view_matrix(camera)?;
    let projection = projection_matrix(projection, viewport_width, viewport_height);
    let view_projection = multiply_mat4(projection, view);
    let mut ambient_color = [0.0, 0.0, 0.0, 1.0];
    let mut directional_color = [0.0, 0.0, 0.0, 1.0];
    let mut directional_direction = [0.0, 0.0, -1.0, 0.0];
    let mut point_color = [0.0, 0.0, 0.0, 1.0];
    let mut point_position = [0.0, 0.0, 0.0, 1.0];
    let mut flags = [0.0, 0.0, if normal_material { 1.0 } else { 0.0 }, 0.0];
    if lights.is_empty() {
        ambient_color = [1.0, 1.0, 1.0, 1.0];
    }
    for light in lights {
        let color = [
            (light.color.0 * light.intensity).max(0.0) as f32,
            (light.color.1 * light.intensity).max(0.0) as f32,
            (light.color.2 * light.intensity).max(0.0) as f32,
            light.color.3 as f32,
        ];
        match light.kind {
            LightKindPayload::Ambient => {
                ambient_color[0] += color[0];
                ambient_color[1] += color[1];
                ambient_color[2] += color[2];
            }
            LightKindPayload::Directional if flags[0] == 0.0 => {
                if let Some(direction) = light.direction {
                    directional_direction = [
                        direction.x as f32,
                        direction.y as f32,
                        direction.z as f32,
                        0.0,
                    ];
                    directional_color = color;
                    flags[0] = 1.0;
                }
            }
            LightKindPayload::Point if flags[1] == 0.0 => {
                if let Some(position) = light.position {
                    point_position = [position.x as f32, position.y as f32, position.z as f32, 1.0];
                    point_color = color;
                    flags[1] = 1.0;
                }
            }
            _ => {}
        }
    }
    Ok(crate::gpu::ModelUniform {
        model,
        view_projection,
        base_color: color_tuple_to_vec4(material.base_color),
        emissive_color: color_tuple_to_vec4(material.emissive_color),
        specular_shininess: [
            material.specular_color.0 as f32,
            material.specular_color.1 as f32,
            material.specular_color.2 as f32,
            material.shininess as f32,
        ],
        ambient_color,
        directional_color,
        directional_direction,
        point_color,
        point_position,
        flags,
    })
}

fn color_tuple_to_vec4(color: (f64, f64, f64, f64)) -> [f32; 4] {
    [
        color.0 as f32,
        color.1 as f32,
        color.2 as f32,
        color.3 as f32,
    ]
}

fn transform_to_model_matrix(transform: Option<Transform3D>) -> [[f32; 4]; 4] {
    transform
        .unwrap_or([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        .map(|column| column.map(|value| value as f32))
}

fn view_matrix(camera: &CameraPayload) -> PyResult<[[f32; 4]; 4]> {
    let forward = normalize_3d(sub_3d(camera.target, camera.eye))?;
    let right = normalize_3d(cross_3d(forward, camera.up))?;
    let up = cross_3d(right, forward);
    Ok([
        [right.x as f32, up.x as f32, forward.x as f32, 0.0],
        [right.y as f32, up.y as f32, forward.y as f32, 0.0],
        [right.z as f32, up.z as f32, forward.z as f32, 0.0],
        [
            -dot_3d(camera.eye, right) as f32,
            -dot_3d(camera.eye, up) as f32,
            -dot_3d(camera.eye, forward) as f32,
            1.0,
        ],
    ])
}

fn projection_matrix(
    projection: &ProjectionPayload,
    viewport_width: f64,
    viewport_height: f64,
) -> [[f32; 4]; 4] {
    match projection {
        ProjectionPayload::Perspective {
            fov_y,
            aspect,
            near,
            far,
        } => {
            let aspect = aspect.unwrap_or(viewport_width / viewport_height);
            let f = 1.0 / (fov_y.to_radians() * 0.5).tan();
            let range = far - near;
            [
                [(f / aspect) as f32, 0.0, 0.0, 0.0],
                [0.0, f as f32, 0.0, 0.0],
                [0.0, 0.0, (far / range) as f32, 1.0],
                [0.0, 0.0, (-(far * near) / range) as f32, 0.0],
            ]
        }
        ProjectionPayload::Orthographic {
            width,
            height,
            near,
            far,
        } => [
            [(2.0 / width) as f32, 0.0, 0.0, 0.0],
            [0.0, (2.0 / height) as f32, 0.0, 0.0],
            [0.0, 0.0, (1.0 / (far - near)) as f32, 0.0],
            [0.0, 0.0, (-near / (far - near)) as f32, 1.0],
        ],
    }
}

fn multiply_mat4(left: [[f32; 4]; 4], right: [[f32; 4]; 4]) -> [[f32; 4]; 4] {
    let mut output = [[0.0; 4]; 4];
    for column in 0..4 {
        for row in 0..4 {
            output[column][row] = left[0][row] * right[column][0]
                + left[1][row] * right[column][1]
                + left[2][row] * right[column][2]
                + left[3][row] * right[column][3];
        }
    }
    output
}
