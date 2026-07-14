use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

use crate::software3d::model::types::{
    CameraPayload, LightKindPayload, LightPayload, MaterialPayload, ProjectionPayload, Transform3D,
    Vec3d,
};

pub(crate) fn parse_camera_payload(camera: &Bound<'_, PyAny>) -> PyResult<CameraPayload> {
    let dict = camera.downcast::<PyDict>()?;
    Ok(CameraPayload {
        eye: parse_vec3_payload(
            &dict
                .get_item("eye")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing eye."))?,
        )?,
        target: parse_vec3_payload(
            &dict
                .get_item("target")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing target."))?,
        )?,
        up: parse_vec3_payload(
            &dict
                .get_item("up")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing up."))?,
        )?,
    })
}

pub(crate) fn parse_projection_payload(
    projection: &Bound<'_, PyAny>,
) -> PyResult<ProjectionPayload> {
    let dict = projection.downcast::<PyDict>()?;
    let kind: String = dict
        .get_item("kind")?
        .ok_or_else(|| PyValueError::new_err("projection payload is missing kind."))?
        .extract()?;
    match kind.as_str() {
        "perspective" => Ok(ProjectionPayload::Perspective {
            fov_y: dict
                .get_item("fov_y")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing fov_y."))?
                .extract()?,
            aspect: dict
                .get_item("aspect")?
                .map(|value| value.extract::<Option<f64>>())
                .transpose()?
                .flatten(),
            near: dict
                .get_item("near")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing near."))?
                .extract()?,
            far: dict
                .get_item("far")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing far."))?
                .extract()?,
        }),
        "orthographic" => Ok(ProjectionPayload::Orthographic {
            width: dict
                .get_item("width")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing width."))?
                .extract()?,
            height: dict
                .get_item("height")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing height."))?
                .extract()?,
            near: dict
                .get_item("near")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing near."))?
                .extract()?,
            far: dict
                .get_item("far")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing far."))?
                .extract()?,
        }),
        _ => Err(PyValueError::new_err("unknown projection payload kind.")),
    }
}

pub(crate) fn parse_material_payload(material: &Bound<'_, PyAny>) -> PyResult<MaterialPayload> {
    let dict = material.downcast::<PyDict>()?;
    Ok(MaterialPayload {
        base_color: dict
            .get_item("base_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing base_color."))?
            .extract()?,
        emissive_color: dict
            .get_item("emissive_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing emissive_color."))?
            .extract()?,
        specular_color: dict
            .get_item("specular_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing specular_color."))?
            .extract()?,
        shininess: dict
            .get_item("shininess")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing shininess."))?
            .extract()?,
    })
}

pub(crate) fn parse_light_payloads(lights: &Bound<'_, PyAny>) -> PyResult<Vec<LightPayload>> {
    let sequence = lights.downcast::<PyList>()?;
    let mut parsed = Vec::with_capacity(sequence.len());
    for item in sequence.iter() {
        let dict = item.downcast::<PyDict>()?;
        let kind_raw: String = dict
            .get_item("kind")?
            .ok_or_else(|| PyValueError::new_err("light payload is missing kind."))?
            .extract()?;
        let kind = match kind_raw.as_str() {
            "ambient" => LightKindPayload::Ambient,
            "directional" => LightKindPayload::Directional,
            "point" => LightKindPayload::Point,
            _ => return Err(PyValueError::new_err("unknown light payload kind.")),
        };
        let position = dict
            .get_item("position")?
            .filter(|value| !value.is_none())
            .map(|value| parse_vec3_payload(&value))
            .transpose()?;
        let direction = dict
            .get_item("direction")?
            .filter(|value| !value.is_none())
            .map(|value| parse_vec3_payload(&value))
            .transpose()?;
        parsed.push(LightPayload {
            kind,
            color: dict
                .get_item("color")?
                .ok_or_else(|| PyValueError::new_err("light payload is missing color."))?
                .extract()?,
            intensity: dict
                .get_item("intensity")?
                .ok_or_else(|| PyValueError::new_err("light payload is missing intensity."))?
                .extract()?,
            position,
            direction,
        });
    }
    Ok(parsed)
}

pub(crate) fn parse_transform_payload(
    transform: Option<Vec<f64>>,
) -> PyResult<Option<Transform3D>> {
    let Some(values) = transform else {
        return Ok(None);
    };
    match values.len() {
        16 => Ok(Some([
            [values[0], values[1], values[2], values[3]],
            [values[4], values[5], values[6], values[7]],
            [values[8], values[9], values[10], values[11]],
            [values[12], values[13], values[14], values[15]],
        ])),
        length => Err(PyValueError::new_err(format!(
            "model transform payload must contain 16 matrix values, got {length}"
        ))),
    }
}

fn parse_vec3_payload(value: &Bound<'_, PyAny>) -> PyResult<Vec3d> {
    let (x, y, z): (f64, f64, f64) = value.extract()?;
    Ok(Vec3d { x, y, z })
}
