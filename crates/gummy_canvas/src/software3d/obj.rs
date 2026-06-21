use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Write};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::software3d::math::triangle_normal;
use crate::software3d::types::{ObjModelData, Vec3d};

fn format_g9(value: f64) -> String {
    if !value.is_finite() {
        return value.to_string();
    }
    if value == 0.0 {
        return "0".to_owned();
    }

    let abs_value = value.abs();
    let exponent = abs_value.log10().floor() as i32;
    if !(-4..9).contains(&exponent) {
        let digits_after_decimal = 8_i32.saturating_sub(exponent).max(0) as usize;
        let mut rendered = format!("{value:.digits_after_decimal$e}");
        if let Some((mantissa, exponent_text)) = rendered.split_once('e') {
            let mut mantissa = mantissa
                .trim_end_matches('0')
                .trim_end_matches('.')
                .to_owned();
            if mantissa == "-0" {
                mantissa = "0".to_owned();
            }
            let exponent_value = exponent_text.parse::<i32>().unwrap_or(0);
            rendered = format!("{mantissa}e{exponent_value:+03}");
        }
        return rendered;
    }

    let digits_after_decimal = 8_i32.saturating_sub(exponent).max(0) as usize;
    let mut rendered = format!("{value:.digits_after_decimal$}");
    while rendered.contains('.') && rendered.ends_with('0') {
        rendered.pop();
    }
    if rendered.ends_with('.') {
        rendered.pop();
    }
    if rendered == "-0" {
        "0".to_owned()
    } else {
        rendered
    }
}

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

pub(super) fn normalize_obj_model(mut model: ObjModelData) -> ObjModelData {
    if model.vertices.is_empty() {
        return model;
    }
    let mut min_x = f64::INFINITY;
    let mut min_y = f64::INFINITY;
    let mut min_z = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    let mut max_z = f64::NEG_INFINITY;
    for vertex in &model.vertices {
        min_x = min_x.min(vertex.x);
        min_y = min_y.min(vertex.y);
        min_z = min_z.min(vertex.z);
        max_x = max_x.max(vertex.x);
        max_y = max_y.max(vertex.y);
        max_z = max_z.max(vertex.z);
    }
    let span = (max_x - min_x).max(max_y - min_y).max(max_z - min_z);
    if span <= 0.0 {
        return model;
    }
    let center = Vec3d {
        x: (min_x + max_x) / 2.0,
        y: (min_y + max_y) / 2.0,
        z: (min_z + max_z) / 2.0,
    };
    let scale = 2.0 / span;
    for vertex in &mut model.vertices {
        vertex.x = (vertex.x - center.x) * scale;
        vertex.y = (vertex.y - center.y) * scale;
        vertex.z = (vertex.z - center.z) * scale;
    }
    model
}

pub(super) fn obj_model_to_dict<'py>(
    py: Python<'py>,
    model: &ObjModelData,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item(
        "vertices",
        model
            .vertices
            .iter()
            .map(|vertex| (vertex.x, vertex.y, vertex.z))
            .collect::<Vec<_>>(),
    )?;
    dict.set_item("faces", model.faces.clone())?;
    if model.texcoords.iter().all(Option::is_some) {
        dict.set_item(
            "texcoords",
            model
                .texcoords
                .iter()
                .filter_map(|value| *value)
                .collect::<Vec<_>>(),
        )?;
    } else {
        dict.set_item("texcoords", Vec::<(f64, f64)>::new())?;
    }
    if model.normals.iter().all(Option::is_some) {
        dict.set_item(
            "normals",
            model
                .normals
                .iter()
                .filter_map(|value| *value)
                .map(|normal| (normal.x, normal.y, normal.z))
                .collect::<Vec<_>>(),
        )?;
    } else {
        dict.set_item("normals", Vec::<(f64, f64, f64)>::new())?;
    }
    Ok(dict)
}

