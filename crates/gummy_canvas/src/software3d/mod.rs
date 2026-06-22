mod lighting;
mod math;
mod obj;
mod payload;
mod primitives;
mod project;
mod rasterize;
mod types;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};
use std::sync::atomic::{AtomicU64, Ordering};

use self::lighting::shade_projected_face;
use self::math::{cross_3d, dot_3d, normalize_3d, sub_3d, triangle_normal};
use self::obj::{
    normalize_obj_model, obj_model_to_dict, parse_obj_text, save_obj_model, save_stl_model,
};
use self::payload::{
    parse_camera_payload, parse_light_payloads, parse_material_payload, parse_mesh_payloads,
    parse_projection_payload,
};
use self::primitives::{
    box_model_data, cone_model_data, cylinder_model_data, ellipsoid_model_data, plane_model_data,
    sphere_model_data, torus_model_data,
};
use self::project::{project_mesh_payload_faces, validate_projection_payload};
use self::types::{
    CameraPayload, LightKindPayload, LightPayload, MaterialPayload, MeshPayload, ObjModelData,
    ProjectionPayload, Vec3d,
};
use crate::Rgba;

pub(crate) use self::rasterize::rasterize_faces_rgba;

static NEXT_MODEL_KEY: AtomicU64 = AtomicU64::new(1);

#[pyclass(name = "CanvasModel3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasModel3D {
    model: ObjModelData,
    source: String,
    gpu_key: u64,
    gpu_vertices: Vec<crate::gpu::ModelVertex>,
    gpu_indices: Vec<u32>,
}

