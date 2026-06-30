mod ecs;
mod health;
mod image_ops;
mod models;

use ecs::*;
pub(crate) use health::{canvas_abi_version, gpu_available, health_check, native_window_available};
use image_ops::*;
use models::*;

use crate::*;

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    m.add_function(wrap_pyfunction!(canvas_abi_version, m)?)?;
    m.add_function(wrap_pyfunction!(native_window_available, m)?)?;
    m.add_function(wrap_pyfunction!(gpu_available, m)?)?;
    m.add_function(wrap_pyfunction!(ecs_abi_version, m)?)?;
    m.add_function(wrap_pyfunction!(ecs_health_check, m)?)?;
    m.add_function(wrap_pyfunction!(image_resize_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_crop_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_alpha_composite_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_mask_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(image_filter_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(media_frame_to_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(parse_obj_model, m)?)?;
    m.add_function(wrap_pyfunction!(create_mesh3d_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_model3d_handle, m)?)?;
    m.add_function(wrap_pyfunction!(parse_obj_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_plane_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_box_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_sphere_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_ellipsoid_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_cylinder_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_cone_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(create_torus_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(project_shade_faces, m)?)?;
    m.add_function(wrap_pyfunction!(project_shade_model_handle, m)?)?;
    m.add_function(wrap_pyfunction!(rasterize_faces_rgba, m)?)?;
    m.add("CANVAS_ABI_VERSION", CANVAS_ABI_VERSION)?;
    m.add_class::<Matrix2D>()?;
    m.add_class::<Canvas>()?;
    m.add_class::<CanvasImage>()?;
    m.add_class::<CanvasSound>()?;
    m.add_class::<PyEcsWorld>()?;
    m.add_class::<PyEcsSpatialIndexRegistry>()?;
    m.add_class::<sketch_state::SketchContextState>()?;
    m.add_class::<software3d::CanvasModel3D>()?;
    m.add_class::<software3d::CanvasMesh3D>()?;
    Ok(())
}
