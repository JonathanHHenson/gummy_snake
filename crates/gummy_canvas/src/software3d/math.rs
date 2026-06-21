use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::types::{CameraPayload, Vec3d};

pub(super) fn camera_space_3d(point: Vec3d, camera: &CameraPayload) -> PyResult<Vec3d> {
    let forward = normalize_3d(sub_3d(camera.target, camera.eye))?;
    let right = normalize_3d(cross_3d(forward, camera.up))?;
    let true_up = cross_3d(right, forward);
    let relative = sub_3d(point, camera.eye);
    Ok(Vec3d {
        x: dot_3d(relative, right),
        y: dot_3d(relative, true_up),
        z: dot_3d(relative, forward),
    })
}

pub(super) fn face_center_3d(points: &[Vec3d]) -> Vec3d {
    let scale = 1.0 / points.len() as f64;
    Vec3d {
        x: points.iter().map(|point| point.x).sum::<f64>() * scale,
        y: points.iter().map(|point| point.y).sum::<f64>() * scale,
        z: points.iter().map(|point| point.z).sum::<f64>() * scale,
    }
}

pub(super) fn face_normal_3d(points: &[Vec3d]) -> Option<Vec3d> {
    if points.len() < 3 {
        return None;
    }
    let normal = cross_3d(sub_3d(points[1], points[0]), sub_3d(points[2], points[0]));
    if dot_3d(normal, normal) == 0.0 {
        None
    } else {
        Some(normal)
    }
}

pub(super) fn sub_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.x - b.x,
        y: a.y - b.y,
        z: a.z - b.z,
    }
}

pub(super) fn add_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.x + b.x,
        y: a.y + b.y,
        z: a.z + b.z,
    }
}

pub(super) fn dot_3d(a: Vec3d, b: Vec3d) -> f64 {
    a.x * b.x + a.y * b.y + a.z * b.z
}

pub(super) fn cross_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.y * b.z - a.z * b.y,
        y: a.z * b.x - a.x * b.z,
        z: a.x * b.y - a.y * b.x,
    }
}

pub(super) fn normalize_3d(value: Vec3d) -> PyResult<Vec3d> {
    let length = dot_3d(value, value).sqrt();
    if length == 0.0 {
        return Err(PyValueError::new_err(
            "3D vectors must have non-zero length.",
        ));
    }
    Ok(Vec3d {
        x: value.x / length,
        y: value.y / length,
        z: value.z / length,
    })
}
