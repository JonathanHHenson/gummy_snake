use std::f64::consts::{PI, TAU};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::primitive_utils::{empty_normals, some_texcoords, validate_positive};
use crate::software3d::types::{ObjModelData, Vec3d};

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
