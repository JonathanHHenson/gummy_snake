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

use self::lighting::shade_projected_face;
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
use self::types::{MeshPayload, ObjModelData, Vec3d};

pub(crate) use self::rasterize::rasterize_faces_rgba;

#[pyclass(name = "CanvasModel3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasModel3D {
    model: ObjModelData,
    source: String,
}

#[pyclass(name = "CanvasMesh3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasMesh3D {
    mesh: ObjModelData,
}

fn canvas_model_from_data(model: ObjModelData, source: &str) -> CanvasModel3D {
    CanvasModel3D {
        model,
        source: source.to_owned(),
    }
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
    Ok(CanvasMesh3D {
        mesh: ObjModelData {
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
        },
    })
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
        CanvasMesh3D {
            mesh: self.model.clone(),
        }
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
    Ok(CanvasModel3D {
        model: parsed,
        source: source.to_owned(),
    })
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
