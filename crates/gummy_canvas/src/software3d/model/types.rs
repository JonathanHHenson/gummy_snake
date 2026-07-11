pub(crate) type Transform3D = [[f64; 4]; 4];

#[derive(Clone, Copy, Debug)]
pub(crate) struct Vec3d {
    pub(crate) x: f64,
    pub(crate) y: f64,
    pub(crate) z: f64,
}

#[derive(Clone, Debug)]
pub(crate) struct ObjModelData {
    pub(crate) vertices: Vec<Vec3d>,
    pub(crate) texcoords: Vec<Option<(f64, f64)>>,
    pub(crate) normals: Vec<Option<Vec3d>>,
    pub(crate) faces: Vec<Vec<usize>>,
}

#[derive(Clone, Debug)]
pub(crate) struct MeshPayload {
    pub(crate) vertices: Vec<Vec3d>,
    pub(crate) faces: Vec<Vec<usize>>,
    pub(crate) texcoords: Vec<(f64, f64)>,
}

#[derive(Clone, Debug)]
pub(crate) struct CameraPayload {
    pub(crate) eye: Vec3d,
    pub(crate) target: Vec3d,
    pub(crate) up: Vec3d,
}

#[derive(Clone, Debug)]
pub(crate) enum ProjectionPayload {
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
pub(crate) struct MaterialPayload {
    pub(crate) base_color: (f64, f64, f64, f64),
    pub(crate) emissive_color: (f64, f64, f64, f64),
    pub(crate) specular_color: (f64, f64, f64, f64),
    pub(crate) shininess: f64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum LightKindPayload {
    Ambient,
    Directional,
    Point,
}

#[derive(Clone, Debug)]
pub(crate) struct LightPayload {
    pub(crate) kind: LightKindPayload,
    pub(crate) color: (f64, f64, f64, f64),
    pub(crate) intensity: f64,
    pub(crate) position: Option<Vec3d>,
    pub(crate) direction: Option<Vec3d>,
}

#[derive(Clone, Debug)]
pub(crate) struct ProjectedPayloadFace {
    pub(crate) points: Vec<(f64, f64)>,
    pub(crate) depth: f64,
    pub(crate) normal: Vec3d,
    pub(crate) center: Vec3d,
    pub(crate) texcoords: Option<Vec<(f64, f64)>>,
}
