use crate::gpu;
use crate::raster::Matrix;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

pub(super) type PrimitiveBatchTuple = (u8, f64, f64, f64, f64, f64, f64);
pub(super) type FillPrimitiveBatchTuple = (u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8);

/// Canvas-local primitive tags. ECS only owns the compact fill subset 1-3.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub(super) enum PrimitiveBatchKind {
    Rect = 1,
    Triangle = 2,
    Ellipse = 3,
    Line = 4,
}

impl TryFrom<u8> for PrimitiveBatchKind {
    type Error = u8;

    fn try_from(kind: u8) -> Result<Self, Self::Error> {
        match kind {
            1 => Ok(Self::Rect),
            2 => Ok(Self::Triangle),
            3 => Ok(Self::Ellipse),
            4 => Ok(Self::Line),
            _ => Err(kind),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub(super) struct PrimitiveBatchRecord {
    pub(super) kind: u8,
    pub(super) a: f64,
    pub(super) b: f64,
    pub(super) c: f64,
    pub(super) d: f64,
    pub(super) e: f64,
    pub(super) f: f64,
}

impl From<PrimitiveBatchTuple> for PrimitiveBatchRecord {
    fn from((kind, a, b, c, d, e, f): PrimitiveBatchTuple) -> Self {
        Self {
            kind,
            a,
            b,
            c,
            d,
            e,
            f,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub(super) struct FillPrimitiveBatchRecord {
    pub(super) kind: u8,
    pub(super) a: f64,
    pub(super) b: f64,
    pub(super) c: f64,
    pub(super) d: f64,
    pub(super) e: f64,
    pub(super) f: f64,
    pub(super) r: u8,
    pub(super) g: u8,
    pub(super) blue: u8,
    pub(super) alpha: u8,
}

impl From<FillPrimitiveBatchTuple> for FillPrimitiveBatchRecord {
    fn from((kind, a, b, c, d, e, f, r, g, blue, alpha): FillPrimitiveBatchTuple) -> Self {
        Self {
            kind,
            a,
            b,
            c,
            d,
            e,
            f,
            r,
            g,
            blue,
            alpha,
        }
    }
}

pub(super) fn fill_primitive_batch_cache_key(
    records: &[FillPrimitiveBatchRecord],
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
        record.kind.hash(&mut hasher);
        record.a.to_bits().hash(&mut hasher);
        record.b.to_bits().hash(&mut hasher);
        record.c.to_bits().hash(&mut hasher);
        record.d.to_bits().hash(&mut hasher);
        record.e.to_bits().hash(&mut hasher);
        record.f.to_bits().hash(&mut hasher);
        record.r.hash(&mut hasher);
        record.g.hash(&mut hasher);
        record.blue.hash(&mut hasher);
        record.alpha.hash(&mut hasher);
    }
    hasher.finish()
}

pub(super) fn unknown_primitive_batch_kind_message(kind: u8) -> String {
    format!("Unknown primitive batch record kind {kind}.")
}

pub(super) fn fill_primitive_batch_instances(
    records: &[FillPrimitiveBatchRecord],
    matrix: Matrix,
    pixel_density: f64,
    _physical_width: usize,
    _physical_height: usize,
) -> PyResult<Option<Vec<gpu::PrimitiveInstance>>> {
    let mut instances = Vec::with_capacity(records.len());
    for record in records {
        let color = [
            record.r as f32 / 255.0,
            record.g as f32 / 255.0,
            record.blue as f32 / 255.0,
            record.alpha as f32 / 255.0,
        ];
        match PrimitiveBatchKind::try_from(record.kind) {
            Ok(PrimitiveBatchKind::Rect | PrimitiveBatchKind::Ellipse) => {
                if !record.a.is_finite()
                    || !record.b.is_finite()
                    || !record.c.is_finite()
                    || !record.d.is_finite()
                    || record.c == 0.0
                    || record.d == 0.0
                {
                    continue;
                }
                let p0 = (record.a, record.b);
                let p1 = (record.a + record.c, record.b + record.d);
                let instance = match PrimitiveBatchKind::try_from(record.kind)
                    .expect("validated primitive batch kind")
                {
                    PrimitiveBatchKind::Rect => {
                        crate::canvas::gpu::shapes::procedural_rect_instance(
                            p0,
                            p1,
                            matrix,
                            pixel_density,
                            color,
                        )
                    }
                    PrimitiveBatchKind::Ellipse => {
                        crate::canvas::gpu::shapes::procedural_ellipse_instance(
                            p0,
                            p1,
                            matrix,
                            pixel_density,
                            color,
                            0.0,
                        )
                    }
                    _ => unreachable!("only rect-like kinds reach this branch"),
                };
                instances.push(instance);
            }
            Ok(PrimitiveBatchKind::Triangle) => {
                if !record.a.is_finite()
                    || !record.b.is_finite()
                    || !record.c.is_finite()
                    || !record.d.is_finite()
                    || !record.e.is_finite()
                    || !record.f.is_finite()
                    || ((record.c - record.a) * (record.f - record.b)
                        - (record.d - record.b) * (record.e - record.a))
                        .abs()
                        <= f64::EPSILON
                {
                    continue;
                }
                instances.push(crate::canvas::gpu::shapes::procedural_triangle_instance(
                    (record.a, record.b),
                    (record.c, record.d),
                    (record.e, record.f),
                    matrix,
                    pixel_density,
                    color,
                ));
            }
            Ok(PrimitiveBatchKind::Line) | Err(_) => {
                return Err(PyValueError::new_err(unknown_primitive_batch_kind_message(
                    record.kind,
                )));
            }
        }
    }
    Ok(Some(instances))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect_record() -> FillPrimitiveBatchRecord {
        FillPrimitiveBatchRecord::from((
            PrimitiveBatchKind::Rect as u8,
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
        ))
    }

    #[test]
    fn primitive_batch_kind_keeps_canvas_line_outside_ecs_fill_protocol() {
        assert_eq!(PrimitiveBatchKind::Rect as u8, 1);
        assert_eq!(PrimitiveBatchKind::Triangle as u8, 2);
        assert_eq!(PrimitiveBatchKind::Ellipse as u8, 3);
        assert_eq!(PrimitiveBatchKind::Line as u8, 4);
        assert_eq!(PrimitiveBatchKind::try_from(99), Err(99));
        assert_eq!(
            unknown_primitive_batch_kind_message(99),
            "Unknown primitive batch record kind 99."
        );
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
        let changed = FillPrimitiveBatchRecord {
            c: 5.0,
            ..rect_record()
        };
        assert_ne!(
            base,
            fill_primitive_batch_cache_key(&[changed], identity, 1.0, 20, 30)
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
        let degenerate = FillPrimitiveBatchRecord {
            c: 0.0,
            ..rect_record()
        };
        let instances = fill_primitive_batch_instances(
            &[degenerate],
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
