use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

pub(crate) type Transform3D = [[f64; 4]; 4];

pub(crate) fn parse_transform_payload(
    transform: Option<Vec<f64>>,
) -> PyResult<Option<Transform3D>> {
    let Some(values) = transform else {
        return Ok(None);
    };
    match values.len() {
        6 => {
            let a = values[0];
            let b = values[1];
            let c = values[2];
            let d = values[3];
            let e = values[4];
            let f = values[5];
            let z_scale = ((a.hypot(b) + c.hypot(d)) / 2.0).max(1e-9);
            Ok(Some([
                [a, b, 0.0, 0.0],
                [c, d, 0.0, 0.0],
                [0.0, 0.0, z_scale, 0.0],
                [e, -f, 0.0, 1.0],
            ]))
        }
        16 => Ok(Some([
            [values[0], values[1], values[2], values[3]],
            [values[4], values[5], values[6], values[7]],
            [values[8], values[9], values[10], values[11]],
            [values[12], values[13], values[14], values[15]],
        ])),
        length => Err(PyValueError::new_err(format!(
            "model transform payload must contain 6 affine or 16 matrix values, got {length}"
        ))),
    }
}

#[derive(Clone, Copy, Debug)]
pub(super) struct Vec3d {
    pub(super) x: f64,
    pub(super) y: f64,
    pub(super) z: f64,
}

#[derive(Clone, Debug)]
pub(super) struct ObjModelData {
    pub(super) vertices: Vec<Vec3d>,
    pub(super) texcoords: Vec<Option<(f64, f64)>>,
    pub(super) normals: Vec<Option<Vec3d>>,
    pub(super) faces: Vec<Vec<usize>>,
}

#[derive(Clone, Debug)]
pub(super) struct MeshPayload {
    pub(super) vertices: Vec<Vec3d>,
    pub(super) faces: Vec<Vec<usize>>,
    pub(super) texcoords: Vec<(f64, f64)>,
}

#[derive(Clone, Debug)]
pub(super) struct CameraPayload {
    pub(super) eye: Vec3d,
    pub(super) target: Vec3d,
    pub(super) up: Vec3d,
}

#[derive(Clone, Debug)]
pub(super) enum ProjectionPayload {
    Perspective {
        fov_y: f64,
        aspect: Option<f64>,
        near: f64,
        far: f64,
    },
    Orthographic {
        width: f64,
        height: f64,
        near: f64,
        far: f64,
    },
}

#[derive(Clone, Debug)]
pub(super) struct MaterialPayload {
    pub(super) base_color: (f64, f64, f64, f64),
    pub(super) emissive_color: (f64, f64, f64, f64),
    pub(super) specular_color: (f64, f64, f64, f64),
    pub(super) shininess: f64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum LightKindPayload {
    Ambient,
    Directional,
    Point,
}

#[derive(Clone, Debug)]
pub(super) struct LightPayload {
    pub(super) kind: LightKindPayload,
    pub(super) color: (f64, f64, f64, f64),
    pub(super) intensity: f64,
    pub(super) position: Option<Vec3d>,
    pub(super) direction: Option<Vec3d>,
}

#[derive(Clone, Debug)]
pub(super) struct ProjectedPayloadFace {
    pub(super) points: Vec<(f64, f64)>,
    pub(super) depth: f64,
    pub(super) normal: Vec3d,
    pub(super) center: Vec3d,
    pub(super) texcoords: Option<Vec<(f64, f64)>>,
}
