use std::f64::consts::{PI, TAU};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::types::{ObjModelData, Vec3d};

fn validate_positive(values: &[(&str, f64)], message: &str) -> PyResult<()> {
    if values.iter().any(|(_, value)| *value <= 0.0) {
        return Err(PyValueError::new_err(message.to_owned()));
    }
    Ok(())
}

fn empty_normals(count: usize) -> Vec<Option<Vec3d>> {
    vec![None; count]
}

fn some_texcoords(texcoords: Vec<(f64, f64)>) -> Vec<Option<(f64, f64)>> {
    texcoords.into_iter().map(Some).collect()
}

pub(super) fn plane_model_data(width: f64, height: Option<f64>) -> PyResult<ObjModelData> {
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

pub(super) fn box_model_data(
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

pub(super) fn sphere_model_data(
    radius: f64,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<ObjModelData> {
    validate_positive(&[("radius", radius)], "sphere() radius must be positive.")?;
    if detail_x < 3 || detail_y < 2 {
        return Err(PyValueError::new_err(
            "sphere() detail values must be at least 3 and 2.",
        ));
    }
    let mut vertices = Vec::with_capacity((detail_y + 1) * detail_x);
    let mut texcoords = Vec::with_capacity((detail_y + 1) * detail_x);
    let mut faces = Vec::with_capacity(detail_y * detail_x);
    for iy in 0..=detail_y {
        let phi = PI * iy as f64 / detail_y as f64;
        let y = phi.cos() * radius;
        let ring_radius = phi.sin() * radius;
        for ix in 0..detail_x {
            let theta = TAU * ix as f64 / detail_x as f64;
            vertices.push(Vec3d {
                x: theta.cos() * ring_radius,
                y,
                z: theta.sin() * ring_radius,
            });
            texcoords.push((
                ix as f64 / detail_x as f64,
                1.0 - iy as f64 / detail_y as f64,
            ));
        }
    }
    let vertex_index = |ix: usize, iy: usize| -> usize { iy * detail_x + (ix % detail_x) };
    for iy in 0..detail_y {
        for ix in 0..detail_x {
            let tl = vertex_index(ix, iy);
            let tr = vertex_index(ix + 1, iy);
            let bl = vertex_index(ix, iy + 1);
            let br = vertex_index(ix + 1, iy + 1);
            faces.push(if iy == 0 {
                vec![tl, bl, br]
            } else if iy == detail_y - 1 {
                vec![tl, tr, bl]
            } else {
                vec![tl, tr, br, bl]
            });
        }
    }
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(texcoords),
        faces,
    })
}

pub(super) fn ellipsoid_model_data(
    rx: f64,
    ry: Option<f64>,
    rz: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<ObjModelData> {
    let ry = ry.unwrap_or(rx);
    let rz = rz.unwrap_or(rx);
    validate_positive(
        &[("radius_x", rx), ("radius_y", ry), ("radius_z", rz)],
        "ellipsoid() radius values must be positive.",
    )?;
    let mut model = sphere_model_data(1.0, detail_x, detail_y)?;
    for vertex in &mut model.vertices {
        vertex.x *= rx;
        vertex.y *= ry;
        vertex.z *= rz;
    }
    Ok(model)
}

pub(super) fn cylinder_model_data(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    bottom_cap: bool,
    top_cap: bool,
) -> PyResult<ObjModelData> {
    validate_positive(
        &[("radius", radius), ("height", height)],
        "cylinder() radius and height must be positive.",
    )?;
    if detail_x < 3 || detail_y < 1 {
        return Err(PyValueError::new_err(
            "cylinder() detail values must be at least 3 and 1.",
        ));
    }
    let mut vertices = Vec::new();
    let mut texcoords = Vec::new();
    let mut faces = Vec::new();
    let half_height = height / 2.0;
    for iy in 0..=detail_y {
        let y = -half_height + height * iy as f64 / detail_y as f64;
        for ix in 0..detail_x {
            let theta = TAU * ix as f64 / detail_x as f64;
            vertices.push(Vec3d {
                x: theta.cos() * radius,
                y,
                z: theta.sin() * radius,
            });
            texcoords.push((ix as f64 / detail_x as f64, iy as f64 / detail_y as f64));
        }
    }
    let vertex_index = |ix: usize, iy: usize| -> usize { iy * detail_x + (ix % detail_x) };
    for iy in 0..detail_y {
        for ix in 0..detail_x {
            faces.push(vec![
                vertex_index(ix, iy),
                vertex_index(ix + 1, iy),
                vertex_index(ix + 1, iy + 1),
                vertex_index(ix, iy + 1),
            ]);
        }
    }
    if bottom_cap {
        let center = vertices.len();
        vertices.push(Vec3d {
            x: 0.0,
            y: -half_height,
            z: 0.0,
        });
        texcoords.push((0.5, 0.5));
        for ix in 0..detail_x {
            faces.push(vec![center, vertex_index(ix + 1, 0), vertex_index(ix, 0)]);
        }
    }
    if top_cap {
        let center = vertices.len();
        vertices.push(Vec3d {
            x: 0.0,
            y: half_height,
            z: 0.0,
        });
        texcoords.push((0.5, 0.5));
        for ix in 0..detail_x {
            faces.push(vec![
                center,
                vertex_index(ix, detail_y),
                vertex_index(ix + 1, detail_y),
            ]);
        }
    }
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(texcoords),
        faces,
    })
}