pub(super) fn save_obj_model(model: &ObjModelData, path: &str) -> PyResult<()> {
    let file = File::create(path)
        .map_err(|err| PyValueError::new_err(format!("Could not create OBJ file {path}: {err}")))?;
    let mut writer = BufWriter::new(file);
    writeln!(writer, "# Generated by Gummy Snake")
        .map_err(|err| PyValueError::new_err(format!("Could not write OBJ file {path}: {err}")))?;
    for vertex in &model.vertices {
        writeln!(
            writer,
            "v {} {} {}",
            format_g9(vertex.x),
            format_g9(vertex.y),
            format_g9(vertex.z)
        )
        .map_err(|err| PyValueError::new_err(format!("Could not write OBJ file {path}: {err}")))?;
    }
    if model.texcoords.iter().all(Option::is_some) {
        for texcoord in &model.texcoords {
            let (u, v) = texcoord.unwrap_or((0.0, 0.0));
            writeln!(writer, "vt {} {}", format_g9(u), format_g9(v)).map_err(|err| {
                PyValueError::new_err(format!("Could not write OBJ file {path}: {err}"))
            })?;
        }
    }
    for face in &model.faces {
        write!(writer, "f").map_err(|err| {
            PyValueError::new_err(format!("Could not write OBJ file {path}: {err}"))
        })?;
        for index in face {
            write!(writer, " {}", index + 1).map_err(|err| {
                PyValueError::new_err(format!("Could not write OBJ file {path}: {err}"))
            })?;
        }
        writeln!(writer).map_err(|err| {
            PyValueError::new_err(format!("Could not write OBJ file {path}: {err}"))
        })?;
    }
    writer
        .flush()
        .map_err(|err| PyValueError::new_err(format!("Could not write OBJ file {path}: {err}")))
}

pub(super) fn save_stl_model(model: &ObjModelData, path: &str, name: &str) -> PyResult<()> {
    let file = File::create(path)
        .map_err(|err| PyValueError::new_err(format!("Could not create STL file {path}: {err}")))?;
    let mut writer = BufWriter::new(file);
    writeln!(writer, "solid {name}")
        .map_err(|err| PyValueError::new_err(format!("Could not write STL file {path}: {err}")))?;
    for face in &model.faces {
        if face.len() < 3 {
            continue;
        }
        let first = face[0];
        for index in 1..face.len() - 1 {
            let a = model.vertices[first];
            let b = model.vertices[face[index]];
            let c = model.vertices[face[index + 1]];
            let normal = triangle_normal(a, b, c);
            writeln!(
                writer,
                "  facet normal {} {} {}",
                format_g9(normal.x),
                format_g9(normal.y),
                format_g9(normal.z)
            )
            .map_err(|err| {
                PyValueError::new_err(format!("Could not write STL file {path}: {err}"))
            })?;
            writeln!(writer, "    outer loop").map_err(|err| {
                PyValueError::new_err(format!("Could not write STL file {path}: {err}"))
            })?;
            for vertex in [a, b, c] {
                writeln!(
                    writer,
                    "      vertex {} {} {}",
                    format_g9(vertex.x),
                    format_g9(vertex.y),
                    format_g9(vertex.z)
                )
                .map_err(|err| {
                    PyValueError::new_err(format!("Could not write STL file {path}: {err}"))
                })?;
            }
            writeln!(writer, "    endloop").map_err(|err| {
                PyValueError::new_err(format!("Could not write STL file {path}: {err}"))
            })?;
            writeln!(writer, "  endfacet").map_err(|err| {
                PyValueError::new_err(format!("Could not write STL file {path}: {err}"))
            })?;
        }
    }
    writeln!(writer, "endsolid {name}")
        .map_err(|err| PyValueError::new_err(format!("Could not write STL file {path}: {err}")))?;
    writer
        .flush()
        .map_err(|err| PyValueError::new_err(format!("Could not write STL file {path}: {err}")))
}
