mod gpu;
mod lighting;
pub(crate) mod math;
mod project;
mod rasterize;

pub(crate) use gpu::{
    model_gpu_buffers, model_gpu_uniform_from_payloads, model_matrix_from_transform,
    model_matrix_from_translation_quaternion, pack_model_gpu_triangles,
};
pub(crate) use lighting::shade_projected_face;
pub(crate) use project::{project_mesh_payload_faces, validate_projection_payload};
pub(crate) use rasterize::rasterize_faces_rgba;
