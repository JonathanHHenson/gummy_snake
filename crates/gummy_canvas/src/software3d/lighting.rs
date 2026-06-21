use pyo3::prelude::*;

use crate::software3d::math::{add_3d, dot_3d, normalize_3d, sub_3d};
use crate::software3d::types::{
    CameraPayload, LightKindPayload, LightPayload, MaterialPayload, ProjectedPayloadFace, Vec3d,
};

pub(super) fn shade_projected_face(
    face: &ProjectedPayloadFace,
    camera: &CameraPayload,
    material: &MaterialPayload,
    lights: &[LightPayload],
    normal_material: bool,
) -> PyResult<(f64, f64, f64, f64)> {
    if normal_material {
        return Ok(clamp_rgba_float((
            (face.normal.x + 1.0) / 2.0,
            (face.normal.y + 1.0) / 2.0,
            (face.normal.z + 1.0) / 2.0,
            material.base_color.3,
        )));
    }
    let (base_r, base_g, base_b, base_a) = material.base_color;
    if lights.is_empty() {
        return Ok(clamp_rgba_float((
            base_r + material.emissive_color.0,
            base_g + material.emissive_color.1,
            base_b + material.emissive_color.2,
            base_a,
        )));
    }
    let mut result = [
        material.emissive_color.0,
        material.emissive_color.1,
        material.emissive_color.2,
    ];
    let view_dir = normalize_3d(sub_3d(camera.eye, face.center))?;
    for light in lights {
        let light_rgb = [light.color.0, light.color.1, light.color.2];
        let intensity = light.intensity.max(0.0);
        if light.kind == LightKindPayload::Ambient {
            for index in 0..3 {
                result[index] += [base_r, base_g, base_b][index] * light_rgb[index] * intensity;
            }
            continue;
        }
        let Some(light_dir) = light_direction_3d(light, face.center)? else {
            continue;
        };
        let diffuse = dot_3d(face.normal, light_dir).max(0.0);
        for index in 0..3 {
            result[index] +=
                [base_r, base_g, base_b][index] * light_rgb[index] * diffuse * intensity;
        }
        let half_vector = normalize_3d(add_3d(light_dir, view_dir))?;
        let specular = dot_3d(face.normal, half_vector)
            .max(0.0)
            .powf(material.shininess.max(1.0));
        for (index, component) in [
            material.specular_color.0,
            material.specular_color.1,
            material.specular_color.2,
        ]
        .iter()
        .enumerate()
        {
            result[index] += component * light_rgb[index] * specular * intensity;
        }
    }
    Ok(clamp_rgba_float((result[0], result[1], result[2], base_a)))
}

fn light_direction_3d(light: &LightPayload, center: Vec3d) -> PyResult<Option<Vec3d>> {
    match light.kind {
        LightKindPayload::Directional => light
            .direction
            .map(|direction| {
                normalize_3d(Vec3d {
                    x: -direction.x,
                    y: -direction.y,
                    z: -direction.z,
                })
            })
            .transpose(),
        LightKindPayload::Point => light
            .position
            .map(|position| normalize_3d(sub_3d(position, center)))
            .transpose(),
        LightKindPayload::Ambient => Ok(None),
    }
}

fn clamp_rgba_float(color: (f64, f64, f64, f64)) -> (f64, f64, f64, f64) {
    let max_rgb = color.0.max(color.1).max(color.2);
    let (r, g, b) = if max_rgb > 1.0 {
        (color.0 / max_rgb, color.1 / max_rgb, color.2 / max_rgb)
    } else {
        (color.0, color.1, color.2)
    };
    (
        r.clamp(0.0, 1.0),
        g.clamp(0.0, 1.0),
        b.clamp(0.0, 1.0),
        color.3.clamp(0.0, 1.0),
    )
}
