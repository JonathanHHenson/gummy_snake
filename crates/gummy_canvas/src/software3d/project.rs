use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::math::{
    camera_space_3d, dot_3d, face_center_3d, face_normal_3d, normalize_3d, sub_3d,
};
use crate::software3d::types::{
    CameraPayload, MeshPayload, ProjectedPayloadFace, ProjectionPayload, Vec3d,
};

pub(super) fn validate_projection_payload(projection: &ProjectionPayload) -> PyResult<()> {
    let (near, far) = match projection {
        ProjectionPayload::Perspective {
            fov_y,
            aspect,
            near,
            far,
        } => {
            if *fov_y <= 0.0 || *fov_y >= 180.0 {
                return Err(PyValueError::new_err(
                    "perspective fov_y must be between 0 and 180 degrees.",
                ));
            }
            if aspect.is_some_and(|value| value <= 0.0) {
                return Err(PyValueError::new_err(
                    "perspective aspect must be positive when provided.",
                ));
            }
            (*near, *far)
        }
        ProjectionPayload::Orthographic {
            width,
            height,
            near,
            far,
        } => {
            if *width <= 0.0 || *height <= 0.0 {
                return Err(PyValueError::new_err(
                    "orthographic width and height must be positive.",
                ));
            }
            (*near, *far)
        }
    };
    if near <= 0.0 {
        return Err(PyValueError::new_err(
            "projection near plane must be positive.",
        ));
    }
    if far <= near {
        return Err(PyValueError::new_err(
            "projection far plane must be greater than the near plane.",
        ));
    }
    Ok(())
}

pub(super) fn project_mesh_payload_faces(
    mesh: &MeshPayload,
    camera: &CameraPayload,
    projection: &ProjectionPayload,
    viewport_width: f64,
    viewport_height: f64,
    cull_backfaces: bool,
) -> PyResult<Vec<ProjectedPayloadFace>> {
    let mut projected = Vec::new();
    let has_texcoords = mesh.texcoords.len() == mesh.vertices.len();
    for indices in &mesh.faces {
        if indices.len() < 3 {
            continue;
        }
        let mut world_points = Vec::with_capacity(indices.len());
        for index in indices {
            let vertex = mesh
                .vertices
                .get(*index)
                .ok_or_else(|| PyValueError::new_err("mesh face index is out of range."))?;
            world_points.push(*vertex);
        }
        let Some(normal) = face_normal_3d(&world_points) else {
            continue;
        };
        let center = face_center_3d(&world_points);
        if cull_backfaces && dot_3d(normal, sub_3d(camera.eye, center)) <= 0.0 {
            continue;
        }
        let camera_points: Vec<Vec3d> = world_points
            .iter()
            .map(|point| camera_space_3d(*point, camera))
            .collect::<PyResult<_>>()?;
        if camera_points
            .iter()
            .any(|point| !visible_3d(*point, projection))
        {
            continue;
        }
        let mut screen_points = Vec::with_capacity(camera_points.len());
        let mut visible = true;
        for point in &camera_points {
            if let Some(screen) =
                project_camera_point_3d(*point, projection, viewport_width, viewport_height)
            {
                screen_points.push(screen);
            } else {
                visible = false;
                break;
            }
        }
        if !visible {
            continue;
        }
        let texcoords = if has_texcoords {
            Some(indices.iter().map(|index| mesh.texcoords[*index]).collect())
        } else {
            None
        };
        projected.push(ProjectedPayloadFace {
            points: screen_points,
            depth: camera_points.iter().map(|point| point.z).sum::<f64>()
                / camera_points.len() as f64,
            normal: normalize_3d(normal)?,
            center,
            texcoords,
        });
    }
    Ok(projected)
}

fn visible_3d(point: Vec3d, projection: &ProjectionPayload) -> bool {
    let (near, far) = match projection {
        ProjectionPayload::Perspective { near, far, .. } => (*near, *far),
        ProjectionPayload::Orthographic { near, far, .. } => (*near, *far),
    };
    near <= point.z && point.z <= far
}

fn project_camera_point_3d(
    point: Vec3d,
    projection: &ProjectionPayload,
    viewport_width: f64,
    viewport_height: f64,
) -> Option<(f64, f64)> {
    match projection {
        ProjectionPayload::Perspective { fov_y, aspect, .. } => {
            let aspect = aspect.unwrap_or(viewport_width / viewport_height);
            let half_fov = fov_y.to_radians() / 2.0;
            let scale_y = half_fov.tan() * point.z;
            if scale_y == 0.0 {
                return None;
            }
            let scale_x = scale_y * aspect;
            if scale_x == 0.0 {
                return None;
            }
            Some(ndc_to_screen_3d(
                point.x / scale_x,
                point.y / scale_y,
                viewport_width,
                viewport_height,
            ))
        }
        ProjectionPayload::Orthographic { width, height, .. } => Some(ndc_to_screen_3d(
            point.x / (width / 2.0),
            point.y / (height / 2.0),
            viewport_width,
            viewport_height,
        )),
    }
}

fn ndc_to_screen_3d(x: f64, y: f64, viewport_width: f64, viewport_height: f64) -> (f64, f64) {
    (
        (x + 1.0) * 0.5 * viewport_width,
        (1.0 - (y + 1.0) * 0.5) * viewport_height,
    )
}
