pub(crate) type Transform2D = (f64, f64, f64, f64, f64, f64);

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
