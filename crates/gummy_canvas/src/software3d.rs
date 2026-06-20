use crate::image_ops::{alpha_composite_pixel, validate_rgba_buffer};
use crate::raster::point_in_polygon;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList};
use std::collections::HashMap;

pub(crate) fn parse_obj_model<'py>(
    py: Python<'py>,
    text: &str,
    source: &str,
    normalize: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let parsed = parse_obj_text(text, source)?;
    let parsed = if normalize {
        normalize_obj_model(parsed)
    } else {
        parsed
    };
    obj_model_to_dict(py, parsed)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn project_shade_faces<'py>(
    py: Python<'py>,
    meshes: &Bound<'py, PyAny>,
    camera: &Bound<'py, PyAny>,
    projection: &Bound<'py, PyAny>,
    viewport_width: f64,
    viewport_height: f64,
    material: &Bound<'py, PyAny>,
    lights: &Bound<'py, PyAny>,
    normal_material: bool,
    cull_backfaces: bool,
) -> PyResult<Bound<'py, PyList>> {
    if viewport_width <= 0.0 || viewport_height <= 0.0 {
        return Err(PyValueError::new_err(
            "viewport dimensions must be positive.",
        ));
    }
    let mesh_payloads = parse_mesh_payloads(meshes)?;
    let camera = parse_camera_payload(camera)?;
    let projection = parse_projection_payload(projection)?;
    validate_projection_payload(&projection)?;
    let material = parse_material_payload(material)?;
    let lights = parse_light_payloads(lights)?;
    let mut faces = Vec::new();
    for mesh in &mesh_payloads {
        faces.extend(project_mesh_payload_faces(
            mesh,
            &camera,
            &projection,
            viewport_width,
            viewport_height,
            cull_backfaces,
        )?);
    }
    faces.sort_by(|left, right| right.depth.total_cmp(&left.depth));
    let output = PyList::empty_bound(py);
    for face in faces {
        let color = shade_projected_face(&face, &camera, &material, &lights, normal_material)?;
        let dict = PyDict::new_bound(py);
        dict.set_item("points", face.points)?;
        dict.set_item("depth", face.depth)?;
        dict.set_item("normal", (face.normal.x, face.normal.y, face.normal.z))?;
        dict.set_item("center", (face.center.x, face.center.y, face.center.z))?;
        dict.set_item("texcoords", face.texcoords)?;
        dict.set_item("color", color)?;
        output.append(dict)?;
    }
    Ok(output)
}

pub(crate) fn rasterize_faces_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    faces: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    if width == 0 || height == 0 {
        return Err(PyValueError::new_err("raster dimensions must be positive."));
    }
    let mut pixels = vec![0_u8; width * height * 4];
    let sequence = faces.downcast::<PyList>()?;
    for face in sequence.iter() {
        let dict = face.downcast::<PyDict>()?;
        let points: Vec<(f64, f64)> = dict
            .get_item("points")?
            .ok_or_else(|| PyValueError::new_err("raster face is missing points."))?
            .extract()?;
        let color_float: (f64, f64, f64, f64) = dict
            .get_item("color")?
            .ok_or_else(|| PyValueError::new_err("raster face is missing color."))?
            .extract()?;
        let color = rgba_float_to_u8(color_float);
        let texcoords_item = dict.get_item("texcoords")?;
        let texture_item = dict.get_item("texture")?;
        if let (Some(texcoords_any), Some(texture_any)) = (texcoords_item, texture_item) {
            if !texture_any.is_none() && !texcoords_any.is_none() {
                let texcoords: Vec<(f64, f64)> = texcoords_any.extract()?;
                let texture_dict = texture_any.downcast::<PyDict>()?;
                let texture_width: usize = texture_dict
                    .get_item("width")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing width."))?
                    .extract()?;
                let texture_height: usize = texture_dict
                    .get_item("height")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing height."))?
                    .extract()?;
                let texture_pixels: Vec<u8> = texture_dict
                    .get_item("pixels")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing pixels."))?
                    .extract()?;
                validate_rgba_buffer(texture_pixels.len(), texture_width, texture_height)?;
                rasterize_textured_face(
                    &mut pixels,
                    width,
                    height,
                    &points,
                    &texcoords,
                    &texture_pixels,
                    texture_width,
                    texture_height,
                    color_float,
                );
                continue;
            }
        }
        rasterize_filled_polygon(&mut pixels, width, height, &points, color);
    }
    Ok(PyBytes::new_bound(py, &pixels))
}

