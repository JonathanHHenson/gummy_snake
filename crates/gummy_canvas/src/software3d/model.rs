use std::sync::atomic::{AtomicU64, Ordering};

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::software3d::gpu::pack_model_gpu_triangles;
use crate::software3d::obj::{obj_model_to_dict, save_obj_model, save_stl_model};
use crate::software3d::types::ObjModelData;

static NEXT_MODEL_KEY: AtomicU64 = AtomicU64::new(1);

#[pyclass(name = "CanvasModel3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasModel3D {
    pub(super) model: ObjModelData,
    source: String,
    pub(super) gpu_key: u64,
    pub(super) gpu_vertices: Vec<crate::gpu::ModelVertex>,
    pub(super) gpu_indices: Vec<u32>,
}

#[pyclass(name = "CanvasMesh3D", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasMesh3D {
    pub(super) mesh: ObjModelData,
}

pub(super) fn canvas_model_from_data(model: ObjModelData, source: &str) -> CanvasModel3D {
    let (gpu_vertices, gpu_indices) = pack_model_gpu_triangles(&model);
    CanvasModel3D {
        model,
        source: source.to_owned(),
        gpu_key: NEXT_MODEL_KEY.fetch_add(1, Ordering::Relaxed),
        gpu_vertices,
        gpu_indices,
    }
}

pub(crate) fn canvas_model_from_meshes(meshes: &[CanvasMesh3D], source: &str) -> CanvasModel3D {
    if meshes.len() == 1 {
        return canvas_model_from_data(meshes[0].mesh.clone(), source);
    }

    let vertex_count = meshes.iter().map(|mesh| mesh.mesh.vertices.len()).sum();
    let face_count = meshes.iter().map(|mesh| mesh.mesh.faces.len()).sum();
    let mut vertices = Vec::with_capacity(vertex_count);
    let mut normals = Vec::with_capacity(vertex_count);
    let mut texcoords = Vec::with_capacity(vertex_count);
    let mut faces = Vec::with_capacity(face_count);
    let mut vertex_offset = 0usize;

    for mesh in meshes {
        let mesh_data = &mesh.mesh;
        vertices.extend(mesh_data.vertices.iter().copied());
        if mesh_data.normals.len() == mesh_data.vertices.len() {
            normals.extend(mesh_data.normals.iter().copied());
        } else {
            normals.extend(std::iter::repeat(None).take(mesh_data.vertices.len()));
        }
        if mesh_data.texcoords.len() == mesh_data.vertices.len() {
            texcoords.extend(mesh_data.texcoords.iter().copied());
        } else {
            texcoords.extend(std::iter::repeat(None).take(mesh_data.vertices.len()));
        }
        faces.extend(
            mesh_data
                .faces
                .iter()
                .map(|face| face.iter().map(|index| index + vertex_offset).collect()),
        );
        vertex_offset += mesh_data.vertices.len();
    }

    canvas_model_from_data(
        ObjModelData {
            vertices,
            texcoords,
            normals,
            faces,
        },
        source,
    )
}

pub(super) fn canvas_mesh_from_data(mesh: ObjModelData) -> CanvasMesh3D {
    CanvasMesh3D { mesh }
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
