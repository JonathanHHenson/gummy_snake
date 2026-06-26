use super::super::{PRIMITIVE_BATCH_ELLIPSE, PRIMITIVE_BATCH_RECT, PRIMITIVE_BATCH_TRIANGLE};
use crate::*;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

pub(super) fn fill_primitive_batch_cache_key(
    records: &[(u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8)],
    matrix: Matrix,
    pixel_density: f64,
    physical_width: usize,
    physical_height: usize,
) -> u64 {
    let mut hasher = DefaultHasher::new();
    matrix.0.to_bits().hash(&mut hasher);
    matrix.1.to_bits().hash(&mut hasher);
    matrix.2.to_bits().hash(&mut hasher);
    matrix.3.to_bits().hash(&mut hasher);
    matrix.4.to_bits().hash(&mut hasher);
    matrix.5.to_bits().hash(&mut hasher);
    pixel_density.to_bits().hash(&mut hasher);
    physical_width.hash(&mut hasher);
    physical_height.hash(&mut hasher);
    records.len().hash(&mut hasher);
    for record in records {
        record.0.hash(&mut hasher);
        record.1.to_bits().hash(&mut hasher);
        record.2.to_bits().hash(&mut hasher);
        record.3.to_bits().hash(&mut hasher);
        record.4.to_bits().hash(&mut hasher);
        record.5.to_bits().hash(&mut hasher);
        record.6.to_bits().hash(&mut hasher);
        record.7.hash(&mut hasher);
        record.8.hash(&mut hasher);
        record.9.hash(&mut hasher);
        record.10.hash(&mut hasher);
    }
    hasher.finish()
}

pub(super) fn fill_primitive_batch_instances(
    records: &[(u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8)],
    matrix: Matrix,
    pixel_density: f64,
    _physical_width: usize,
    _physical_height: usize,
) -> PyResult<Option<Vec<gpu::PrimitiveInstance>>> {
    let axis_aligned = matrix.1.abs() <= f64::EPSILON && matrix.2.abs() <= f64::EPSILON;
    if !axis_aligned
        && records
            .iter()
            .any(|record| record.0 == PRIMITIVE_BATCH_RECT || record.0 == PRIMITIVE_BATCH_ELLIPSE)
    {
        return Ok(None);
    }
    let mut instances = Vec::with_capacity(records.len());
    for (kind, a, b, c, d, e, f, r, g, blue, alpha) in records {
        let color = [
            *r as f32 / 255.0,
            *g as f32 / 255.0,
            *blue as f32 / 255.0,
            *alpha as f32 / 255.0,
        ];
        match *kind {
            PRIMITIVE_BATCH_RECT | PRIMITIVE_BATCH_ELLIPSE => {
                let p0 = transform_batch_point(matrix, pixel_density, *a, *b);
                let p1 = transform_batch_point(matrix, pixel_density, *a + *c, *b + *d);
                let min_x = p0.0.min(p1.0) as f32;
                let min_y = p0.1.min(p1.1) as f32;
                let max_x = p0.0.max(p1.0) as f32;
                let max_y = p0.1.max(p1.1) as f32;
                if !min_x.is_finite()
                    || !min_y.is_finite()
                    || !max_x.is_finite()
                    || !max_y.is_finite()
                    || min_x == max_x
                    || min_y == max_y
                {
                    continue;
                }
                instances.push(gpu::PrimitiveInstance {
                    p0: [min_x, min_y],
                    p1: [max_x, max_y],
                    p2: [0.0, 0.0],
                    bounds: [min_x, min_y, max_x, max_y],
                    color,
                    params: [*kind as f32, 0.0, 0.0, 0.0],
                });
            }
            PRIMITIVE_BATCH_TRIANGLE => {
                let p0 = transform_batch_point(matrix, pixel_density, *a, *b);
                let p1 = transform_batch_point(matrix, pixel_density, *c, *d);
                let p2 = transform_batch_point(matrix, pixel_density, *e, *f);
                let min_x = p0.0.min(p1.0).min(p2.0) as f32;
                let min_y = p0.1.min(p1.1).min(p2.1) as f32;
                let max_x = p0.0.max(p1.0).max(p2.0) as f32;
                let max_y = p0.1.max(p1.1).max(p2.1) as f32;
                if !min_x.is_finite()
                    || !min_y.is_finite()
                    || !max_x.is_finite()
                    || !max_y.is_finite()
                    || min_x == max_x
                    || min_y == max_y
                {
                    continue;
                }
                instances.push(gpu::PrimitiveInstance {
                    p0: [p0.0 as f32, p0.1 as f32],
                    p1: [p1.0 as f32, p1.1 as f32],
                    p2: [p2.0 as f32, p2.1 as f32],
                    bounds: [min_x, min_y, max_x, max_y],
                    color,
                    params: [PRIMITIVE_BATCH_TRIANGLE as f32, 0.0, 0.0, 0.0],
                });
            }
            _ => {
                return Err(PyValueError::new_err(format!(
                    "Unknown primitive batch record kind {kind}."
                )));
            }
        }
    }
    Ok(Some(instances))
}

fn transform_batch_point(matrix: Matrix, pixel_density: f64, x: f64, y: f64) -> Point {
    let (a, b, c, d, e, f) = matrix;
    (
        (a * x + c * y + e) * pixel_density,
        (b * x + d * y + f) * pixel_density,
    )
}