#[derive(Clone, Copy, Debug)]
struct Vec3d {
    x: f64,
    y: f64,
    z: f64,
}

#[derive(Clone, Debug)]
struct ObjModelData {
    vertices: Vec<Vec3d>,
    texcoords: Vec<Option<(f64, f64)>>,
    normals: Vec<Option<Vec3d>>,
    faces: Vec<Vec<usize>>,
}

#[derive(Clone, Debug)]
struct MeshPayload {
    vertices: Vec<Vec3d>,
    faces: Vec<Vec<usize>>,
    texcoords: Vec<(f64, f64)>,
}

#[derive(Clone, Debug)]
struct CameraPayload {
    eye: Vec3d,
    target: Vec3d,
    up: Vec3d,
}

#[derive(Clone, Debug)]
enum ProjectionPayload {
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
struct MaterialPayload {
    base_color: (f64, f64, f64, f64),
    emissive_color: (f64, f64, f64, f64),
    specular_color: (f64, f64, f64, f64),
    shininess: f64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum LightKindPayload {
    Ambient,
    Directional,
    Point,
}

#[derive(Clone, Debug)]
struct LightPayload {
    kind: LightKindPayload,
    color: (f64, f64, f64, f64),
    intensity: f64,
    position: Option<Vec3d>,
    direction: Option<Vec3d>,
}

#[derive(Clone, Debug)]
struct ProjectedPayloadFace {
    points: Vec<(f64, f64)>,
    depth: f64,
    normal: Vec3d,
    center: Vec3d,
    texcoords: Option<Vec<(f64, f64)>>,
}

fn parse_obj_text(text: &str, source: &str) -> PyResult<ObjModelData> {
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

fn normalize_obj_model(mut model: ObjModelData) -> ObjModelData {
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

fn obj_model_to_dict<'py>(py: Python<'py>, model: ObjModelData) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item(
        "vertices",
        model
            .vertices
            .iter()
            .map(|vertex| (vertex.x, vertex.y, vertex.z))
            .collect::<Vec<_>>(),
    )?;
    dict.set_item("faces", model.faces)?;
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

fn parse_mesh_payloads(meshes: &Bound<'_, PyAny>) -> PyResult<Vec<MeshPayload>> {
    let sequence = meshes.downcast::<PyList>()?;
    let mut parsed = Vec::with_capacity(sequence.len());
    for item in sequence.iter() {
        let dict = item.downcast::<PyDict>()?;
        let vertices = dict
            .get_item("vertices")?
            .ok_or_else(|| PyValueError::new_err("mesh payload is missing vertices."))?
            .extract::<Vec<(f64, f64, f64)>>()?
            .into_iter()
            .map(|(x, y, z)| Vec3d { x, y, z })
            .collect();
        let faces = dict
            .get_item("faces")?
            .ok_or_else(|| PyValueError::new_err("mesh payload is missing faces."))?
            .extract::<Vec<Vec<usize>>>()?;
        let texcoords = dict
            .get_item("texcoords")?
            .map(|value| value.extract::<Vec<(f64, f64)>>())
            .transpose()?
            .unwrap_or_default();
        parsed.push(MeshPayload {
            vertices,
            faces,
            texcoords,
        });
    }
    Ok(parsed)
}

fn parse_vec3_payload(value: &Bound<'_, PyAny>) -> PyResult<Vec3d> {
    let (x, y, z): (f64, f64, f64) = value.extract()?;
    Ok(Vec3d { x, y, z })
}

fn parse_camera_payload(camera: &Bound<'_, PyAny>) -> PyResult<CameraPayload> {
    let dict = camera.downcast::<PyDict>()?;
    Ok(CameraPayload {
        eye: parse_vec3_payload(
            &dict
                .get_item("eye")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing eye."))?,
        )?,
        target: parse_vec3_payload(
            &dict
                .get_item("target")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing target."))?,
        )?,
        up: parse_vec3_payload(
            &dict
                .get_item("up")?
                .ok_or_else(|| PyValueError::new_err("camera payload is missing up."))?,
        )?,
    })
}

fn parse_projection_payload(projection: &Bound<'_, PyAny>) -> PyResult<ProjectionPayload> {
    let dict = projection.downcast::<PyDict>()?;
    let kind: String = dict
        .get_item("kind")?
        .ok_or_else(|| PyValueError::new_err("projection payload is missing kind."))?
        .extract()?;
    match kind.as_str() {
        "perspective" => Ok(ProjectionPayload::Perspective {
            fov_y: dict
                .get_item("fov_y")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing fov_y."))?
                .extract()?,
            aspect: dict
                .get_item("aspect")?
                .map(|value| value.extract::<Option<f64>>())
                .transpose()?
                .flatten(),
            near: dict
                .get_item("near")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing near."))?
                .extract()?,
            far: dict
                .get_item("far")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing far."))?
                .extract()?,
        }),
        "orthographic" => Ok(ProjectionPayload::Orthographic {
            width: dict
                .get_item("width")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing width."))?
                .extract()?,
            height: dict
                .get_item("height")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing height."))?
                .extract()?,
            near: dict
                .get_item("near")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing near."))?
                .extract()?,
            far: dict
                .get_item("far")?
                .ok_or_else(|| PyValueError::new_err("projection payload is missing far."))?
                .extract()?,
        }),
        _ => Err(PyValueError::new_err("unknown projection payload kind.")),
    }
}

fn parse_material_payload(material: &Bound<'_, PyAny>) -> PyResult<MaterialPayload> {
    let dict = material.downcast::<PyDict>()?;
    Ok(MaterialPayload {
        base_color: dict
            .get_item("base_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing base_color."))?
            .extract()?,
        emissive_color: dict
            .get_item("emissive_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing emissive_color."))?
            .extract()?,
        specular_color: dict
            .get_item("specular_color")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing specular_color."))?
            .extract()?,
        shininess: dict
            .get_item("shininess")?
            .ok_or_else(|| PyValueError::new_err("material payload is missing shininess."))?
            .extract()?,
    })
}

fn parse_light_payloads(lights: &Bound<'_, PyAny>) -> PyResult<Vec<LightPayload>> {
    let sequence = lights.downcast::<PyList>()?;
    let mut parsed = Vec::with_capacity(sequence.len());
    for item in sequence.iter() {
        let dict = item.downcast::<PyDict>()?;
        let kind_raw: String = dict
            .get_item("kind")?
            .ok_or_else(|| PyValueError::new_err("light payload is missing kind."))?
            .extract()?;
        let kind = match kind_raw.as_str() {
            "ambient" => LightKindPayload::Ambient,
            "directional" => LightKindPayload::Directional,
            "point" => LightKindPayload::Point,
            _ => return Err(PyValueError::new_err("unknown light payload kind.")),
        };
        let position = dict
            .get_item("position")?
            .filter(|value| !value.is_none())
            .map(|value| parse_vec3_payload(&value))
            .transpose()?;
        let direction = dict
            .get_item("direction")?
            .filter(|value| !value.is_none())
            .map(|value| parse_vec3_payload(&value))
            .transpose()?;
        parsed.push(LightPayload {
            kind,
            color: dict
                .get_item("color")?
                .ok_or_else(|| PyValueError::new_err("light payload is missing color."))?
                .extract()?,
            intensity: dict
                .get_item("intensity")?
                .ok_or_else(|| PyValueError::new_err("light payload is missing intensity."))?
                .extract()?,
            position,
            direction,
        });
    }
    Ok(parsed)
}

fn validate_projection_payload(projection: &ProjectionPayload) -> PyResult<()> {
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

fn project_mesh_payload_faces(
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

fn shade_projected_face(
    face: &ProjectedPayloadFace,
    camera: &CameraPayload,
    material: &MaterialPayload,
    lights: &[LightPayload],
    normal_material: bool,
) -> PyResult<(f64, f64, f64, f64)> {
    if normal_material {
        return Ok(clamp_rgba_float((
            (face.normal.x + 1.0) / 2.0,
            (face.normal.y + 1.0) / 2.0,
            (face.normal.z + 1.0) / 2.0,
            material.base_color.3,
        )));
    }
    let (base_r, base_g, base_b, base_a) = material.base_color;
    if lights.is_empty() {
        return Ok(clamp_rgba_float((
            base_r + material.emissive_color.0,
            base_g + material.emissive_color.1,
            base_b + material.emissive_color.2,
            base_a,
        )));
    }
    let mut result = [
        material.emissive_color.0,
        material.emissive_color.1,
        material.emissive_color.2,
    ];
    let view_dir = normalize_3d(sub_3d(camera.eye, face.center))?;
    for light in lights {
        let light_rgb = [light.color.0, light.color.1, light.color.2];
        let intensity = light.intensity.max(0.0);
        if light.kind == LightKindPayload::Ambient {
            for index in 0..3 {
                result[index] += [base_r, base_g, base_b][index] * light_rgb[index] * intensity;
            }
            continue;
        }
        let Some(light_dir) = light_direction_3d(light, face.center)? else {
            continue;
        };
        let diffuse = dot_3d(face.normal, light_dir).max(0.0);
        for index in 0..3 {
            result[index] +=
                [base_r, base_g, base_b][index] * light_rgb[index] * diffuse * intensity;
        }
        let half_vector = normalize_3d(add_3d(light_dir, view_dir))?;
        let specular = dot_3d(face.normal, half_vector)
            .max(0.0)
            .powf(material.shininess.max(1.0));
        for (index, component) in [
            material.specular_color.0,
            material.specular_color.1,
            material.specular_color.2,
        ]
        .iter()
        .enumerate()
        {
            result[index] += component * light_rgb[index] * specular * intensity;
        }
    }
    Ok(clamp_rgba_float((result[0], result[1], result[2], base_a)))
}

fn camera_space_3d(point: Vec3d, camera: &CameraPayload) -> PyResult<Vec3d> {
    let forward = normalize_3d(sub_3d(camera.target, camera.eye))?;
    let right = normalize_3d(cross_3d(forward, camera.up))?;
    let true_up = cross_3d(right, forward);
    let relative = sub_3d(point, camera.eye);
    Ok(Vec3d {
        x: dot_3d(relative, right),
        y: dot_3d(relative, true_up),
        z: dot_3d(relative, forward),
    })
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

fn face_center_3d(points: &[Vec3d]) -> Vec3d {
    let scale = 1.0 / points.len() as f64;
    Vec3d {
        x: points.iter().map(|point| point.x).sum::<f64>() * scale,
        y: points.iter().map(|point| point.y).sum::<f64>() * scale,
        z: points.iter().map(|point| point.z).sum::<f64>() * scale,
    }
}

fn face_normal_3d(points: &[Vec3d]) -> Option<Vec3d> {
    if points.len() < 3 {
        return None;
    }
    let normal = cross_3d(sub_3d(points[1], points[0]), sub_3d(points[2], points[0]));
    if dot_3d(normal, normal) == 0.0 {
        None
    } else {
        Some(normal)
    }
}

fn light_direction_3d(light: &LightPayload, center: Vec3d) -> PyResult<Option<Vec3d>> {
    match light.kind {
        LightKindPayload::Directional => light
            .direction
            .map(|direction| {
                normalize_3d(Vec3d {
                    x: -direction.x,
                    y: -direction.y,
                    z: -direction.z,
                })
            })
            .transpose(),
        LightKindPayload::Point => light
            .position
            .map(|position| normalize_3d(sub_3d(position, center)))
            .transpose(),
        LightKindPayload::Ambient => Ok(None),
    }
}

fn sub_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.x - b.x,
        y: a.y - b.y,
        z: a.z - b.z,
    }
}

fn add_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.x + b.x,
        y: a.y + b.y,
        z: a.z + b.z,
    }
}

