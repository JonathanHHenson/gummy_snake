use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::software3d::types::{ObjModelData, Vec3d};

pub(super) fn parse_obj_text(text: &str, source: &str) -> PyResult<ObjModelData> {
    let mut positions = Vec::new();
    let mut texcoords = Vec::new();
    let mut normals = Vec::new();
    let mut vertices = Vec::new();
    let mut vertex_texcoords = Vec::new();
    let mut vertex_normals = Vec::new();
    let mut faces = Vec::new();
    let mut vertex_map: HashMap<(usize, Option<usize>, Option<usize>), usize> = HashMap::new();
    for (line_index, raw_line) in text.lines().enumerate() {
        let line_number = line_index + 1;
        let line = raw_line
            .split_once('#')
            .map_or(raw_line, |(prefix, _)| prefix)
            .trim();
        if line.is_empty() {
            continue;
        }
        let mut parts = line.split_whitespace();
        let keyword = parts.next().unwrap_or_default();
        let values: Vec<&str> = parts.collect();
        match keyword {
            "v" => {
                if values.len() < 3 {
                    return Err(PyValueError::new_err(format!(
                        "OBJ vertex on line {line_number} in {source} requires x y z."
                    )));
                }
                positions.push(Vec3d {
                    x: parse_obj_float(values[0], "vertex", line_number, source)?,
                    y: parse_obj_float(values[1], "vertex", line_number, source)?,
                    z: parse_obj_float(values[2], "vertex", line_number, source)?,
                });
            }
            "vt" => {
                if values.len() < 2 {
                    return Err(PyValueError::new_err(format!(
                        "OBJ texcoord on line {line_number} in {source} requires u v."
                    )));
                }
                texcoords.push((
                    parse_obj_float(values[0], "texcoord", line_number, source)?,
                    parse_obj_float(values[1], "texcoord", line_number, source)?,
                ));
            }
            "vn" => {
                if values.len() < 3 {
                    return Err(PyValueError::new_err(format!(
                        "OBJ normal on line {line_number} in {source} requires x y z."
                    )));
                }
                normals.push(Vec3d {
                    x: parse_obj_float(values[0], "normal", line_number, source)?,
                    y: parse_obj_float(values[1], "normal", line_number, source)?,
                    z: parse_obj_float(values[2], "normal", line_number, source)?,
                });
            }
            "f" => {
                if values.len() < 3 {
                    return Err(PyValueError::new_err(format!(
                        "OBJ face on line {line_number} in {source} requires at least 3 vertices."
                    )));
                }
                let mut face = Vec::with_capacity(values.len());
                for token in values {
                    let reference = parse_obj_vertex_ref(
                        token,
                        positions.len(),
                        texcoords.len(),
                        normals.len(),
                        line_number,
                        source,
                    )?;
                    let index = if let Some(existing) = vertex_map.get(&reference).copied() {
                        existing
                    } else {
                        let (position_index, texcoord_index, normal_index) = reference;
                        vertices.push(positions[position_index]);
                        vertex_texcoords.push(texcoord_index.map(|index| texcoords[index]));
                        vertex_normals.push(normal_index.map(|index| normals[index]));
                        let next = vertices.len() - 1;
                        vertex_map.insert(reference, next);
                        next
                    };
                    face.push(index);
                }
                faces.push(face);
            }
            "o" | "g" | "s" | "mtllib" | "usemtl" => {}
            _ => {}
        }
    }
    if vertices.is_empty() || faces.is_empty() {
        return Err(PyValueError::new_err(format!(
            "OBJ model {source} contained no drawable faces."
        )));
    }
    Ok(ObjModelData {
        vertices,
        texcoords: vertex_texcoords,
        normals: vertex_normals,
        faces,
    })
}

fn parse_obj_float(raw: &str, kind: &str, line_number: usize, source: &str) -> PyResult<f64> {
    raw.parse::<f64>().map_err(|err| {
        PyValueError::new_err(format!(
            "OBJ {kind} value {raw:?} on line {line_number} in {source} is invalid: {err}."
        ))
    })
}

fn parse_obj_vertex_ref(
    token: &str,
    positions_len: usize,
    texcoords_len: usize,
    normals_len: usize,
    line_number: usize,
    source: &str,
) -> PyResult<(usize, Option<usize>, Option<usize>)> {
    let parts: Vec<&str> = token.split('/').collect();
    if parts.is_empty() || parts[0].is_empty() {
        return Err(PyValueError::new_err(format!(
            "OBJ face vertex {token:?} on line {line_number} in {source} is invalid."
        )));
    }
    let position = resolve_obj_index(parts[0], positions_len, "position", line_number, source)?;
    let texcoord = if parts.len() >= 2 && !parts[1].is_empty() {
        Some(resolve_obj_index(
            parts[1],
            texcoords_len,
            "texcoord",
            line_number,
            source,
        )?)
    } else {
        None
    };
    let normal = if parts.len() >= 3 && !parts[2].is_empty() {
        Some(resolve_obj_index(
            parts[2],
            normals_len,
            "normal",
            line_number,
            source,
        )?)
    } else {
        None
    };
    Ok((position, texcoord, normal))
}

fn resolve_obj_index(
    raw: &str,
    length: usize,
    kind: &str,
    line_number: usize,
    source: &str,
) -> PyResult<usize> {
    if length == 0 {
        return Err(PyValueError::new_err(format!(
            "OBJ references a {kind} before any {kind}s were defined on line {line_number} in {source}."
        )));
    }
    let index = raw.parse::<i64>().map_err(|_| {
        PyValueError::new_err(format!(
            "OBJ {kind} index {raw:?} on line {line_number} in {source} is invalid."
        ))
    })?;
    let resolved = if index > 0 {
        index - 1
    } else {
        length as i64 + index
    };
    if !(0..length as i64).contains(&resolved) {
        return Err(PyValueError::new_err(format!(
            "OBJ {kind} index {raw:?} on line {line_number} in {source} is out of range."
        )));
    }
    Ok(resolved as usize)
}
