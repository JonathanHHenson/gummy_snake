use pyo3::prelude::*;
use pyo3::types::PyAny;

use super::input::{
    parse_camera_payload, parse_light_payloads, parse_material_payload, parse_projection_payload,
    parse_transform_payload,
};
use crate::software3d;
use crate::software3d::model::types::{
    CameraPayload, LightPayload, MaterialPayload, ProjectionPayload,
};

#[allow(clippy::too_many_arguments)]
pub(crate) fn model_gpu_uniform(
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
    normal_material: bool,
    transform: Option<Vec<f64>>,
) -> PyResult<crate::gpu::ModelUniform> {
    let inputs = parse_model_uniform_inputs(camera, projection, material, lights)?;
    software3d::model_gpu_uniform_from_payloads(
        &inputs.camera,
        &inputs.projection,
        viewport_width,
        viewport_height,
        &inputs.material,
        &inputs.lights,
        normal_material,
        parse_transform_payload(transform)?,
    )
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn model_gpu_uniforms(
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
    normal_material: bool,
    transforms: Vec<Vec<f64>>,
) -> PyResult<Vec<crate::gpu::ModelUniform>> {
    let inputs = parse_model_uniform_inputs(camera, projection, material, lights)?;
    transforms
        .into_iter()
        .map(|transform| {
            software3d::model_gpu_uniform_from_payloads(
                &inputs.camera,
                &inputs.projection,
                viewport_width,
                viewport_height,
                &inputs.material,
                &inputs.lights,
                normal_material,
                parse_transform_payload(Some(transform))?,
            )
        })
        .collect()
}

struct ModelUniformInputs {
    camera: CameraPayload,
    projection: ProjectionPayload,
    material: MaterialPayload,
    lights: Vec<LightPayload>,
}

fn parse_model_uniform_inputs(
    camera: &Bound<'_, PyAny>,
    projection: &Bound<'_, PyAny>,
    material: &Bound<'_, PyAny>,
    lights: &Bound<'_, PyAny>,
) -> PyResult<ModelUniformInputs> {
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    software3d::validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    Ok(ModelUniformInputs {
        camera,
        projection,
        material,
        lights,
    })
}