fn dot_3d(a: Vec3d, b: Vec3d) -> f64 {
    a.x * b.x + a.y * b.y + a.z * b.z
}

fn cross_3d(a: Vec3d, b: Vec3d) -> Vec3d {
    Vec3d {
        x: a.y * b.z - a.z * b.y,
        y: a.z * b.x - a.x * b.z,
        z: a.x * b.y - a.y * b.x,
    }
}

fn normalize_3d(value: Vec3d) -> PyResult<Vec3d> {
    let length = dot_3d(value, value).sqrt();
    if length == 0.0 {
        return Err(PyValueError::new_err(
            "3D vectors must have non-zero length.",
        ));
    }
    Ok(Vec3d {
        x: value.x / length,
        y: value.y / length,
        z: value.z / length,
    })
}

fn clamp_rgba_float(color: (f64, f64, f64, f64)) -> (f64, f64, f64, f64) {
    let max_rgb = color.0.max(color.1).max(color.2);
    let (r, g, b) = if max_rgb > 1.0 {
        (color.0 / max_rgb, color.1 / max_rgb, color.2 / max_rgb)
    } else {
        (color.0, color.1, color.2)
    };
    (
        r.clamp(0.0, 1.0),
        g.clamp(0.0, 1.0),
        b.clamp(0.0, 1.0),
        color.3.clamp(0.0, 1.0),
    )
}

