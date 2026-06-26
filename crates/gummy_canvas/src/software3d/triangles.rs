use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;

use crate::software3d::lighting::shade_projected_face;
use crate::software3d::mesh::model_to_mesh_payload;
use crate::software3d::model::CanvasModel3D;
use crate::software3d::payload::{
    parse_camera_payload, parse_light_payloads, parse_material_payload, parse_projection_payload,
};
use crate::software3d::project::{project_mesh_payload_faces, validate_projection_payload};
use crate::software3d::types::Transform2D;
use crate::software3d::{ShadedTriangle, TexturedTriangle};
use crate::Rgba;

#[allow(clippy::too_many_arguments)]
pub(crate) fn model_handle_shaded_triangles_with_depth(
    model: &CanvasModel3D,
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
    transform: Option<Transform2D>,
    pixel_density: f64,
) -> PyResult<Vec<ShadedTriangle>> {
    if viewport_width <= 0.0 || viewport_height <= 0.0 {
        return Err(PyValueError::new_err(
            "viewport dimensions must be positive.",
        ));
    }
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    let mesh = model_to_mesh_payload(&model.model, transform);
    let mut faces = project_mesh_payload_faces(
        &mesh,
        &camera,
        &projection,
        viewport_width,
        viewport_height,
        cull_backfaces,
    )?;
    faces.sort_by(|left, right| right.depth.total_cmp(&left.depth));

    let mut triangles = Vec::new();
    for face in faces {
        if face.points.len() < 3 {
            continue;
        }
        let color = crate::raster::gpu_color(rgba_from_unit_tuple(shade_projected_face(
            &face,
            &camera,
            &material,
            &lights,
            normal_material,
        )?));
        let first = scale_point(face.points[0], pixel_density);
        for index in 1..face.points.len() - 1 {
            triangles.push(ShadedTriangle {
                depth: face.depth,
                vertices: [
                    ([first.0 as f32, first.1 as f32], color),
                    (
                        [
                            (face.points[index].0 * pixel_density) as f32,
                            (face.points[index].1 * pixel_density) as f32,
                        ],
                        color,
                    ),
                    (
                        [
                            (face.points[index + 1].0 * pixel_density) as f32,
                            (face.points[index + 1].1 * pixel_density) as f32,
                        ],
                        color,
                    ),
                ],
            });
        }
    }
    Ok(triangles)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn model_handle_textured_triangles_with_depth(
    model: &CanvasModel3D,
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
    transform: Option<Transform2D>,
    pixel_density: f64,
) -> PyResult<Vec<TexturedTriangle>> {
    if viewport_width <= 0.0 || viewport_height <= 0.0 {
        return Err(PyValueError::new_err(
            "viewport dimensions must be positive.",
        ));
    }
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    let mesh = model_to_mesh_payload(&model.model, transform);
    let mut faces = project_mesh_payload_faces(
        &mesh,
        &camera,
        &projection,
        viewport_width,
        viewport_height,
        cull_backfaces,
    )?;
    faces.sort_by(|left, right| right.depth.total_cmp(&left.depth));

    let mut triangles = Vec::new();
    for face in faces {
        if face.points.len() < 3 {
            continue;
        }
        let Some(texcoords) = face.texcoords.as_ref() else {
            continue;
        };
        if texcoords.len() != face.points.len() {
            continue;
        }
        let color = crate::raster::gpu_color(rgba_from_unit_tuple(shade_projected_face(
            &face,
            &camera,
            &material,
            &lights,
            normal_material,
        )?));
        let first = scale_point(face.points[0], pixel_density);
        let first_uv = texcoord_to_gpu(texcoords[0]);
        for index in 1..face.points.len() - 1 {
            triangles.push(TexturedTriangle {
                vertices: [
                    ([first.0 as f32, first.1 as f32], first_uv, color),
                    (
                        [
                            (face.points[index].0 * pixel_density) as f32,
                            (face.points[index].1 * pixel_density) as f32,
                        ],
                        texcoord_to_gpu(texcoords[index]),
                        color,
                    ),
                    (
                        [
                            (face.points[index + 1].0 * pixel_density) as f32,
                            (face.points[index + 1].1 * pixel_density) as f32,
                        ],
                        texcoord_to_gpu(texcoords[index + 1]),
                        color,
                    ),
                ],
            });
        }
    }
    Ok(triangles)
}

fn rgba_from_unit_tuple(color: (f64, f64, f64, f64)) -> Rgba {
    Rgba {
        r: (color.0.clamp(0.0, 1.0) * 255.0).round() as u8,
        g: (color.1.clamp(0.0, 1.0) * 255.0).round() as u8,
        b: (color.2.clamp(0.0, 1.0) * 255.0).round() as u8,
        a: (color.3.clamp(0.0, 1.0) * 255.0).round() as u8,
    }
}

fn scale_point(point: (f64, f64), scale: f64) -> (f64, f64) {
    (point.0 * scale, point.1 * scale)
}

fn texcoord_to_gpu(texcoord: (f64, f64)) -> [f32; 2] {
    [
        texcoord.0.clamp(0.0, 1.0) as f32,
        (1.0 - texcoord.1.clamp(0.0, 1.0)) as f32,
    ]
}
