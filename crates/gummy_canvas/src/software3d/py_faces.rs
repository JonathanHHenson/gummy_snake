use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

use crate::software3d::lighting::shade_projected_face;
use crate::software3d::mesh::model_to_mesh_payload;
use crate::software3d::model::CanvasModel3D;
use crate::software3d::payload::{
    parse_camera_payload, parse_light_payloads, parse_material_payload, parse_mesh_payloads,
    parse_projection_payload,
};
use crate::software3d::project::{project_mesh_payload_faces, validate_projection_payload};
use crate::software3d::types::{
    CameraPayload, LightPayload, MaterialPayload, ProjectedPayloadFace, Transform2D,
};

fn projected_faces_to_py<'py>(
    py: Python<'py>,
    mut faces: Vec<ProjectedPayloadFace>,
    camera: &CameraPayload,
    material: &MaterialPayload,
    lights: &[LightPayload],
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