#[pyclass(name = "CanvasMesh3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasMesh3D {
    mesh: ObjModelData,
    #[allow(dead_code)]
    gpu_key: u64,
    #[allow(dead_code)]
    gpu_vertices: Vec<crate::gpu::ModelVertex>,
    #[allow(dead_code)]
    gpu_indices: Vec<u32>,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct ShadedTriangle {
    pub(crate) depth: f64,
    pub(crate) vertices: [([f32; 2], crate::gpu::GpuColor); 3],
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct TexturedTriangle {
    pub(crate) vertices: [([f32; 2], [f32; 2], crate::gpu::GpuColor); 3],
}

fn canvas_model_from_data(model: ObjModelData, source: &str) -> CanvasModel3D {
    let (gpu_vertices, gpu_indices) = pack_model_gpu_triangles(&model);
    CanvasModel3D {
        model,
        source: source.to_owned(),
        gpu_key: NEXT_MODEL_KEY.fetch_add(1, Ordering::Relaxed),
        gpu_vertices,
        gpu_indices,
    }
}

fn canvas_mesh_from_data(mesh: ObjModelData) -> CanvasMesh3D {
    let (gpu_vertices, gpu_indices) = pack_model_gpu_triangles(&mesh);
    CanvasMesh3D {
        mesh,
        gpu_key: NEXT_MODEL_KEY.fetch_add(1, Ordering::Relaxed),
        gpu_vertices,
        gpu_indices,
    }
}

fn pack_model_gpu_triangles(model: &ObjModelData) -> (Vec<crate::gpu::ModelVertex>, Vec<u32>) {
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

#[allow(clippy::too_many_arguments)]
pub(crate) fn model_gpu_uniform(
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
    normal_material: bool,
    transform: Option<Transform2D>,
) -> PyResult<crate::gpu::ModelUniform> {
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    model_gpu_uniform_from_payloads(
        &camera,
        &projection,
        viewport_width,
        viewport_height,
        &material,
        &lights,
        normal_material,
        transform,
    )
}

fn model_gpu_uniform_from_payloads(
    camera: &CameraPayload,
    projection: &ProjectionPayload,
    viewport_width: f64,
    viewport_height: f64,
    material: &MaterialPayload,
    lights: &[LightPayload],
    normal_material: bool,
    transform: Option<Transform2D>,
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

fn transform_to_model_matrix(transform: Option<Transform2D>) -> [[f32; 4]; 4] {
    let (a, b, c, d, e, f) = transform.unwrap_or((1.0, 0.0, 0.0, 1.0, 0.0, 0.0));
    let z_scale = ((a.hypot(b) + c.hypot(d)) / 2.0).max(1e-9);
    [
        [a as f32, b as f32, 0.0, 0.0],
        [c as f32, d as f32, 0.0, 0.0],
        [0.0, 0.0, z_scale as f32, 0.0],
        [e as f32, (-f) as f32, 0.0, 1.0],
    ]
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

type Transform2D = (f64, f64, f64, f64, f64, f64);

fn model_to_mesh_payload(model: &ObjModelData, transform: Option<Transform2D>) -> MeshPayload {
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

fn projected_faces_to_py<'py>(
    py: Python<'py>,
    mut faces: Vec<self::types::ProjectedPayloadFace>,
    camera: &self::types::CameraPayload,
    material: &self::types::MaterialPayload,
    lights: &[self::types::LightPayload],
    normal_material: bool,
) -> PyResult<Bound<'py, PyList>> {
    faces.sort_by(|left, right| right.depth.total_cmp(&left.depth));
    let output = PyList::empty_bound(py);
    for face in faces {
        let color = shade_projected_face(&face, camera, material, lights, normal_material)?;
        let dict = PyDict::new_bound(py);
        dict.set_item("points", face.points)?;
        dict.set_item("depth", face.depth)?;
        dict.set_item("normal", (face.normal.x, face.normal.y, face.normal.z))?;
        dict.set_item("center", (face.center.x, face.center.y, face.center.z))?;
        dict.set_item("texcoords", face.texcoords)?;
        dict.set_item("color", color)?;
        output.append(dict)?;
    }
    Ok(output)
}

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

#[pymethods]
impl CanvasMesh3D {
    fn vertex_count(&self) -> usize {
        self.mesh.vertices.len()
    }

    fn face_count(&self) -> usize {
        self.mesh.faces.len()
    }

    fn to_mesh_payload<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        obj_model_to_dict(py, &self.mesh)
    }
}

#[pymethods]
impl CanvasModel3D {
    #[getter]
    fn source(&self) -> &str {
        &self.source
    }

    fn vertex_count(&self) -> usize {
        self.model.vertices.len()
    }

    fn face_count(&self) -> usize {
        self.model.faces.len()
    }

    fn to_mesh_payload<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        obj_model_to_dict(py, &self.model)
    }

    fn to_mesh_handle(&self) -> CanvasMesh3D {
        canvas_mesh_from_data(self.model.clone())
    }

    fn save_obj(&self, path: &str) -> PyResult<()> {
        save_obj_model(&self.model, path)
    }

    #[pyo3(signature = (path, name="gummy_snake_model"))]
    fn save_stl(&self, path: &str, name: &str) -> PyResult<()> {
        save_stl_model(&self.model, path, name)
    }
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

#[allow(clippy::too_many_arguments)]
pub(crate) fn project_shade_faces<'py>(
    py: Python<'py>,
    meshes: &Bound<'py, PyAny>,
    camera: &Bound<'py, PyAny>,
    projection: &Bound<'py, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'py, PyAny>,
    lights: &Bound<'py, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
) -> PyResult<Bound<'py, PyList>> {
    if viewport_width <= 0.0 || viewport_height <= 0.0 {
        return Err(PyValueError::new_err(
            "viewport dimensions must be positive.",
        ));
    }
    let mesh_payloads = parse_mesh_payloads(meshes)?;
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    let mut faces = Vec::new();
    for mesh in &mesh_payloads {
        faces.extend(project_mesh_payload_faces(
            mesh,
            &camera,
            &projection,
            viewport_width,
            viewport_height,
            cull_backfaces,
        )?);
    }
    projected_faces_to_py(py, faces, &camera, &material, &lights, normal_material)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn project_shade_model_handle<'py>(
    py: Python<'py>,
    model: &CanvasModel3D,
    camera: &Bound<'py, PyAny>,
    projection: &Bound<'py, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'py, PyAny>,
    lights: &Bound<'py, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
    transform: Option<Transform2D>,
) -> PyResult<Bound<'py, PyList>> {
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
    let faces = project_mesh_payload_faces(
        &mesh,
        &camera,
        &projection,
        viewport_width,
        viewport_height,
        cull_backfaces,
    )?;
    projected_faces_to_py(py, faces, &camera, &material, &lights, normal_material)
}