fn rgba_float_to_u8(color: (f64, f64, f64, f64)) -> [u8; 4] {
    [
        (color.0.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.1.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.2.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.3.clamp(0.0, 1.0) * 255.0).round() as u8,
    ]
}

fn rasterize_filled_polygon(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: &[(f64, f64)],
    color: [u8; 4],
) {
    if points.len() < 3 {
        return;
    }
    let min_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let max_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min((width - 1) as f64) as usize;
    let min_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let max_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min((height - 1) as f64) as usize;
    if min_x > max_x || min_y > max_y {
        return;
    }
    for y in min_y..=max_y {
        for x in min_x..=max_x {
            if point_in_polygon((x as f64 + 0.5, y as f64 + 0.5), points) {
                let offset = (y * width + x) * 4;
                alpha_composite_pixel(&mut pixels[offset..offset + 4], &color);
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn rasterize_textured_face(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: &[(f64, f64)],
    texcoords: &[(f64, f64)],
    texture: &[u8],
    texture_width: usize,
    texture_height: usize,
    modulation: (f64, f64, f64, f64),
) {
    if points.len() < 3 || points.len() != texcoords.len() {
        return;
    }
    for index in 1..points.len() - 1 {
        rasterize_textured_triangle(
            pixels,
            width,
            height,
            [points[0], points[index], points[index + 1]],
            [texcoords[0], texcoords[index], texcoords[index + 1]],
            texture,
            texture_width,
            texture_height,
            modulation,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn rasterize_textured_triangle(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: [(f64, f64); 3],
    texcoords: [(f64, f64); 3],
    texture: &[u8],
    texture_width: usize,
    texture_height: usize,
    modulation: (f64, f64, f64, f64),
) {
    let [(x1, y1), (x2, y2), (x3, y3)] = points;
    let denominator = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3);
    if denominator == 0.0 {
        return;
    }
    let min_x = x1.min(x2).min(x3).floor().max(0.0) as usize;
    let max_x = x1.max(x2).max(x3).ceil().min((width - 1) as f64) as usize;
    let min_y = y1.min(y2).min(y3).floor().max(0.0) as usize;
    let max_y = y1.max(y2).max(y3).ceil().min((height - 1) as f64) as usize;
    if min_x > max_x || min_y > max_y {
        return;
    }
    for py in min_y..=max_y {
        let sample_y = py as f64 + 0.5;
        for px in min_x..=max_x {
            let sample_x = px as f64 + 0.5;
            let w1 = ((y2 - y3) * (sample_x - x3) + (x3 - x2) * (sample_y - y3)) / denominator;
            let w2 = ((y3 - y1) * (sample_x - x3) + (x1 - x3) * (sample_y - y3)) / denominator;
            let w3 = 1.0 - w1 - w2;
            if w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6 {
                continue;
            }
            let u = w1 * texcoords[0].0 + w2 * texcoords[1].0 + w3 * texcoords[2].0;
            let v = w1 * texcoords[0].1 + w2 * texcoords[1].1 + w3 * texcoords[2].1;
            let tx = ((u.clamp(0.0, 1.0) * (texture_width - 1) as f64).round() as usize)
                .min(texture_width - 1);
            let ty = (((1.0 - v.clamp(0.0, 1.0)) * (texture_height - 1) as f64).round() as usize)
                .min(texture_height - 1);
            let src = (ty * texture_width + tx) * 4;
            let shaded = [
                (texture[src] as f64 * modulation.0)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 1] as f64 * modulation.1)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 2] as f64 * modulation.2)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 3] as f64 * modulation.3)
                    .round()
                    .clamp(0.0, 255.0) as u8,
            ];
            let dst = (py * width + px) * 4;
            alpha_composite_pixel(&mut pixels[dst..dst + 4], &shaded);
        }
    }
}