pub(super) fn cone_model_data(
    radius: f64,
    height: f64,
    detail_x: usize,
    detail_y: usize,
    cap: bool,
) -> PyResult<ObjModelData> {
    validate_positive(
        &[("radius", radius), ("height", height)],
        "cone() radius and height must be positive.",
    )?;
    if detail_x < 3 || detail_y < 1 {
        return Err(PyValueError::new_err(
            "cone() detail values must be at least 3 and 1.",
        ));
    }
    let mut vertices = Vec::new();
    let mut texcoords = Vec::new();
    let mut faces = Vec::new();
    let half_height = height / 2.0;
    for iy in 0..=detail_y {
        let fraction = iy as f64 / detail_y as f64;
        let ring_radius = radius * (1.0 - fraction);
        let y = -half_height + height * fraction;
        for ix in 0..detail_x {
            let theta = TAU * ix as f64 / detail_x as f64;
            vertices.push(Vec3d {
                x: theta.cos() * ring_radius,
                y,
                z: theta.sin() * ring_radius,
            });
            texcoords.push((ix as f64 / detail_x as f64, fraction));
        }
    }
    let vertex_index = |ix: usize, iy: usize| -> usize { iy * detail_x + (ix % detail_x) };
    for iy in 0..detail_y {
        for ix in 0..detail_x {
            if iy == detail_y - 1 {
                faces.push(vec![
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix, iy + 1),
                ]);
            } else {
                faces.push(vec![
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix + 1, iy + 1),
                    vertex_index(ix, iy + 1),
                ]);
            }
        }
    }
    if cap {
        let center = vertices.len();
        vertices.push(Vec3d {
            x: 0.0,
            y: -half_height,
            z: 0.0,
        });
        texcoords.push((0.5, 0.5));
        for ix in 0..detail_x {
            faces.push(vec![center, vertex_index(ix + 1, 0), vertex_index(ix, 0)]);
        }
    }
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(texcoords),
        faces,
    })
}

pub(super) fn torus_model_data(
    radius: f64,
    tube_radius: Option<f64>,
    detail_x: usize,
    detail_y: usize,
) -> PyResult<ObjModelData> {
    let tube = tube_radius.unwrap_or(radius / 4.0);
    validate_positive(
        &[("radius", radius), ("tube_radius", tube)],
        "torus() radius values must be positive.",
    )?;
    if detail_x < 3 || detail_y < 3 {
        return Err(PyValueError::new_err(
            "torus() detail values must be at least 3.",
        ));
    }
    let mut vertices = Vec::with_capacity(detail_x * detail_y);
    let mut texcoords = Vec::with_capacity(detail_x * detail_y);
    let mut faces = Vec::with_capacity(detail_x * detail_y);
    for iy in 0..detail_y {
        let phi = TAU * iy as f64 / detail_y as f64;
        let (sin_phi, cos_phi) = phi.sin_cos();
        for ix in 0..detail_x {
            let theta = TAU * ix as f64 / detail_x as f64;
            let ring = radius + tube * theta.cos();
            vertices.push(Vec3d {
                x: ring * cos_phi,
                y: tube * theta.sin(),
                z: ring * sin_phi,
            });
            texcoords.push((ix as f64 / detail_x as f64, iy as f64 / detail_y as f64));
        }
    }
    let vertex_index =
        |ix: usize, iy: usize| -> usize { (iy % detail_y) * detail_x + (ix % detail_x) };
    for iy in 0..detail_y {
        for ix in 0..detail_x {
            faces.push(vec![
                vertex_index(ix, iy),
                vertex_index(ix + 1, iy),
                vertex_index(ix + 1, iy + 1),
                vertex_index(ix, iy + 1),
            ]);
        }
    }
    Ok(ObjModelData {
        normals: empty_normals(vertices.len()),
        vertices,
        texcoords: some_texcoords(texcoords),
        faces,
    })
}
