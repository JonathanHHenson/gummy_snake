mod export;
mod parse;

use crate::software3d::model::types::{ObjModelData, Vec3d};

pub(crate) use export::{save_obj_model, save_stl_model};
pub(crate) use parse::parse_obj_text;

pub(crate) fn normalize_obj_model(mut model: ObjModelData) -> ObjModelData {
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
