use crate::software3d;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList};

#[pyfunction]
pub(crate) fn parse_obj_model<'py>(
    py: Python<'py>,
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<Bound<'py, PyDict>> {
    software3d::parse_obj_model(py, text, source, normalize)
}

#[pyfunction]
pub(crate) fn create_mesh3d_handle(
    vertices: &Bound<'_, PyAny>,
    faces: &Bound<'_, PyAny>,
    normals: &Bound<'_, PyAny>,
    texcoords: &Bound<'_, PyAny>,
) -> PyResult<software3d::CanvasMesh3D> {
    software3d::create_mesh3d_handle(vertices, faces, normals, texcoords)
}

#[pyfunction]
pub(crate) fn parse_obj_model_handle(
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::parse_obj_model_handle(text, source, normalize)
}

#[pyfunction(signature = (width, height=None))]
pub(crate) fn create_plane_model_handle(
    width: f64,
    height: Option<f64>,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_plane_model_handle(width, height)
}

#[pyfunction(signature = (width, height=None, depth=None))]
pub(crate) fn create_box_model_handle(
    width: f64,
    height: Option<f64>,
    depth: Option<f64>,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_box_model_handle(width, height, depth)
}

#[pyfunction]
pub(crate) fn create_sphere_model_handle(
    radius: f64,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_sphere_model_handle(radius, detail_x, detail_y)
}

#[pyfunction(signature = (radius_x, radius_y=None, radius_z=None, detail_x=24, detail_y=16))]
pub(crate) fn create_ellipsoid_model_handle(
    radius_x: f64,
    radius_y: Option<f64>,
    radius_z: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_ellipsoid_model_handle(radius_x, radius_y, radius_z, detail_x, detail_y)
}

#[pyfunction]
pub(crate) fn create_cylinder_model_handle(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    bottom_cap: bool,
    top_cap: bool,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_cylinder_model_handle(
        radius, height, detail_x, detail_y, bottom_cap, top_cap,
    )
}

#[pyfunction]
pub(crate) fn create_cone_model_handle(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    cap: bool,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_cone_model_handle(radius, height, detail_x, detail_y, cap)
}

#[pyfunction(signature = (radius, tube_radius=None, detail_x=24, detail_y=12))]
pub(crate) fn create_torus_model_handle(
    radius: f64,
    tube_radius: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<software3d::CanvasModel3D> {
    software3d::create_torus_model_handle(radius, tube_radius, detail_x, detail_y)
}

#[pyfunction]
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
    software3d::project_shade_faces(
        py,
        meshes,
        camera,
        projection,
        viewport_width,
        viewport_height,
        material,
        lights,
        normal_material,
        cull_backfaces,
    )
}

#[pyfunction(signature = (model, camera, projection, viewport_width, viewport_height, material, lights, normal_material, cull_backfaces, transform=None))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn project_shade_model_handle<'py>(
    py: Python<'py>,
    model: &software3d::CanvasModel3D,
    camera: &Bound<'py, PyAny>,
    projection: &Bound<'py, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'py, PyAny>,
    lights: &Bound<'py, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
    transform: Option<(f64, f64, f64, f64, f64, f64)>,
) -> PyResult<Bound<'py, PyList>> {
    software3d::project_shade_model_handle(
        py,
        model,
        camera,
        projection,
        viewport_width,
        viewport_height,
        material,
        lights,
        normal_material,
        cull_backfaces,
        transform,
    )
}

#[pyfunction]
pub(crate) fn rasterize_faces_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    faces: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    software3d::rasterize_faces_rgba(py, width, height, faces)
}
