mod gpu;
mod lighting;
mod math;
mod mesh;
mod model;
mod model_factory;
mod obj;
mod obj_export;
mod obj_parse;
mod payload;
mod primitive_lathe;
mod primitive_spherical;
mod primitive_utils;
mod primitives;
mod project;
mod py_faces;
mod rasterize;
mod triangles;
mod types;

pub(crate) use self::gpu::{model_gpu_buffers, model_gpu_uniform, model_gpu_uniforms};
pub(crate) use self::mesh::create_mesh3d_handle;
pub(crate) use self::model::{canvas_model_from_meshes, CanvasMesh3D, CanvasModel3D};
pub(crate) use self::model_factory::{
    create_box_model_handle, create_cone_model_handle, create_cylinder_model_handle,
    create_ellipsoid_model_handle, create_plane_model_handle, create_sphere_model_handle,
    create_torus_model_handle, parse_obj_model, parse_obj_model_handle,
};
pub(crate) use self::py_faces::{project_shade_faces, project_shade_model_handle};
pub(crate) use self::rasterize::rasterize_faces_rgba;
pub(crate) use self::triangles::{
    model_handle_shaded_triangles_with_depth, model_handle_textured_triangles_with_depth,
};

#[derive(Clone, Copy, Debug)]
pub(crate) struct ShadedTriangle {
    pub(crate) depth: f64,
    pub(crate) vertices: [([f32; 2], crate::gpu::GpuColor); 3],
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct TexturedTriangle {
    pub(crate) vertices: [([f32; 2], [f32; 2], crate::gpu::GpuColor); 3],
}
