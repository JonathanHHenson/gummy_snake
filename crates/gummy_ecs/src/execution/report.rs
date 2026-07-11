use crate::column::EcsValue;
use crate::entity::Entity;

#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionWrite {
    ComponentField {
        entity: Entity,
        component: String,
        field: String,
        value: EcsValue,
    },
    ResourceField {
        resource: String,
        field: String,
        value: EcsValue,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionEvent {
    pub event_type: String,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionCanvasCommand {
    pub command: String,
    pub args: Vec<EcsValue>,
}

/// Stable compact fill kinds emitted by ECS execution reports.
///
/// The wire representation deliberately remains `u8` in
/// [`ExecutionCanvasFillRecord`] so existing Rust consumers can continue
/// constructing and reading records directly. Canvas-only line and GPU
/// procedural kinds do not belong to this protocol.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ExecutionCanvasFillKind {
    Rect = 1,
    Triangle = 2,
    Ellipse = 3,
}

impl ExecutionCanvasFillKind {
    pub const fn as_u8(self) -> u8 {
        self as u8
    }
}

impl TryFrom<u8> for ExecutionCanvasFillKind {
    type Error = u8;

    fn try_from(kind: u8) -> std::result::Result<Self, Self::Error> {
        match kind {
            1 => Ok(Self::Rect),
            2 => Ok(Self::Triangle),
            3 => Ok(Self::Ellipse),
            _ => Err(kind),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionCanvasFillRecord {
    pub kind: u8,
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub d: f64,
    pub e: f64,
    pub f: f64,
    pub r: u8,
    pub g: u8,
    pub blue: u8,
    pub alpha: u8,
}

impl ExecutionCanvasFillRecord {
    pub fn rect(x: f64, y: f64, width: f64, height: f64, color: [u8; 4]) -> Self {
        Self::rect_like(ExecutionCanvasFillKind::Rect, x, y, width, height, color)
    }

    pub fn ellipse_centered(
        center_x: f64,
        center_y: f64,
        width: f64,
        height: f64,
        color: [u8; 4],
    ) -> Self {
        Self::rect_like(
            ExecutionCanvasFillKind::Ellipse,
            center_x - width / 2.0,
            center_y - height / 2.0,
            width,
            height,
            color,
        )
    }

    pub fn triangle(
        first: (f64, f64),
        second: (f64, f64),
        third: (f64, f64),
        color: [u8; 4],
    ) -> Self {
        let [r, g, blue, alpha] = color;
        Self {
            kind: ExecutionCanvasFillKind::Triangle.as_u8(),
            a: first.0,
            b: first.1,
            c: second.0,
            d: second.1,
            e: third.0,
            f: third.1,
            r,
            g,
            blue,
            alpha,
        }
    }

    fn rect_like(
        kind: ExecutionCanvasFillKind,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        color: [u8; 4],
    ) -> Self {
        let [r, g, blue, alpha] = color;
        Self {
            kind: kind.as_u8(),
            a: x,
            b: y,
            c: width,
            d: height,
            e: 0.0,
            f: 0.0,
            r,
            g,
            blue,
            alpha,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionCanvasFillBatch {
    pub records: Vec<ExecutionCanvasFillRecord>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionReport {
    pub rows_scanned: usize,
    pub fields_written: usize,
    pub resource_fields_written: usize,
    pub events_emitted: usize,
    pub structural_commands: usize,
    pub duplicate_writes: usize,
    pub spatial_indexes_built: usize,
    pub spatial_candidate_rows: usize,
    pub spatial_exact_rows: usize,
    pub spatial_false_positive_rows: usize,
    pub spatial_deduplicated_pairs: usize,
    pub spatial_algorithm_hash_grid: usize,
    pub spatial_algorithm_quadtree: usize,
    pub spatial_algorithm_octree: usize,
    pub spatial_algorithm_hilbert_curve: usize,
    pub spatial_index_reuses: usize,
    pub spatial_index_full_rebuilds: usize,
    pub spatial_index_incremental_updates: usize,
    pub spatial_parallel_chunks: usize,
    pub spatial_parallel_workers: usize,
    pub spatial_thread_scratch_reuses: usize,
    pub spatial_candidate_buffer_growths: usize,
    pub writes: Vec<ExecutionWrite>,
    pub events: Vec<ExecutionEvent>,
    pub canvas_commands: Vec<ExecutionCanvasCommand>,
    pub canvas_fill_batches: Vec<ExecutionCanvasFillBatch>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compact_fill_kind_tags_are_stable_and_exclusive() {
        assert_eq!(ExecutionCanvasFillKind::Rect.as_u8(), 1);
        assert_eq!(ExecutionCanvasFillKind::Triangle.as_u8(), 2);
        assert_eq!(ExecutionCanvasFillKind::Ellipse.as_u8(), 3);
        assert_eq!(ExecutionCanvasFillKind::try_from(4), Err(4));
    }

    #[test]
    fn compact_fill_constructors_preserve_bounds_and_color_channels() {
        assert_eq!(
            ExecutionCanvasFillRecord::rect(1.0, 2.0, 3.0, 4.0, [10, 20, 30, 40]),
            ExecutionCanvasFillRecord {
                kind: 1,
                a: 1.0,
                b: 2.0,
                c: 3.0,
                d: 4.0,
                e: 0.0,
                f: 0.0,
                r: 10,
                g: 20,
                blue: 30,
                alpha: 40,
            }
        );
        assert_eq!(
            ExecutionCanvasFillRecord::ellipse_centered(10.0, 20.0, 6.0, 8.0, [1, 2, 3, 4]),
            ExecutionCanvasFillRecord {
                kind: 3,
                a: 7.0,
                b: 16.0,
                c: 6.0,
                d: 8.0,
                e: 0.0,
                f: 0.0,
                r: 1,
                g: 2,
                blue: 3,
                alpha: 4,
            }
        );
        assert_eq!(
            ExecutionCanvasFillRecord::triangle((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), [7, 8, 9, 10],),
            ExecutionCanvasFillRecord {
                kind: 2,
                a: 1.0,
                b: 2.0,
                c: 3.0,
                d: 4.0,
                e: 5.0,
                f: 6.0,
                r: 7,
                g: 8,
                blue: 9,
                alpha: 10,
            }
        );
    }
}
