use std::f64::consts::TAU;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::primitive_utils::{empty_normals, some_texcoords, validate_positive};
use crate::software3d::types::{ObjModelData, Vec3d};

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
