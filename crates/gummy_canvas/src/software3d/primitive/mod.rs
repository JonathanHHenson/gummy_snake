mod lathe;
mod spherical;
mod utils;

use pyo3::prelude::*;

use crate::software3d::model::types::{ObjModelData, Vec3d};
use utils::{empty_normals, some_texcoords, validate_positive};

pub(crate) use lathe::{cone_model_data, cylinder_model_data};
pub(crate) use spherical::{ellipsoid_model_data, sphere_model_data, torus_model_data};

pub(crate) fn plane_model_data(width: f64, height: Option<f64>) -> PyResult<ObjModelData> {
    let height = height.unwrap_or(width);
    validate_positive(
        &[("width", width), ("height", height)],
        "plane() dimensions must be positive.",
    )?;
    let hw = width / 2.0;
    let hh = height / 2.0;
    let vertices = vec![
        Vec3d {
            x: -hw,
            y: -hh,
            z: 0.0,
        },
        Vec3d {
            x: hw,
            y: -hh,
            z: 0.0,
        },
        Vec3d {
            x: hw,
            y: hh,
            z: 0.0,
        },
        Vec3d {
            x: -hw,
            y: hh,
            z: 0.0,
        },
    ];
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]),
        faces: vec![vec![0, 1, 2, 3]],
    })
}

pub(crate) fn box_model_data(
    width: f64,
    height: Option<f64>,
    depth: Option<f64>,
) -> PyResult<ObjModelData> {
    let height = height.unwrap_or(width);
    let depth = depth.unwrap_or(width);
    validate_positive(
        &[("width", width), ("height", height), ("depth", depth)],
        "box() dimensions must be positive.",
    )?;
    let hw = width / 2.0;
    let hh = height / 2.0;
    let hd = depth / 2.0;
    let specs = vec![
        vec![
            (-hw, hh, -hd),
            (hw, hh, -hd),
            (hw, -hh, -hd),
            (-hw, -hh, -hd),
        ],
        vec![(-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)],
        vec![
            (-hw, -hh, -hd),
            (hw, -hh, -hd),
            (hw, -hh, hd),
            (-hw, -hh, hd),
        ],
        vec![(hw, hh, -hd), (-hw, hh, -hd), (-hw, hh, hd), (hw, hh, hd)],
        vec![(hw, -hh, -hd), (hw, hh, -hd), (hw, hh, hd), (hw, -hh, hd)],
        vec![
            (-hw, -hh, hd),
            (-hw, hh, hd),
            (-hw, hh, -hd),
            (-hw, -hh, -hd),
        ],
    ];
    let uv = vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)];
    let mut vertices = Vec::with_capacity(24);
    let mut texcoords = Vec::with_capacity(24);
    let mut faces = Vec::with_capacity(6);
    for face_vertices in specs {
        let start = vertices.len();
        vertices.extend(face_vertices.into_iter().map(|(x, y, z)| Vec3d { x, y, z }));
        texcoords.extend(uv.iter().copied());
        faces.push(vec![start, start + 1, start + 2, start + 3]);
    }
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(texcoords),
        faces,
    })
}
