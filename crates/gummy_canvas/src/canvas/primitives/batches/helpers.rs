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
                if !a.is_finite()
                    || !b.is_finite()
                    || !c.is_finite()
                    || !d.is_finite()
                    || *c == 0.0
                    || *d == 0.0
                {
                    continue;
                }
                instances.push(transformed_rect_like_instance(
                    (*a, *b),
                    (*a + *c, *b + *d),
                    matrix,
                    pixel_density,
                    color,
                    if *kind == PRIMITIVE_BATCH_RECT {
                        5.0
                    } else {
                        7.0
                    },
                    0.0,
                ));
            }
            PRIMITIVE_BATCH_TRIANGLE => {
                if !a.is_finite()
                    || !b.is_finite()
                    || !c.is_finite()
                    || !d.is_finite()
                    || !e.is_finite()
                    || !f.is_finite()
                    || ((*c - *a) * (*f - *b) - (*d - *b) * (*e - *a)).abs() <= f64::EPSILON
                {
                    continue;
                }
                instances.push(transformed_triangle_instance(
                    (*a, *b),
                    (*c, *d),
                    (*e, *f),
                    matrix,
                    pixel_density,
                    color,
                ));
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

fn transformed_rect_like_instance(
    p0: Point,
    p1: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: [f32; 4],
    kind: f32,
    stroke_width: f64,
) -> gpu::PrimitiveInstance {
    let (a, b, c, d, e, f) = matrix;
    gpu::PrimitiveInstance {
        p0: [p0.0 as f32, p0.1 as f32],
        p1: [p1.0 as f32, p1.1 as f32],
        p2: [(a * pixel_density) as f32, (b * pixel_density) as f32],
        bounds: [
            (c * pixel_density) as f32,
            (d * pixel_density) as f32,
            (e * pixel_density) as f32,
            (f * pixel_density) as f32,
        ],
        color,
        params: [kind, stroke_width as f32, 0.0, 0.0],
    }
}

fn transformed_triangle_instance(
    p0: Point,
    p1: Point,
    p2: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: [f32; 4],
) -> gpu::PrimitiveInstance {
    let (a, b, c, d, e, f) = matrix;
    gpu::PrimitiveInstance {
        p0: [p0.0 as f32, p0.1 as f32],
        p1: [p1.0 as f32, p1.1 as f32],
        p2: [p2.0 as f32, p2.1 as f32],
        bounds: [
            (a * pixel_density) as f32,
            (b * pixel_density) as f32,
            (c * pixel_density) as f32,
            (d * pixel_density) as f32,
        ],
        color,
        params: [
            6.0,
            (e * pixel_density) as f32,
            (f * pixel_density) as f32,
            0.0,
        ],
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    type FillRecord = (u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8);

    fn rect_record() -> FillRecord {
        (
            PRIMITIVE_BATCH_RECT,
            1.0,
            2.0,
            3.0,
            4.0,
            0.0,
            0.0,
            10,
            20,
            30,
            40,
        )
    }

    #[test]
    fn fill_primitive_cache_key_tracks_canvas_scale_and_content() {
        let records = vec![rect_record()];
        let identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0);
        let base = fill_primitive_batch_cache_key(&records, identity, 1.0, 20, 30);

        assert_ne!(
            base,
            fill_primitive_batch_cache_key(&records, identity, 2.0, 40, 60)
        );
        assert_ne!(
            base,
            fill_primitive_batch_cache_key(
                &[(
                    PRIMITIVE_BATCH_RECT,
                    1.0,
                    2.0,
                    5.0,
                    4.0,
                    0.0,
                    0.0,
                    10,
                    20,
                    30,
                    40
                )],
                identity,
                1.0,
                20,
                30,
            )
        );
    }

    #[test]
    fn fill_primitive_instances_carry_logical_coordinates_and_scaled_matrix() {
        let instances = fill_primitive_batch_instances(
            &[rect_record()],
            (1.0, 0.0, 0.0, 1.0, 5.0, 7.0),
            2.0,
            40,
            60,
        )
        .expect("valid records")
        .expect("rects use procedural instances");

        assert_eq!(instances.len(), 1);
        assert_eq!(instances[0].p0, [1.0, 2.0]);
        assert_eq!(instances[0].p1, [4.0, 6.0]);
        assert_eq!(instances[0].p2, [2.0, 0.0]);
        assert_eq!(instances[0].bounds, [0.0, 2.0, 10.0, 14.0]);
        assert_eq!(instances[0].params[0], 5.0);
        assert_eq!(
            instances[0].color,
            [10.0 / 255.0, 20.0 / 255.0, 30.0 / 255.0, 40.0 / 255.0]
        );
    }

    #[test]
    fn fill_primitive_instances_keep_rotated_rects_on_gpu() {
        let instances = fill_primitive_batch_instances(
            &[rect_record()],
            (0.0, 1.0, -1.0, 0.0, 0.0, 0.0),
            1.0,
            20,
            30,
        )
        .expect("valid rotated record")
        .expect("rotated rects use procedural instances");

        assert_eq!(instances.len(), 1);
        assert_eq!(instances[0].p0, [1.0, 2.0]);
        assert_eq!(instances[0].p1, [4.0, 6.0]);
        assert_eq!(instances[0].p2, [0.0, 1.0]);
        assert_eq!(instances[0].bounds, [-1.0, 0.0, 0.0, 0.0]);
        assert_eq!(instances[0].params[0], 5.0);
    }

    #[test]
    fn fill_primitive_instances_skip_degenerate_records() {
        let instances = fill_primitive_batch_instances(
            &[(
                PRIMITIVE_BATCH_RECT,
                1.0,
                2.0,
                0.0,
                4.0,
                0.0,
                0.0,
                10,
                20,
                30,
                40,
            )],
            (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            1.0,
            20,
            30,
        )
        .expect("degenerate supported records are skipped")
        .expect("rects use procedural instances");

        assert!(instances.is_empty());
    }
}
