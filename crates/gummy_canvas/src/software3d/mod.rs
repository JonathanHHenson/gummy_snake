pub(crate) mod model;
mod obj;
mod primitive;
mod render;

pub(crate) use self::model::{
    canvas_mesh_from_data, canvas_model_from_meshes, create_box_model_handle,
    create_cone_model_handle, create_cylinder_model_handle, create_ellipsoid_model_handle,
    create_plane_model_handle, create_sphere_model_handle, create_torus_model_handle,
    model_to_mesh_payload, parse_obj_model_handle, CanvasMesh3D, CanvasModel3D,
};
pub(crate) use self::obj::{normalize_obj_model, parse_obj_text};
pub(crate) use self::render::{
    model_gpu_buffers, model_gpu_uniform_from_payloads, model_matrix_from_transform,
    model_matrix_from_translation_quaternion, project_mesh_payload_faces, rasterize_faces_rgba,
    shade_projected_face, validate_projection_payload,
};

// Canvas model draws retain these internal paths while Python payload parsing lives at the
// PyO3 boundary in `bindings::models`.
pub(crate) use crate::bindings::models::{
    model_gpu_translation_quaternion_uniforms, model_gpu_uniform, model_gpu_uniforms,
};
