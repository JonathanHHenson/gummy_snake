use std::collections::hash_map::DefaultHasher;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::sync::Arc;
use std::time::Instant;

use rayon::prelude::*;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::hilbert::HilbertIndex;
use crate::plan::{
    ActionNode, BridgePlanPayload, ExprNode, PhysicalPlan, PhysicalPlanHandle,
    SpatialBoundsExprNode, SpatialRelationNode,
};
use crate::scheduler::install_on_ecs_worker_pool;
use crate::schema::StorageType;
use crate::spatial::{
    Dimensions, HashGridIndex, SpatialAabb, SpatialIndexBackend, SpatialPoint, SpatialRecord,
};
use crate::tree_spatial::{OctreeIndex, QuadtreeIndex};
use crate::world::World;

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
}

#[derive(Debug, Clone, Default)]
struct EvalContext {
    bindings: HashMap<String, Entity>,
    loop_items: HashMap<usize, EcsValue>,
}

impl EvalContext {
    fn with_binding(&self, query: String, entity: Entity) -> Self {
        let mut next = self.clone();
        next.bindings.insert(query, entity);
        next
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum WriteKey {
    Component {
        entity: Entity,
        component: String,
        field: String,
    },
    Resource {
        resource: String,
        field: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum ExprCacheKey {
    Empty(usize),
    One(usize, usize, u64),
    Many(usize, Vec<(usize, u64)>),
}

const DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS: u64 = 1_000_000;
const DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS: usize = 262_144;
const DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER: usize = 2;
const DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING: i64 = 16;

#[derive(Debug, Clone)]
pub(crate) enum BuiltSpatialIndex {
    HashGrid(HashGridIndex),
    DirectPointHashGrid(DirectPointHashGrid),
    Quadtree(QuadtreeIndex),
    Octree(OctreeIndex),
    Hilbert(HilbertIndex),
}

#[derive(Debug, Clone)]
struct DirectPointRecord {
    entity: Entity,
    point: SpatialPoint,
}

#[derive(Debug, Clone)]
pub(crate) struct DirectPointHashGrid {
    dimensions: Dimensions,
    cell_size: f64,
    buckets: HashMap<[i64; 3], Vec<usize>>,
    dense_buckets: Option<DirectPointDenseBuckets>,
    regular_grid: Option<DirectPointRegularGrid>,
    records: Vec<DirectPointRecord>,
}

#[derive(Debug, Clone)]
struct DirectPointRegularGrid {
    x0: f64,
    y0: f64,
    dx: f64,
    dy: f64,
    width: usize,
    height: usize,
    cells: Vec<Option<usize>>,
}

#[derive(Debug, Clone)]
struct DirectPointDenseBuckets {
    min_cell: [i64; 3],
    spans: [usize; 3],
    buckets: Vec<Vec<usize>>,
}

impl DirectPointRegularGrid {
    fn new(records: &[DirectPointRecord]) -> Option<Self> {
        if records.len() < 8 {
            return None;
        }
        if records
            .iter()
            .any(|record| record.point.dimensions() != Dimensions::D2)
        {
            return None;
        }
        if records.len() >= 256 {
            let sample_len = records.len().min(512);
            let sample = &records[..sample_len];
            let sample_xs = sorted_unique_axis(sample, 0);
            let sample_ys = sorted_unique_axis(sample, 1);
            if sample_xs.len().saturating_mul(sample_ys.len())
                > sample_len.saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            {
                return None;
            }
        }
        let xs = sorted_unique_axis(records, 0);
        let ys = sorted_unique_axis(records, 1);
        let dx = regular_axis_spacing(&xs)?;
        let dy = regular_axis_spacing(&ys)?;
        let width = xs.len();
        let height = ys.len();
        let total = width.checked_mul(height)?;
        let dense_budget = records
            .len()
            .saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            .max(4096);
        if total > DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS || total > dense_budget {
            return None;
        }
        let x0 = xs[0];
        let y0 = ys[0];
        let x_tolerance = regular_grid_tolerance(dx);
        let y_tolerance = regular_grid_tolerance(dy);
        let mut cells = vec![None; total];
        for (record_index, record) in records.iter().enumerate() {
            let ix = regular_grid_axis_index(record.point.coord(0), x0, dx, width, x_tolerance)?;
            let iy = regular_grid_axis_index(record.point.coord(1), y0, dy, height, y_tolerance)?;
            let cell_index = iy.checked_mul(width)?.checked_add(ix)?;
            if cells[cell_index].replace(record_index).is_some() {
                return None;
            }
        }
        Some(Self {
            x0,
            y0,
            dx,
            dy,
            width,
            height,
            cells,
        })
    }

    fn visit_radius<F>(
        &self,
        records: &[DirectPointRecord],
        origin_x: f64,
        origin_y: f64,
        radius: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        let min_x = regular_grid_query_min(origin_x - radius, self.x0, self.dx);
        let max_x = regular_grid_query_max(origin_x + radius, self.x0, self.dx);
        let min_y = regular_grid_query_min(origin_y - radius, self.y0, self.dy);
        let max_y = regular_grid_query_max(origin_y + radius, self.y0, self.dy);
        let min_x = min_x.clamp(0, self.width.saturating_sub(1) as i64) as usize;
        let max_x = max_x.clamp(0, self.width.saturating_sub(1) as i64) as usize;
        let min_y = min_y.clamp(0, self.height.saturating_sub(1) as i64) as usize;
        let max_y = max_y.clamp(0, self.height.saturating_sub(1) as i64) as usize;
        if min_x > max_x || min_y > max_y {
            return Ok(());
        }
        for iy in min_y..=max_y {
            let row = iy * self.width;
            for ix in min_x..=max_x {
                let Some(record_index) = self.cells[row + ix] else {
                    continue;
                };
                let record = &records[record_index];
                let dx = record.point.coord(0) - origin_x;
                let dy = record.point.coord(1) - origin_y;
                let distance_sq = dx * dx + dy * dy;
                if distance_sq <= radius_sq {
                    visit(record_index, record, distance_sq)?;
                }
            }
        }
        Ok(())
    }
}

fn sorted_unique_axis(records: &[DirectPointRecord], axis: usize) -> Vec<f64> {
    let mut values = records
        .iter()
        .map(|record| record.point.coord(axis))
        .collect::<Vec<_>>();
    values.sort_by(f64::total_cmp);
    values.dedup_by(|left, right| *left == *right);
    values
}

fn regular_axis_spacing(values: &[f64]) -> Option<f64> {
    match values {
        [] => None,
        [_] => Some(1.0),
        [first, second, rest @ ..] => {
            let spacing = second - first;
            if !spacing.is_finite() || spacing <= 0.0 {
                return None;
            }
            let tolerance = regular_grid_tolerance(spacing);
            let mut previous = *second;
            for value in rest {
                let delta = *value - previous;
                if (delta - spacing).abs() > tolerance {
                    return None;
                }
                previous = *value;
            }
            Some(spacing)
        }
    }
}

fn regular_grid_tolerance(spacing: f64) -> f64 {
    spacing.abs().max(1.0) * 1.0e-9
}

fn regular_grid_axis_index(
    value: f64,
    origin: f64,
    spacing: f64,
    len: usize,
    tolerance: f64,
) -> Option<usize> {
    let index = ((value - origin) / spacing).round();
    if index < 0.0 || index > len.saturating_sub(1) as f64 {
        return None;
    }
    let expected = origin + index * spacing;
    if (expected - value).abs() > tolerance {
        return None;
    }
    Some(index as usize)
}

fn regular_grid_query_min(value: f64, origin: f64, spacing: f64) -> i64 {
    ((value - origin) / spacing - 1.0e-9).ceil() as i64
}

fn regular_grid_query_max(value: f64, origin: f64, spacing: f64) -> i64 {
    ((value - origin) / spacing + 1.0e-9).floor() as i64
}

impl DirectPointDenseBuckets {
    fn new(dimensions: Dimensions, cells: &[[i64; 3]]) -> Option<Self> {
        if cells.is_empty() {
            return None;
        }
        let axis_count = dimensions.len();
        let mut min_cell = [i64::MAX; 3];
        let mut max_cell = [i64::MIN; 3];
        for cell in cells {
            for axis in 0..axis_count {
                min_cell[axis] = min_cell[axis].min(cell[axis]);
                max_cell[axis] = max_cell[axis].max(cell[axis]);
            }
        }
        for axis in 0..axis_count {
            min_cell[axis] =
                min_cell[axis].saturating_sub(DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING);
            max_cell[axis] =
                max_cell[axis].saturating_add(DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING);
        }
        for axis in axis_count..3 {
            min_cell[axis] = 0;
            max_cell[axis] = 0;
        }
        let mut spans = [1_usize; 3];
        let mut total = 1_usize;
        for axis in 0..axis_count {
            let span = max_cell[axis]
                .checked_sub(min_cell[axis])
                .and_then(|value| value.checked_add(1))?;
            let span = usize::try_from(span).ok()?;
            spans[axis] = span;
            total = total.checked_mul(span)?;
        }
        let dense_budget = cells
            .len()
            .saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            .max(4096);
        if total > DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS || total > dense_budget {
            return None;
        }
        Some(Self {
            min_cell,
            spans,
            buckets: vec![Vec::new(); total],
        })
    }

    fn push(&mut self, cell: [i64; 3], record_index: usize) {
        if let Some(index) = self.bucket_index(cell) {
            self.buckets[index].push(record_index);
        }
    }

    fn try_push(&mut self, cell: [i64; 3], record_index: usize) -> bool {
        let Some(index) = self.bucket_index(cell) else {
            return false;
        };
        self.buckets[index].push(record_index);
        true
    }

    fn remove(&mut self, cell: [i64; 3], record_index: usize) -> bool {
        let Some(index) = self.bucket_index(cell) else {
            return false;
        };
        let Some(bucket) = self.buckets.get_mut(index) else {
            return false;
        };
        let Some(position) = bucket
            .iter()
            .position(|candidate| *candidate == record_index)
        else {
            return false;
        };
        bucket.swap_remove(position);
        true
    }

    fn bucket(&self, cell: [i64; 3]) -> Option<&[usize]> {
        self.bucket_index(cell)
            .and_then(|index| self.buckets.get(index).map(Vec::as_slice))
    }

    fn bucket_index(&self, cell: [i64; 3]) -> Option<usize> {
        let mut index = 0_usize;
        let mut stride = 1_usize;
        for axis in 0..3 {
            let relative = cell[axis].checked_sub(self.min_cell[axis])?;
            let relative = usize::try_from(relative).ok()?;
            if relative >= self.spans[axis] {
                return None;
            }
            index = index.checked_add(relative.checked_mul(stride)?)?;
            stride = stride.checked_mul(self.spans[axis])?;
        }
        Some(index)
    }
}

#[derive(Debug, Clone)]
pub(crate) struct CachedSpatialIndex {
    pub index: BuiltSpatialIndex,
    pub signature: String,
    pub structural_revision: u64,
    pub field_revision: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum NumericComparison {
    LessThan,
    LessThanOrEqual,
    GreaterThan,
    GreaterThanOrEqual,
}

#[derive(Debug, Clone, Copy)]
enum SpatialDistanceFilter {
    Distance {
        comparison: NumericComparison,
        threshold: f64,
    },
    DistanceSq {
        comparison: NumericComparison,
        threshold: f64,
    },
}

#[derive(Debug, Clone)]
enum SpatialBatchValue {
    Count,
    DirectField { component: String, field: String },
    NegDeltaOverDistance { axis: usize, minimum_distance: f64 },
}

#[derive(Debug, Clone)]
enum FastSpatialBatchValue {
    Count,
    DirectField { array_index: usize },
    DirectPointCoord { axis: usize },
    NegDeltaOverDistance { axis: usize, minimum_distance: f64 },
}

#[derive(Debug, Clone)]
struct SpatialBatchSpec {
    expr_index: usize,
    kind: String,
    value: SpatialBatchValue,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FastAggregateKind {
    Any,
    Count,
    Sum,
    Mean,
    Min,
    Max,
}

#[derive(Debug, Clone)]
struct FastSpatialBatchSpec {
    expr_index: usize,
    kind: FastAggregateKind,
    value: FastSpatialBatchValue,
}

#[derive(Debug, Clone)]
struct FastFieldArray {
    component: String,
    field: String,
    values: Vec<Option<(u32, f64)>>,
}

#[derive(Debug, Clone, Copy)]
struct SpatialBatchAccum {
    count: usize,
    sum: f64,
    min: f64,
    max: f64,
}

#[derive(Debug, Clone, Copy, Default)]
struct SpatialLocalCounters {
    candidate_rows: usize,
    exact_rows: usize,
    rows_scanned: usize,
    deduplicated_pairs: usize,
    candidate_buffer_growths: usize,
}

#[derive(Debug)]
struct SpatialChunkResult {
    row_start: usize,
    origins: Vec<Entity>,
    values: Vec<f64>,
    present: Option<Vec<bool>>,
    counters: SpatialLocalCounters,
}

#[derive(Debug)]
enum SpatialF64RowArray {
    Dense(Vec<f64>),
    Optional(Vec<Option<f64>>),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SpatialPrecomputeLayout {
    SparseEntity,
    QueryRows,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct F64WriteTarget {
    query: String,
    component: String,
    field: String,
}

#[derive(Clone, Debug, Default)]
struct QueryAccessSummary {
    component_reads: HashMap<String, Vec<String>>,
    component_writes: HashMap<String, Vec<String>>,
    resource_reads: HashSet<String>,
    resource_writes: HashSet<String>,
    event_reads: HashSet<String>,
    event_writes: HashSet<String>,
    hidden_reads: HashSet<String>,
    hidden_writes: HashSet<String>,
    structural: bool,
    f64_write_targets: Vec<F64WriteTarget>,
    copyback_eligible: bool,
}

#[derive(Debug, Clone)]
struct DirectF64SetSpec {
    query: String,
    component: String,
    field: String,
    value_expr: usize,
}

#[derive(Debug, Clone)]
struct RowLocalTarget {
    component: String,
    field: String,
}

#[derive(Debug, Clone)]
enum RowLocalAction {
    Noop,
    SetField {
        field_slot: usize,
        target_slot: usize,
        value_expr: usize,
    },
    Sequence(Vec<RowLocalAction>),
    When {
        condition_expr: usize,
        then_action: Box<RowLocalAction>,
        otherwise_action: Option<Box<RowLocalAction>>,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum F64UnaryOp {
    Neg,
    Not,
    Abs,
    Sqrt,
    Sin,
    Cos,
    Floor,
    Ceil,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum F64BinaryOp {
    Add,
    Sub,
    Mul,
    TrueDiv,
    FloorDiv,
    Mod,
    Pow,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    Min,
    Max,
    And,
    Or,
}

#[derive(Debug, Clone)]
enum CompiledF64Expr {
    Literal(f64),
    Field(usize),
    SpatialAggregate(usize),
    ResourceField {
        resource: String,
        field: String,
    },
    InputState {
        name: String,
        code: Option<i64>,
    },
    Unary {
        op: F64UnaryOp,
        input: usize,
    },
    Binary {
        op: F64BinaryOp,
        left: usize,
        right: usize,
    },
    Passthrough(usize),
    Unsupported(String),
}

struct CompiledF64ReadOnlyProgram<'a> {
    expressions: Vec<CompiledF64Expr>,
    aliases: Vec<usize>,
    initial_values: Vec<(usize, f64)>,
    field_arrays: Vec<CompiledF64Array<'a>>,
    field_slot_by_key: HashMap<(String, String), usize>,
    spatial_arrays: Vec<CompiledSpatialF64Array<'a>>,
}

#[derive(Clone, Copy)]
enum CompiledF64Array<'a> {
    SparseEntity(&'a [Option<(u32, f64)>]),
    QueryRows(&'a [f64]),
}

#[derive(Clone, Copy)]
enum CompiledSpatialF64Array<'a> {
    SparseEntity(&'a [Option<(u32, f64)>]),
    QueryRows(&'a [f64]),
    QueryRowsOptional(&'a [Option<f64>]),
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum CompiledF64ExprKey {
    Literal(u64),
    Field(usize),
    SpatialAggregate(usize),
    ResourceField(String, String),
    InputState(String, Option<i64>),
    Unary(F64UnaryOp, usize),
    Binary(F64BinaryOp, usize, usize),
    Passthrough(usize),
}

#[derive(Debug, Clone)]
struct DirectSpatialCoord {
    component: String,
    field: String,
}

#[derive(Debug, Clone)]
struct DirectSpatialRelationBatch {
    specs: Vec<SpatialBatchSpec>,
    distance_filter: Option<SpatialDistanceFilter>,
    query_radius: f64,
}

#[derive(Debug, Clone)]
struct FastDirectSpatialRelationBatch {
    specs: Vec<FastSpatialBatchSpec>,
    distance_filter: Option<SpatialDistanceFilter>,
    query_radius: f64,
    query_radius_sq: f64,
}

impl Default for SpatialBatchAccum {
    fn default() -> Self {
        Self {
            count: 0,
            sum: 0.0,
            min: f64::INFINITY,
            max: f64::NEG_INFINITY,
        }
    }
}

impl SpatialDistanceFilter {
    fn matches(self, distance_sq: f64) -> bool {
        match self {
            Self::Distance {
                comparison,
                threshold,
            } => compare_f64(distance_sq.sqrt(), comparison, threshold),
            Self::DistanceSq {
                comparison,
                threshold,
            } => compare_f64(distance_sq, comparison, threshold),
        }
    }

    fn upper_radius_bound(self) -> Option<f64> {
        match self {
            Self::Distance {
                comparison: NumericComparison::LessThan | NumericComparison::LessThanOrEqual,
                threshold,
            } if threshold.is_finite() && threshold >= 0.0 => Some(threshold),
            Self::DistanceSq {
                comparison: NumericComparison::LessThan | NumericComparison::LessThanOrEqual,
                threshold,
            } if threshold.is_finite() && threshold >= 0.0 => Some(threshold.sqrt()),
            _ => None,
        }
    }
}

fn compare_f64(left: f64, comparison: NumericComparison, right: f64) -> bool {
    match comparison {
        NumericComparison::LessThan => left < right,
        NumericComparison::LessThanOrEqual => left <= right,
        NumericComparison::GreaterThan => left > right,
        NumericComparison::GreaterThanOrEqual => left >= right,
    }
}

fn comparison_from_op(op: &str) -> Option<NumericComparison> {
    match op {
        "lt" | "<" => Some(NumericComparison::LessThan),
        "le" | "<=" => Some(NumericComparison::LessThanOrEqual),
        "gt" | ">" => Some(NumericComparison::GreaterThan),
        "ge" | ">=" => Some(NumericComparison::GreaterThanOrEqual),
        _ => None,
    }
}

fn reverse_comparison(comparison: NumericComparison) -> NumericComparison {
    match comparison {
        NumericComparison::LessThan => NumericComparison::GreaterThan,
        NumericComparison::LessThanOrEqual => NumericComparison::GreaterThanOrEqual,
        NumericComparison::GreaterThan => NumericComparison::LessThan,
        NumericComparison::GreaterThanOrEqual => NumericComparison::LessThanOrEqual,
    }
}

impl DirectPointHashGrid {
    fn new(dimensions: Dimensions, cell_size: f64) -> Result<Self> {
        if !cell_size.is_finite() || cell_size <= 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid cell_size must be finite and positive".to_string(),
            ));
        }
        Ok(Self {
            dimensions,
            cell_size,
            buckets: HashMap::new(),
            dense_buckets: None,
            regular_grid: None,
            records: Vec::new(),
        })
    }

    fn build_sorted_points(&mut self, records: Vec<DirectPointRecord>) -> Result<()> {
        self.buckets.clear();
        self.dense_buckets = None;
        self.regular_grid = None;
        let mut cells = Vec::with_capacity(records.len());
        for record in &records {
            if record.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid record dimensions do not match index dimensions".to_string(),
                ));
            }
            cells.push(self.cell(&record.point)?);
        }
        self.records = records;
        self.regular_grid = DirectPointRegularGrid::new(&self.records);
        if let Some(mut dense) = DirectPointDenseBuckets::new(self.dimensions, &cells) {
            for (index, cell) in cells.iter().enumerate() {
                dense.push(*cell, index);
            }
            self.dense_buckets = Some(dense);
            return Ok(());
        }
        self.build_sparse_buckets(cells);
        Ok(())
    }

    fn build_sparse_buckets(&mut self, cells: Vec<[i64; 3]>) {
        self.buckets.clear();
        for (index, cell) in cells.into_iter().enumerate() {
            self.buckets.entry(cell).or_default().push(index);
        }
    }

    fn build_from_spatial_records(&mut self, records: &[SpatialRecord]) -> Result<()> {
        if records.iter().any(|record| record.bounds.is_some()) {
            return Err(EcsError::InvalidSpatialInput(
                "direct point hash grid only supports point records".to_string(),
            ));
        }
        let mut direct = records
            .iter()
            .map(|record| DirectPointRecord {
                entity: record.entity,
                point: record.point.clone(),
            })
            .collect::<Vec<_>>();
        direct.sort_by_key(|record| record.entity.raw());
        self.build_sorted_points(direct)
    }

    fn update_sorted_points(&mut self, records: &[DirectPointRecord]) -> Result<bool> {
        if records.len() != self.records.len() || self.regular_grid.is_some() {
            self.build_sorted_points(records.to_vec())?;
            return Ok(false);
        }
        for (index, next) in records.iter().enumerate() {
            if self.records[index].entity != next.entity {
                self.build_sorted_points(records.to_vec())?;
                return Ok(false);
            }
            if next.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid record dimensions do not match index dimensions".to_string(),
                ));
            }
            let old_cell = self.cell(&self.records[index].point)?;
            let new_cell = self.cell(&next.point)?;
            if old_cell != new_cell {
                if let Some(dense) = &mut self.dense_buckets {
                    if !dense.remove(old_cell, index) || !dense.try_push(new_cell, index) {
                        self.build_sorted_points(records.to_vec())?;
                        return Ok(false);
                    }
                } else {
                    if let Some(bucket) = self.buckets.get_mut(&old_cell) {
                        if let Some(position) =
                            bucket.iter().position(|candidate| *candidate == index)
                        {
                            bucket.swap_remove(position);
                        }
                        if bucket.is_empty() {
                            self.buckets.remove(&old_cell);
                        }
                    }
                    self.buckets.entry(new_cell).or_default().push(index);
                }
            }
            self.records[index] = next.clone();
        }
        Ok(true)
    }

    fn cell(&self, point: &SpatialPoint) -> Result<[i64; 3]> {
        if point.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid point dimensions do not match index dimensions".to_string(),
            ));
        }
        self.cell_from_coords([point.coord(0), point.coord(1), point.coord(2)])
    }

    fn cell_from_coords(&self, coords: [f64; 3]) -> Result<[i64; 3]> {
        let mut cell = [0_i64; 3];
        for (axis, slot) in cell.iter_mut().enumerate().take(self.dimensions.len()) {
            let value = (coords[axis] / self.cell_size).floor();
            if value < i64::MIN as f64 || value > i64::MAX as f64 {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid cell coordinate overflow".to_string(),
                ));
            }
            *slot = value as i64;
        }
        Ok(cell)
    }

    fn visit_radius_unordered<F>(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        mut visit: F,
    ) -> Result<()>
    where
        F: FnMut(&DirectPointRecord, f64) -> Result<()>,
    {
        self.visit_radius_unordered_indexed(origin, radius, |_, record, distance_sq| {
            visit(record, distance_sq)
        })
    }

    fn visit_radius_unordered_indexed<F>(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        mut visit: F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        if origin.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "query point dimensions do not match index dimensions".to_string(),
            ));
        }
        if !radius.is_finite() || radius < 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "query radius must be finite and non-negative".to_string(),
            ));
        }
        let origin_x = origin.coord(0);
        let origin_y = origin.coord(1);
        let origin_z = if self.dimensions == Dimensions::D3 {
            origin.coord(2)
        } else {
            0.0
        };
        let radius_sq = radius * radius;
        if self.dimensions == Dimensions::D2 {
            if let Some(regular_grid) = &self.regular_grid {
                return regular_grid.visit_radius(
                    &self.records,
                    origin_x,
                    origin_y,
                    radius,
                    radius_sq,
                    &mut visit,
                );
            }
        }
        let min_cell = self.cell_from_coords([
            origin_x - radius,
            origin_y - radius,
            if self.dimensions == Dimensions::D3 {
                origin_z - radius
            } else {
                0.0
            },
        ])?;
        let max_cell = self.cell_from_coords([
            origin_x + radius,
            origin_y + radius,
            if self.dimensions == Dimensions::D3 {
                origin_z + radius
            } else {
                0.0
            },
        ])?;
        validate_direct_point_cell_span(self.dimensions, min_cell, max_cell)?;
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    let cell = [x, y, 0];
                    if let Some(bucket) = self.direct_bucket(cell) {
                        self.visit_radius_bucket_2d(
                            bucket, origin_x, origin_y, radius_sq, &mut visit,
                        )?;
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        let cell = [x, y, z];
                        if let Some(bucket) = self.direct_bucket(cell) {
                            self.visit_radius_bucket_3d(
                                bucket, origin_x, origin_y, origin_z, radius_sq, &mut visit,
                            )?;
                        }
                    }
                }
            }
        }
        Ok(())
    }

    fn direct_bucket(&self, cell: [i64; 3]) -> Option<&[usize]> {
        if let Some(dense) = &self.dense_buckets {
            return dense.bucket(cell);
        }
        self.buckets.get(&cell).map(Vec::as_slice)
    }

    fn visit_radius_bucket_2d<F>(
        &self,
        bucket: &[usize],
        origin_x: f64,
        origin_y: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for record_index in bucket {
            let record = &self.records[*record_index];
            let dx = record.point.coord(0) - origin_x;
            let dy = record.point.coord(1) - origin_y;
            let distance_sq = dx * dx + dy * dy;
            if distance_sq <= radius_sq {
                visit(*record_index, record, distance_sq)?;
            }
        }
        Ok(())
    }

    fn visit_radius_bucket_3d<F>(
        &self,
        bucket: &[usize],
        origin_x: f64,
        origin_y: f64,
        origin_z: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for record_index in bucket {
            let record = &self.records[*record_index];
            let dx = record.point.coord(0) - origin_x;
            let dy = record.point.coord(1) - origin_y;
            let dz = record.point.coord(2) - origin_z;
            let distance_sq = dx * dx + dy * dy + dz * dz;
            if distance_sq <= radius_sq {
                visit(*record_index, record, distance_sq)?;
            }
        }
        Ok(())
    }

    fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        out.clear();
        self.visit_radius_unordered(origin, radius, |record, _| {
            out.push(SpatialRecord {
                entity: record.entity,
                point: record.point.clone(),
                bounds: None,
            });
            Ok(())
        })
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "query bounds dimensions do not match index dimensions".to_string(),
            ));
        }
        out.clear();
        let min_cell = self.cell(bounds.minimum())?;
        let max_cell = self.cell(bounds.maximum())?;
        validate_direct_point_cell_span(self.dimensions, min_cell, max_cell)?;
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    if let Some(bucket) = self.direct_bucket([x, y, 0]) {
                        self.push_aabb_matches(bucket, bounds, out);
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        if let Some(bucket) = self.direct_bucket([x, y, z]) {
                            self.push_aabb_matches(bucket, bounds, out);
                        }
                    }
                }
            }
        }
        Ok(())
    }

    fn push_aabb_matches(
        &self,
        bucket: &[usize],
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) {
        for index in bucket {
            let record = &self.records[*index];
            let inside = (0..self.dimensions.len()).all(|axis| {
                let coord = record.point.coord(axis);
                bounds.minimum().coord(axis) <= coord && coord <= bounds.maximum().coord(axis)
            });
            if inside {
                out.push(SpatialRecord {
                    entity: record.entity,
                    point: record.point.clone(),
                    bounds: None,
                });
            }
        }
    }
}

fn validate_direct_point_cell_span(
    dimensions: Dimensions,
    min_cell: [i64; 3],
    max_cell: [i64; 3],
) -> Result<()> {
    let mut total = 1_u64;
    for axis in 0..dimensions.len() {
        let span = max_cell[axis]
            .checked_sub(min_cell[axis])
            .and_then(|value| value.checked_add(1))
            .ok_or_else(|| {
                EcsError::InvalidSpatialInput("hash grid cell span overflow".to_string())
            })?;
        let span = u64::try_from(span).map_err(|_| {
            EcsError::InvalidSpatialInput("hash grid cell span must be non-negative".to_string())
        })?;
        total = total.checked_mul(span).ok_or_else(|| {
            EcsError::InvalidSpatialInput("hash grid cell span overflow".to_string())
        })?;
        if total > DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS {
            return Err(EcsError::InvalidSpatialInput(format!(
                "hash grid query spans {total} cells; maximum is {DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS}"
            )));
        }
    }
    Ok(())
}

impl BuiltSpatialIndex {
    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.build(records),
            Self::DirectPointHashGrid(index) => index.build_from_spatial_records(records),
            Self::Quadtree(index) => index.build(records),
            Self::Octree(index) => index.build(records),
            Self::Hilbert(index) => index.build(records),
        }
    }

    fn update_incremental(&mut self, records: &[SpatialRecord]) -> Result<bool> {
        match self {
            Self::HashGrid(index) => index.update_incremental(records),
            Self::DirectPointHashGrid(index) => {
                index.build_from_spatial_records(records)?;
                Ok(false)
            }
            Self::Quadtree(index) => index.update_incremental(records),
            Self::Octree(index) => index.update_incremental(records),
            Self::Hilbert(index) => index.update_incremental(records),
        }
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_radius(origin, radius, out),
            Self::DirectPointHashGrid(index) => index.query_radius_unordered(origin, radius, out),
            Self::Quadtree(index) => index.query_radius(origin, radius, out),
            Self::Octree(index) => index.query_radius(origin, radius, out),
            Self::Hilbert(index) => index.query_radius(origin, radius, out),
        }
    }

    fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_radius_unordered(origin, radius, out),
            Self::DirectPointHashGrid(index) => index.query_radius_unordered(origin, radius, out),
            Self::Quadtree(index) => index.query_radius_unordered(origin, radius, out),
            Self::Octree(index) => index.query_radius_unordered(origin, radius, out),
            _ => self.query_radius(origin, radius, out),
        }
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_aabb(bounds, out),
            Self::DirectPointHashGrid(index) => index.query_aabb(bounds, out),
            Self::Quadtree(index) => index.query_aabb(bounds, out),
            Self::Octree(index) => index.query_aabb(bounds, out),
            Self::Hilbert(index) => index.query_aabb(bounds, out),
        }
    }
}

struct PlanExecutor<'a> {
    world: &'a mut World,
    plan: &'a PhysicalPlan,
    query_rows: HashMap<String, Vec<Entity>>,
    query_indices: HashMap<String, usize>,
    query_location_cache: HashMap<String, Vec<(usize, usize)>>,
    report: ExecutionReport,
    report_writes: bool,
    spatial_indexes: HashMap<String, BuiltSpatialIndex>,
    spatial_index_metadata: HashMap<String, (String, u64, u64)>,
    spatial_relation_cache:
        HashMap<(String, Option<usize>, Option<usize>, bool, String, u64), Arc<Vec<SpatialRecord>>>,
    expr_cache: HashMap<ExprCacheKey, EcsValue>,
    local_expr_cache: Option<Vec<Option<EcsValue>>>,
    local_expr_bindings: Option<HashMap<String, Entity>>,
    numeric_field_cache_enabled: bool,
    numeric_field_cache: HashMap<String, HashMap<String, Vec<Option<(u32, f64)>>>>,
    numeric_field_cache_rows: HashMap<String, HashMap<String, Vec<f64>>>,
    spatial_batch_spec_cache:
        HashMap<(String, Option<usize>, Option<usize>), Vec<SpatialBatchSpec>>,
    spatial_precomputed_f64: HashMap<usize, Vec<Option<(u32, f64)>>>,
    spatial_precomputed_f64_rows: HashMap<usize, SpatialF64RowArray>,
    profile: bool,
    profile_eval_calls: usize,
    profile_expr_cache_hits: usize,
    profile_expr_cache_misses: usize,
    profile_spatial_relation_hits: usize,
    profile_spatial_relation_misses: usize,
    profile_spatial_index_nanos: u128,
    profile_spatial_query_nanos: u128,
    profile_spatial_filter_nanos: u128,
    profile_direct_aggregate_nanos: u128,
    profile_direct_aggregate_hits: usize,
}

impl World {
    pub fn execute_bridge_plan(&mut self, payload: BridgePlanPayload) -> Result<ExecutionReport> {
        let plan = self.compile_bridge_plan(payload)?;
        self.execute_plan(&plan)
    }

    pub fn execute_compiled_plan(&mut self, handle: PhysicalPlanHandle) -> Result<ExecutionReport> {
        self.execute_compiled_plan_with_options(handle, true)
    }

    pub fn execute_compiled_plan_with_options(
        &mut self,
        handle: PhysicalPlanHandle,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let plan = self.validated_compiled_plan(handle)?;
        self.execute_plan_with_options(plan.as_ref(), include_writes)
    }

    pub fn execute_compiled_plans_with_options(
        &mut self,
        handles: &[PhysicalPlanHandle],
        include_writes: bool,
    ) -> Result<Vec<ExecutionReport>> {
        if handles.is_empty() {
            return Ok(Vec::new());
        }
        if include_writes || handles.len() == 1 {
            return handles
                .iter()
                .map(|handle| self.execute_compiled_plan_with_options(*handle, include_writes))
                .collect();
        }
        let plans = handles
            .iter()
            .map(|handle| self.validated_compiled_plan(*handle))
            .collect::<Result<Vec<_>>>()?;
        let access = plans
            .iter()
            .map(|plan| self.query_access_summary(plan.as_ref()))
            .collect::<Result<Vec<_>>>()?;
        let mut query_sets: HashMap<(usize, String), HashSet<u64>> = HashMap::new();
        for (plan_index, plan) in plans.iter().enumerate() {
            for query in &plan.queries {
                let rows = query_rows_for_world(self, plan.as_ref(), &query.name)?;
                query_sets.insert(
                    (plan_index, query.name.clone()),
                    rows.into_iter().map(|entity| entity.raw()).collect(),
                );
            }
        }

        let mut waves: Vec<Vec<usize>> = Vec::new();
        let mut current = Vec::new();
        for plan_index in 0..plans.len() {
            if !access[plan_index].copyback_eligible {
                if !current.is_empty() {
                    waves.push(std::mem::take(&mut current));
                }
                waves.push(vec![plan_index]);
                continue;
            }
            let conflicts = current.iter().any(|other| {
                query_access_conflicts(
                    &access[*other],
                    *other,
                    &access[plan_index],
                    plan_index,
                    &query_sets,
                )
            });
            if conflicts {
                if !current.is_empty() {
                    waves.push(std::mem::take(&mut current));
                }
            }
            current.push(plan_index);
        }
        if !current.is_empty() {
            waves.push(current);
        }

        let mut reports_by_index: Vec<Option<ExecutionReport>> = vec![None; plans.len()];
        for wave in waves {
            if wave.len() == 1 {
                let plan_index = wave[0];
                let report = self.execute_plan_with_options(plans[plan_index].as_ref(), false)?;
                reports_by_index[plan_index] = Some(report);
                continue;
            }
            let snapshot = self.clone();
            let wave_results = install_on_ecs_worker_pool(|| {
                wave.par_iter()
                    .map(|plan_index| {
                        let mut child = snapshot.clone();
                        let report = child
                            .execute_plan_with_options_inner(plans[*plan_index].as_ref(), false)?;
                        Ok((*plan_index, child, report))
                    })
                    .collect::<Result<Vec<_>>>()
            })?;
            let mut wave_results = wave_results;
            wave_results.sort_by_key(|(plan_index, _, _)| *plan_index);
            for (plan_index, child, report) in wave_results {
                self.copy_f64_write_targets_from(
                    &child,
                    plans[plan_index].as_ref(),
                    &access[plan_index],
                )?;
                reports_by_index[plan_index] = Some(report);
            }
        }
        reports_by_index
            .into_iter()
            .map(|report| {
                report.ok_or_else(|| {
                    EcsError::InvalidSchedule(
                        "compiled ECS batch did not produce one report per plan".to_string(),
                    )
                })
            })
            .collect()
    }

    fn validated_compiled_plan(
        &self,
        handle: PhysicalPlanHandle,
    ) -> Result<std::sync::Arc<PhysicalPlan>> {
        let plan = self.compiled_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if plan.schema_fingerprint != current_schema_fingerprint {
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {}, \
                 but the world schema fingerprint is {}; recompile the plan",
                plan.schema_fingerprint, current_schema_fingerprint
            )));
        }
        Ok(plan)
    }

    fn query_access_summary(&self, plan: &PhysicalPlan) -> Result<QueryAccessSummary> {
        let mut access = QueryAccessSummary {
            copyback_eligible: true,
            ..QueryAccessSummary::default()
        };
        collect_action_query_access(self, plan, plan.root_action, &mut access)?;
        if access.structural
            || !access.resource_writes.is_empty()
            || !access.event_writes.is_empty()
            || !access.hidden_writes.is_empty()
        {
            access.copyback_eligible = false;
        }
        if access.f64_write_targets.is_empty() {
            access.copyback_eligible = false;
        }
        Ok(access)
    }

    fn copy_f64_write_targets_from(
        &mut self,
        source: &World,
        plan: &PhysicalPlan,
        access: &QueryAccessSummary,
    ) -> Result<()> {
        let mut seen = HashSet::new();
        for target in &access.f64_write_targets {
            if !seen.insert(target.clone()) {
                continue;
            }
            let entities = query_rows_for_world(self, plan, &target.query)?;
            if entities.is_empty() {
                continue;
            }
            let locations = self.locations_for_entities(entities.iter().copied())?;
            let mut values = Vec::with_capacity(entities.len());
            for entity in &entities {
                values.push(source.get_field_f64(*entity, &target.component, &target.field)?);
            }
            self.set_field_f64_resolved_strided(
                &target.component,
                &target.field,
                &locations,
                &values,
                0,
                1,
            )?;
        }
        Ok(())
    }

    pub fn warm_compiled_plan_spatial_indexes(
        &mut self,
        handle: PhysicalPlanHandle,
    ) -> Result<ExecutionReport> {
        let plan = self.compiled_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if plan.schema_fingerprint != current_schema_fingerprint {
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {}, \
                 but the world schema fingerprint is {}; recompile the plan",
                plan.schema_fingerprint, current_schema_fingerprint
            )));
        }
        self.warm_plan_spatial_indexes(plan.as_ref())
    }

    pub fn execute_plan(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        self.execute_plan_with_options(plan, true)
    }

    pub fn execute_plan_with_options(
        &mut self,
        plan: &PhysicalPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| self.execute_plan_with_options_inner(plan, include_writes))
    }

    pub fn warm_plan_spatial_indexes(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| self.warm_plan_spatial_indexes_inner(plan))
    }

    fn warm_plan_spatial_indexes_inner(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        let mut query_rows = HashMap::new();
        let mut query_indices = HashMap::new();
        for (query_index, query) in plan.queries.iter().enumerate() {
            query_indices.insert(query.name.clone(), query_index);
            let mut rows = self.query_filter(query.filter.clone())?;
            if let Some(allowed) = &query.allowed_entities {
                let allowed = allowed
                    .iter()
                    .map(|entity| entity.raw())
                    .collect::<HashSet<_>>();
                rows.retain(|entity| allowed.contains(&entity.raw()));
            }
            query_rows.insert(query.name.clone(), rows);
        }
        let mut executor = PlanExecutor {
            world: self,
            plan,
            query_rows,
            query_indices,
            query_location_cache: HashMap::new(),
            report: ExecutionReport::default(),
            report_writes: false,
            spatial_indexes: HashMap::new(),
            spatial_index_metadata: HashMap::new(),
            spatial_relation_cache: HashMap::new(),
            expr_cache: HashMap::new(),
            local_expr_cache: None,
            local_expr_bindings: None,
            numeric_field_cache_enabled: false,
            numeric_field_cache: HashMap::new(),
            numeric_field_cache_rows: HashMap::new(),
            spatial_batch_spec_cache: HashMap::new(),
            spatial_precomputed_f64: HashMap::new(),
            spatial_precomputed_f64_rows: HashMap::new(),
            profile: false,
            profile_eval_calls: 0,
            profile_expr_cache_hits: 0,
            profile_expr_cache_misses: 0,
            profile_spatial_relation_hits: 0,
            profile_spatial_relation_misses: 0,
            profile_spatial_index_nanos: 0,
            profile_spatial_query_nanos: 0,
            profile_spatial_filter_nanos: 0,
            profile_direct_aggregate_nanos: 0,
            profile_direct_aggregate_hits: 0,
        };
        let query_names = executor.query_rows.keys().cloned().collect::<Vec<_>>();
        for query_name in query_names {
            executor.precompute_direct_spatial_aggregates_for_query(
                &query_name,
                SpatialPrecomputeLayout::SparseEntity,
            )?;
        }
        executor.persist_spatial_index_cache();
        Ok(std::mem::take(&mut executor.report))
    }

    fn execute_plan_with_options_inner(
        &mut self,
        plan: &PhysicalPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let profile = std::env::var_os("GUMMY_ECS_PROFILE").is_some();
        let total_start = profile.then(Instant::now);
        let query_start = profile.then(Instant::now);
        let mut query_rows = HashMap::new();
        let mut query_indices = HashMap::new();
        for (query_index, query) in plan.queries.iter().enumerate() {
            query_indices.insert(query.name.clone(), query_index);
            let mut rows = self.query_filter(query.filter.clone())?;
            if let Some(allowed) = &query.allowed_entities {
                let allowed = allowed
                    .iter()
                    .map(|entity| entity.raw())
                    .collect::<HashSet<_>>();
                rows.retain(|entity| allowed.contains(&entity.raw()));
            }
            query_rows.insert(query.name.clone(), rows);
        }
        if let Some(start) = query_start {
            eprintln!(
                "ecs_profile execute_query_prep elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let mut executor = PlanExecutor {
            world: self,
            plan,
            query_rows,
            query_indices,
            query_location_cache: HashMap::new(),
            report: ExecutionReport::default(),
            report_writes: include_writes,
            spatial_indexes: HashMap::new(),
            spatial_index_metadata: HashMap::new(),
            spatial_relation_cache: HashMap::new(),
            expr_cache: HashMap::new(),
            local_expr_cache: None,
            local_expr_bindings: None,
            numeric_field_cache_enabled: false,
            numeric_field_cache: HashMap::new(),
            numeric_field_cache_rows: HashMap::new(),
            spatial_batch_spec_cache: HashMap::new(),
            spatial_precomputed_f64: HashMap::new(),
            spatial_precomputed_f64_rows: HashMap::new(),
            profile,
            profile_eval_calls: 0,
            profile_expr_cache_hits: 0,
            profile_expr_cache_misses: 0,
            profile_spatial_relation_hits: 0,
            profile_spatial_relation_misses: 0,
            profile_spatial_index_nanos: 0,
            profile_spatial_query_nanos: 0,
            profile_spatial_filter_nanos: 0,
            profile_direct_aggregate_nanos: 0,
            profile_direct_aggregate_hits: 0,
        };
        let execute_result = executor.execute_action(plan.root_action, &[EvalContext::default()]);
        executor.persist_spatial_index_cache();
        execute_result?;
        if let Some(start) = total_start {
            eprintln!(
                "ecs_profile execute_total elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(executor.report)
    }

    pub fn storage_type_for_field(&self, component: &str, field: &str) -> Result<StorageType> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        schema
            .fields
            .iter()
            .find(|candidate| candidate.name == field)
            .map(|candidate| candidate.storage_type)
            .ok_or_else(|| EcsError::UnknownField {
                component: component.to_string(),
                field: field.to_string(),
            })
    }

    pub fn coerce_value_for_component_field(
        &self,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<EcsValue> {
        let storage_type = self.storage_type_for_field(component, field)?;
        coerce_value_for_storage(storage_type, value)
    }

    pub fn coerce_component_row(
        &self,
        component: &str,
        row: HashMap<String, EcsValue>,
    ) -> Result<HashMap<String, EcsValue>> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        let mut coerced = HashMap::with_capacity(row.len());
        for field in &schema.fields {
            let value = row
                .get(&field.name)
                .cloned()
                .ok_or_else(|| EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.name.clone(),
                })?;
            coerced.insert(
                field.name.clone(),
                coerce_value_for_storage(field.storage_type, value)?,
            );
        }
        for field in row.keys() {
            if !schema
                .fields
                .iter()
                .any(|candidate| &candidate.name == field)
            {
                return Err(EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.clone(),
                });
            }
        }
        Ok(coerced)
    }
}

impl<'a> PlanExecutor<'a> {
    fn execute_action(&mut self, action_index: usize, contexts: &[EvalContext]) -> Result<()> {
        if !self.report_writes {
            if let Some(query_name) = self.row_local_numeric_action_query(action_index, contexts) {
                return self.execute_row_local_numeric_action(action_index, &query_name);
            }
        }

        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(()),
            ActionNode::Sequence(children) => {
                for child in children {
                    self.expr_cache.clear();
                    self.numeric_field_cache.clear();
                    self.numeric_field_cache_rows.clear();
                    self.persist_spatial_index_cache();
                    self.spatial_relation_cache.clear();
                    self.execute_action(*child, contexts)?;
                }
                Ok(())
            }
            ActionNode::Parallel(children) => self.execute_parallel(children, contexts),
            ActionNode::SetField { target, value } => self.execute_set(*target, *value, contexts),
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => self.execute_when(*condition, *then_action, *otherwise_action, contexts),
            ActionNode::ForEach {
                source,
                item_slot,
                action,
            } => self.execute_for_each(*source, *item_slot, *action, contexts),
            ActionNode::EmitEvent { event_type, value } => {
                for ctx in contexts {
                    let payload = self.eval_expr(*value, ctx)?;
                    self.world.emit_event(event_type, payload.clone())?;
                    self.report.events_emitted += 1;
                    self.report.events.push(ExecutionEvent {
                        event_type: event_type.clone(),
                        payload,
                    });
                }
                Ok(())
            }
            ActionNode::AddComponent {
                query,
                component,
                value,
            } => self.execute_add_component(query, component, *value, contexts),
            ActionNode::RemoveComponent { query, component } => {
                self.execute_remove_component(query, component, contexts)
            }
            ActionNode::AddTag { query, tag } => self.execute_add_tag(query, tag, contexts),
            ActionNode::RemoveTag { query, tag } => self.execute_remove_tag(query, tag, contexts),
            ActionNode::Despawn { query } => self.execute_despawn(query, contexts),
            ActionNode::Udf { descriptor, .. } => Err(EcsError::InvalidPlan(format!(
                "physical execution cannot call Python UDF '{descriptor}'"
            ))),
        }
    }

    fn structural_contexts(
        &self,
        query: &str,
        contexts: &[EvalContext],
    ) -> Result<Vec<EvalContext>> {
        let mut queries = BTreeSet::new();
        queries.insert(query.to_string());
        let mut out = Vec::new();
        for ctx in contexts {
            out.extend(self.expand_context_for_queries(ctx, &queries)?);
        }
        Ok(out)
    }

    fn execute_add_component(
        &mut self,
        query: &str,
        component: &str,
        value: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for add_component"))
            })?;
            let value = value.map(|expr| self.eval_expr(expr, &ctx)).transpose()?;
            self.world
                .add_component_default(entity, component.to_string())?;
            if let Some(EcsValue::Struct(fields)) = value {
                for (field, field_value) in fields {
                    self.world
                        .set_field(entity, component, &field, field_value)?;
                }
            }
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_remove_component(
        &mut self,
        query: &str,
        component: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for remove_component"))
            })?;
            self.world.remove_component(entity, component)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_add_tag(&mut self, query: &str, tag: &str, contexts: &[EvalContext]) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for add_tag"))
            })?;
            self.world.add_tag(entity, tag)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_remove_tag(
        &mut self,
        query: &str,
        tag: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for remove_tag"))
            })?;
            self.world.remove_tag(entity, tag)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_despawn(&mut self, query: &str, contexts: &[EvalContext]) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for despawn"))
            })?;
            self.world.despawn(entity)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_for_each(
        &mut self,
        source: usize,
        item_slot: usize,
        action: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in contexts {
            let value = self.eval_expr(source, ctx)?;
            let items = match value {
                EcsValue::List(values) => values,
                other => {
                    return Err(EcsError::InvalidPlan(format!(
                        "for_each source must evaluate to a list, got {}",
                        other.kind_name()
                    )))
                }
            };
            for item in items {
                let mut loop_ctx = ctx.clone();
                loop_ctx.loop_items.insert(item_slot, item);
                self.execute_action(action, &[loop_ctx])?;
            }
        }
        Ok(())
    }

    fn execute_parallel(&mut self, children: &[usize], contexts: &[EvalContext]) -> Result<()> {
        if children
            .iter()
            .all(|child| matches!(self.plan.actions[*child], ActionNode::SetField { .. }))
        {
            return self.execute_parallel_set_fields(children, contexts);
        }

        let snapshot = self.world.clone();
        let mut targets_seen = HashSet::new();
        let mut shared_spatial_indexes = HashMap::new();
        let mut shared_spatial_index_metadata = HashMap::new();
        let mut shared_spatial_relation_cache = HashMap::new();
        let mut shared_expr_cache = HashMap::new();
        for child in children {
            let share_expr_cache_after_child = matches!(
                self.plan.actions[*child],
                ActionNode::SetField { .. } | ActionNode::When { .. }
            );
            let mut child_world = snapshot.clone();
            let mut child_executor = PlanExecutor {
                world: &mut child_world,
                plan: self.plan,
                query_rows: self.query_rows.clone(),
                query_indices: self.query_indices.clone(),
                query_location_cache: self.query_location_cache.clone(),
                report: ExecutionReport::default(),
                report_writes: true,
                spatial_indexes: shared_spatial_indexes,
                spatial_index_metadata: shared_spatial_index_metadata,
                spatial_relation_cache: shared_spatial_relation_cache,
                expr_cache: shared_expr_cache,
                local_expr_cache: None,
                local_expr_bindings: None,
                numeric_field_cache_enabled: false,
                numeric_field_cache: HashMap::new(),
                numeric_field_cache_rows: HashMap::new(),
                spatial_batch_spec_cache: HashMap::new(),
                spatial_precomputed_f64: HashMap::new(),
                spatial_precomputed_f64_rows: HashMap::new(),
                profile: self.profile,
                profile_eval_calls: 0,
                profile_expr_cache_hits: 0,
                profile_expr_cache_misses: 0,
                profile_spatial_relation_hits: 0,
                profile_spatial_relation_misses: 0,
                profile_spatial_index_nanos: 0,
                profile_spatial_query_nanos: 0,
                profile_spatial_filter_nanos: 0,
                profile_direct_aggregate_nanos: 0,
                profile_direct_aggregate_hits: 0,
            };
            child_executor.execute_action(*child, contexts)?;
            shared_spatial_indexes = child_executor.spatial_indexes;
            shared_spatial_index_metadata = child_executor.spatial_index_metadata;
            shared_spatial_relation_cache = child_executor.spatial_relation_cache;
            shared_expr_cache = if share_expr_cache_after_child {
                child_executor.expr_cache
            } else {
                HashMap::new()
            };
            self.merge_parallel_report(child_executor.report, &mut targets_seen)?;
        }
        self.spatial_indexes.extend(shared_spatial_indexes);
        self.spatial_index_metadata
            .extend(shared_spatial_index_metadata);
        Ok(())
    }

    fn execute_parallel_set_fields(
        &mut self,
        children: &[usize],
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut specs = Vec::with_capacity(children.len());
        let mut expr_query_cache = HashMap::new();
        for child in children {
            let ActionNode::SetField { target, value } = self.plan.actions[*child] else {
                unreachable!("parallel set fast path only receives set actions");
            };
            let mut query_names = self.expr_queries_cached(value, &mut expr_query_cache)?;
            match &self.plan.expressions[target] {
                ExprNode::Field { query, .. } => {
                    query_names.insert(query.clone());
                }
                ExprNode::ResourceField { .. } => {}
                other => {
                    return Err(EcsError::InvalidPlan(format!(
                        "set target must be a field or resource field, got {other:?}"
                    )))
                }
            }
            specs.push((*child, target, value, query_names));
        }

        let can_fuse = specs
            .first()
            .map(|(_, _, _, first_queries)| {
                specs
                    .iter()
                    .all(|(_, _, _, query_names)| query_names == first_queries)
            })
            .unwrap_or(true);

        let query_rows = self.query_rows.clone();
        let query_indices = self.query_indices.clone();
        let collector_report;
        let collector_spatial_indexes;
        let collector_spatial_index_metadata;
        {
            let profile = self.profile;
            let parallel_start = profile.then(Instant::now);
            let mut collector = PlanExecutor {
                world: &mut *self.world,
                plan: self.plan,
                query_rows,
                query_indices,
                query_location_cache: HashMap::new(),
                report: ExecutionReport::default(),
                report_writes: self.report_writes,
                spatial_indexes: HashMap::new(),
                spatial_index_metadata: HashMap::new(),
                spatial_relation_cache: HashMap::new(),
                expr_cache: HashMap::new(),
                local_expr_cache: None,
                local_expr_bindings: None,
                numeric_field_cache_enabled: true,
                numeric_field_cache: HashMap::new(),
                numeric_field_cache_rows: HashMap::new(),
                spatial_batch_spec_cache: HashMap::new(),
                spatial_precomputed_f64: HashMap::new(),
                spatial_precomputed_f64_rows: HashMap::new(),
                profile,
                profile_eval_calls: 0,
                profile_expr_cache_hits: 0,
                profile_expr_cache_misses: 0,
                profile_spatial_relation_hits: 0,
                profile_spatial_relation_misses: 0,
                profile_spatial_index_nanos: 0,
                profile_spatial_query_nanos: 0,
                profile_spatial_filter_nanos: 0,
                profile_direct_aggregate_nanos: 0,
                profile_direct_aggregate_hits: 0,
            };

            if can_fuse {
                collector.execute_fused_parallel_set_collect(&specs, contexts)?;
            } else {
                for (child, target, value, _) in &specs {
                    let child_start = profile.then(Instant::now);
                    collector.execute_set_collect(*target, *value, contexts)?;
                    if let Some(start) = child_start {
                        eprintln!(
                            "ecs_profile parallel_set_child action={child} target={target} value={value} elapsed_ms={:.3} eval_calls={} expr_hits={} expr_misses={} relation_hits={} relation_misses={} spatial_index_ms={:.3} spatial_query_ms={:.3} spatial_filter_ms={:.3} direct_agg_hits={} direct_agg_ms={:.3}",
                            start.elapsed().as_secs_f64() * 1000.0,
                            collector.profile_eval_calls,
                            collector.profile_expr_cache_hits,
                            collector.profile_expr_cache_misses,
                            collector.profile_spatial_relation_hits,
                            collector.profile_spatial_relation_misses,
                            collector.profile_spatial_index_nanos as f64 / 1_000_000.0,
                            collector.profile_spatial_query_nanos as f64 / 1_000_000.0,
                            collector.profile_spatial_filter_nanos as f64 / 1_000_000.0,
                            collector.profile_direct_aggregate_hits,
                            collector.profile_direct_aggregate_nanos as f64 / 1_000_000.0,
                        );
                    }
                }
            }
            if let Some(start) = parallel_start {
                eprintln!(
                    "ecs_profile parallel_set_collect_total fused={} elapsed_ms={:.3} eval_calls={} expr_hits={} expr_misses={} relation_hits={} relation_misses={} spatial_index_ms={:.3} spatial_query_ms={:.3} spatial_filter_ms={:.3} direct_agg_hits={} direct_agg_ms={:.3}",
                    can_fuse,
                    start.elapsed().as_secs_f64() * 1000.0,
                    collector.profile_eval_calls,
                    collector.profile_expr_cache_hits,
                    collector.profile_expr_cache_misses,
                    collector.profile_spatial_relation_hits,
                    collector.profile_spatial_relation_misses,
                    collector.profile_spatial_index_nanos as f64 / 1_000_000.0,
                    collector.profile_spatial_query_nanos as f64 / 1_000_000.0,
                    collector.profile_spatial_filter_nanos as f64 / 1_000_000.0,
                    collector.profile_direct_aggregate_hits,
                    collector.profile_direct_aggregate_nanos as f64 / 1_000_000.0,
                );
            }
            let drop_start = profile.then(Instant::now);
            collector_report = std::mem::take(&mut collector.report);
            collector_spatial_indexes = std::mem::take(&mut collector.spatial_indexes);
            collector_spatial_index_metadata =
                std::mem::take(&mut collector.spatial_index_metadata);
            drop(collector);
            if let Some(start) = drop_start {
                eprintln!(
                    "ecs_profile parallel_set_collector_drop elapsed_ms={:.3}",
                    start.elapsed().as_secs_f64() * 1000.0
                );
            }
        }

        self.spatial_indexes.extend(collector_spatial_indexes);
        self.spatial_index_metadata
            .extend(collector_spatial_index_metadata);

        let merge_start = self.profile.then(Instant::now);
        let write_count = collector_report.writes.len();
        let mut targets_seen = HashSet::new();
        let result = self.merge_parallel_report(collector_report, &mut targets_seen);
        if let Some(start) = merge_start {
            eprintln!(
                "ecs_profile parallel_set_merge elapsed_ms={:.3} writes={write_count}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        result
    }

    fn merge_parallel_report(
        &mut self,
        child_report: ExecutionReport,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        self.report.rows_scanned += child_report.rows_scanned;
        self.report.events_emitted += child_report.events_emitted;
        self.report.structural_commands += child_report.structural_commands;
        self.report.duplicate_writes += child_report.duplicate_writes;
        self.report.spatial_indexes_built += child_report.spatial_indexes_built;
        self.report.spatial_candidate_rows += child_report.spatial_candidate_rows;
        self.report.spatial_exact_rows += child_report.spatial_exact_rows;
        self.report.spatial_false_positive_rows += child_report.spatial_false_positive_rows;
        self.report.spatial_deduplicated_pairs += child_report.spatial_deduplicated_pairs;
        self.report.spatial_algorithm_hash_grid += child_report.spatial_algorithm_hash_grid;
        self.report.spatial_algorithm_quadtree += child_report.spatial_algorithm_quadtree;
        self.report.spatial_algorithm_octree += child_report.spatial_algorithm_octree;
        self.report.spatial_algorithm_hilbert_curve += child_report.spatial_algorithm_hilbert_curve;
        self.report.spatial_index_reuses += child_report.spatial_index_reuses;
        self.report.spatial_index_full_rebuilds += child_report.spatial_index_full_rebuilds;
        self.report.spatial_index_incremental_updates +=
            child_report.spatial_index_incremental_updates;
        self.report.spatial_parallel_chunks += child_report.spatial_parallel_chunks;
        self.report.spatial_parallel_workers = self
            .report
            .spatial_parallel_workers
            .max(child_report.spatial_parallel_workers);
        self.report.spatial_thread_scratch_reuses += child_report.spatial_thread_scratch_reuses;
        self.report.spatial_candidate_buffer_growths +=
            child_report.spatial_candidate_buffer_growths;
        self.report.events.extend(child_report.events);
        if child_report.writes.is_empty() {
            self.report.fields_written += child_report.fields_written;
            self.report.resource_fields_written += child_report.resource_fields_written;
        }
        for write in child_report.writes {
            match &write {
                ExecutionWrite::ComponentField {
                    entity,
                    component,
                    field,
                    value,
                } => {
                    let key = WriteKey::Component {
                        entity: *entity,
                        component: component.clone(),
                        field: field.clone(),
                    };
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                    self.world
                        .set_field(*entity, component, field, value.clone())?;
                    self.report.fields_written += 1;
                }
                ExecutionWrite::ResourceField {
                    resource,
                    field,
                    value,
                } => {
                    let key = WriteKey::Resource {
                        resource: resource.clone(),
                        field: field.clone(),
                    };
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                    self.world
                        .set_resource_field(resource, field, value.clone())?;
                    self.report.resource_fields_written += 1;
                }
            }
            if self.report_writes {
                self.report.writes.push(write);
            }
        }
        Ok(())
    }

    fn row_local_numeric_action_query(
        &self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Option<String> {
        if contexts.len() != 1
            || !contexts[0].bindings.is_empty()
            || !contexts[0].loop_items.is_empty()
        {
            return None;
        }
        if !self.action_contains_when(action_index) {
            return None;
        }
        let mut query_name = None;
        if self.row_local_numeric_action_supported(action_index, &mut query_name) {
            query_name
        } else {
            None
        }
    }

    fn action_contains_when(&self, action_index: usize) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::When { .. } => true,
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => children
                .iter()
                .any(|child| self.action_contains_when(*child)),
            ActionNode::ForEach { action, .. } => self.action_contains_when(*action),
            ActionNode::Noop
            | ActionNode::SetField { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::Udf { .. } => false,
        }
    }

    fn row_local_numeric_action_supported(
        &self,
        action_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => true,
            ActionNode::Sequence(children) => children
                .iter()
                .all(|child| self.row_local_numeric_action_supported(*child, query_name)),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return false;
                };
                if !self.note_row_local_query(query_name, query) {
                    return false;
                }
                if !self
                    .world
                    .storage_type_for_field(component, field)
                    .is_ok_and(storage_type_is_numeric)
                {
                    return false;
                }
                self.expr_supports_f64(*value, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*value, query)
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                let Some(primary_query) = query_name.as_deref() else {
                    return false;
                };
                self.expr_supports_f64(*condition, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*condition, primary_query)
                    && self.row_local_numeric_action_supported(*then_action, query_name)
                    && otherwise_action.is_none_or(|action| {
                        self.row_local_numeric_action_supported(action, query_name)
                    })
            }
            ActionNode::Parallel(_)
            | ActionNode::ForEach { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::Udf { .. } => false,
        }
    }

    fn note_row_local_query(&self, query_name: &mut Option<String>, candidate: &str) -> bool {
        match query_name {
            Some(existing) => existing == candidate,
            None => {
                *query_name = Some(candidate.to_string());
                true
            }
        }
    }

    fn expr_uses_only_row_local_direct_fields(&self, expr_index: usize, query_name: &str) -> bool {
        self.expr_uses_only_row_local_direct_fields_inner(
            expr_index,
            query_name,
            &mut HashSet::new(),
        )
    }

    fn expr_uses_only_row_local_direct_fields_inner(
        &self,
        expr_index: usize,
        query_name: &str,
        seen: &mut HashSet<usize>,
    ) -> bool {
        if !seen.insert(expr_index) {
            return true;
        }
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::SpatialAggregate { .. } => true,
            ExprNode::Field { query, .. } => query == query_name,
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*input, query_name, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*left, query_name, seen)
                    && self.expr_uses_only_row_local_direct_fields_inner(*right, query_name, seen)
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. }
            | ExprNode::ContextJoin { .. }
            | ExprNode::Exists { .. }
            | ExprNode::Aggregate { .. }
            | ExprNode::SpatialMetadata { .. } => false,
        }
    }

    fn compile_row_local_action(
        &self,
        action_index: usize,
        query_name: &str,
        program: &CompiledF64ReadOnlyProgram<'_>,
        targets: &mut Vec<RowLocalTarget>,
        target_slots: &mut HashMap<(String, String), usize>,
    ) -> Result<RowLocalAction> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(RowLocalAction::Noop),
            ActionNode::Sequence(children) => children
                .iter()
                .map(|child| {
                    self.compile_row_local_action(
                        *child,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    )
                })
                .collect::<Result<Vec<_>>>()
                .map(RowLocalAction::Sequence),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return Err(EcsError::InvalidPlan(
                        "row-local numeric action target must be a field".to_string(),
                    ));
                };
                if query != query_name {
                    return Err(EcsError::InvalidPlan(format!(
                        "row-local numeric action cannot write query '{query}' from primary query '{query_name}'"
                    )));
                }
                let key = (component.clone(), field.clone());
                let field_slot = *program.field_slot_by_key.get(&key).ok_or_else(|| {
                    EcsError::InvalidPlan(format!(
                        "row-local numeric field cache missing target '{component}.{field}'"
                    ))
                })?;
                let target_slot = if let Some(slot) = target_slots.get(&key) {
                    *slot
                } else {
                    let slot = targets.len();
                    target_slots.insert(key, slot);
                    targets.push(RowLocalTarget {
                        component: component.clone(),
                        field: field.clone(),
                    });
                    slot
                };
                Ok(RowLocalAction::SetField {
                    field_slot,
                    target_slot,
                    value_expr: *value,
                })
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => Ok(RowLocalAction::When {
                condition_expr: *condition,
                then_action: Box::new(self.compile_row_local_action(
                    *then_action,
                    query_name,
                    program,
                    targets,
                    target_slots,
                )?),
                otherwise_action: otherwise_action
                    .map(|action| {
                        self.compile_row_local_action(
                            action,
                            query_name,
                            program,
                            targets,
                            target_slots,
                        )
                        .map(Box::new)
                    })
                    .transpose()?,
            }),
            other => Err(EcsError::InvalidPlan(format!(
                "row-local numeric executor does not support action {other:?}"
            ))),
        }
    }

    fn execute_row_local_numeric_action(
        &mut self,
        action_index: usize,
        query_name: &str,
    ) -> Result<()> {
        let rows = self.query_rows.get(query_name).cloned().ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        if rows.is_empty() {
            return Ok(());
        }

        let precompute_start = self.profile.then(Instant::now);
        self.precompute_direct_spatial_aggregates_for_query(
            query_name,
            SpatialPrecomputeLayout::QueryRows,
        )?;
        if let Some(start) = precompute_start {
            eprintln!(
                "ecs_profile row_local_f64_precompute elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let preload_start = self.profile.then(Instant::now);
        self.preload_numeric_fields_for_query(query_name, SpatialPrecomputeLayout::QueryRows)?;
        if let Some(start) = preload_start {
            eprintln!(
                "ecs_profile row_local_f64_preload elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let locations = self.query_locations(query_name)?;
        let program = compile_f64_readonly_program(
            self.plan,
            self.world,
            query_name,
            &self.numeric_field_cache,
            &self.numeric_field_cache_rows,
            &self.spatial_precomputed_f64,
            &self.spatial_precomputed_f64_rows,
        );
        let mut targets = Vec::new();
        let mut target_slots = HashMap::new();
        let action = self.compile_row_local_action(
            action_index,
            query_name,
            &program,
            &mut targets,
            &mut target_slots,
        )?;
        let target_count = targets.len();
        if target_count == 0 {
            return Ok(());
        }

        let expr_count = self.plan.expressions.len();
        let field_count = program.field_arrays.len();
        let field_dependents = build_row_local_field_dependents(&program);
        let mut flat_values = vec![0.0; rows.len() * target_count];
        let mut dirty = vec![false; rows.len() * target_count];
        let eval_start = self.profile.then(Instant::now);
        let world = &*self.world;
        flat_values
            .par_chunks_mut(target_count)
            .zip(dirty.par_chunks_mut(target_count))
            .zip(rows.par_iter().enumerate())
            .try_for_each_init(
                || {
                    (
                        vec![0.0; expr_count],
                        vec![0_u32; expr_count],
                        1_u32,
                        vec![0.0; field_count],
                    )
                },
                |(cache_values, cache_marks, cache_generation, field_values),
                 ((out, dirty_row), (row_index, entity))| {
                    invalidate_row_local_f64_cache(cache_marks, cache_generation);
                    for (slot, value) in field_values.iter_mut().enumerate() {
                        *value = compiled_field_f64_value(
                            program.field_arrays[slot],
                            row_index,
                            *entity,
                        )?;
                    }
                    execute_row_local_f64_action(
                        &action,
                        row_index,
                        *entity,
                        &program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        &field_dependents,
                        out,
                        dirty_row,
                    )
                },
            )?;
        if let Some(start) = eval_start {
            eprintln!(
                "ecs_profile row_local_f64_eval elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        self.report.rows_scanned += rows.len();

        let apply_start = self.profile.then(Instant::now);
        for (target_index, target) in targets.iter().enumerate() {
            let all_dirty = (0..rows.len()).all(|row| dirty[row * target_count + target_index]);
            if all_dirty {
                self.report.fields_written += self.world.set_field_f64_resolved_strided(
                    &target.component,
                    &target.field,
                    &locations,
                    &flat_values,
                    target_index,
                    target_count,
                )?;
                continue;
            }
            let mut writes = Vec::new();
            for (row_index, entity) in rows.iter().enumerate() {
                if dirty[row_index * target_count + target_index] {
                    writes.push((
                        *entity,
                        flat_values[row_index * target_count + target_index],
                    ));
                }
            }
            if !writes.is_empty() {
                self.report.fields_written +=
                    self.world
                        .set_field_f64_many(&target.component, &target.field, &writes)?;
            }
        }
        if let Some(start) = apply_start {
            eprintln!(
                "ecs_profile row_local_f64_apply elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }

    fn execute_set(
        &mut self,
        target_index: usize,
        value_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(value_index, &mut query_names)?;
        match &self.plan.expressions[target_index] {
            ExprNode::Field { query, .. } => {
                query_names.insert(query.clone());
            }
            ExprNode::ResourceField { .. } => {}
            other => {
                return Err(EcsError::InvalidPlan(format!(
                    "set target must be a field or resource field, got {other:?}"
                )))
            }
        }

        let mut targets_seen = HashSet::new();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let value = self.eval_expr(value_index, &ctx)?;
                self.write_target(target_index, value, &ctx, &mut targets_seen)?;
            }
        }
        Ok(())
    }

    fn execute_set_collect(
        &mut self,
        target_index: usize,
        value_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(value_index, &mut query_names)?;
        match &self.plan.expressions[target_index] {
            ExprNode::Field { query, .. } => {
                query_names.insert(query.clone());
            }
            ExprNode::ResourceField { .. } => {}
            other => {
                return Err(EcsError::InvalidPlan(format!(
                    "set target must be a field or resource field, got {other:?}"
                )))
            }
        }

        let mut targets_seen = HashSet::new();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let value = self.eval_expr(value_index, &ctx)?;
                self.collect_target_write(target_index, value, &ctx, &mut targets_seen)?;
            }
        }
        Ok(())
    }

    fn execute_fused_parallel_set_collect(
        &mut self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        if self.fused_parallel_specs_support_f64(specs) {
            return self.execute_fused_parallel_set_collect_f64(specs, contexts);
        }

        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..specs.len()).map(|_| Vec::new()).collect::<Vec<_>>();
        let mut child_targets_seen = (0..specs.len()).map(|_| HashSet::new()).collect::<Vec<_>>();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                self.local_expr_cache = Some(vec![None; self.plan.expressions.len()]);
                self.local_expr_bindings = Some(ctx.bindings.clone());
                for (child_index, (_, target, value, _)) in specs.iter().enumerate() {
                    let value = self.eval_expr(*value, &ctx)?;
                    let write = self.collect_target_write_record(
                        *target,
                        value,
                        &ctx,
                        &mut child_targets_seen[child_index],
                    )?;
                    child_writes[child_index].push(write);
                }
                self.local_expr_cache = None;
                self.local_expr_bindings = None;
            }
        }
        for writes in child_writes {
            self.report.writes.extend(writes);
        }
        Ok(())
    }

    fn execute_fused_parallel_set_collect_f64(
        &mut self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        if !self.report_writes {
            if let Some(direct_specs) = self.direct_f64_set_specs(specs) {
                return self.execute_fused_parallel_set_collect_f64_direct(
                    &direct_specs,
                    specs,
                    contexts,
                );
            }
        }

        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..specs.len()).map(|_| Vec::new()).collect::<Vec<_>>();
        let mut child_targets_seen = (0..specs.len()).map(|_| HashSet::new()).collect::<Vec<_>>();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let mut cache = vec![None; self.plan.expressions.len()];
                for (child_index, (_, target, value, _)) in specs.iter().enumerate() {
                    let value = self.eval_expr_f64(*value, &ctx, &mut cache)?;
                    let write = self.collect_target_write_record(
                        *target,
                        EcsValue::F64(value),
                        &ctx,
                        &mut child_targets_seen[child_index],
                    )?;
                    child_writes[child_index].push(write);
                }
            }
        }
        for writes in child_writes {
            self.report.writes.extend(writes);
        }
        Ok(())
    }

    fn execute_fused_parallel_set_collect_f64_direct(
        &mut self,
        direct_specs: &[DirectF64SetSpec],
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..direct_specs.len())
            .map(|_| Vec::<(Entity, f64)>::new())
            .collect::<Vec<_>>();
        let mut dense_apply: Option<(Vec<Entity>, Vec<(usize, usize)>, Vec<f64>, usize)> = None;
        let mut cache = vec![None; self.plan.expressions.len()];
        let collect_start: Option<Instant>;
        if query_names.len() == 1 {
            let query_name = query_names
                .iter()
                .next()
                .expect("single query name")
                .clone();
            if contexts.len() == 1
                && contexts[0].bindings.is_empty()
                && contexts[0].loop_items.is_empty()
            {
                let precompute_start = self.profile.then(Instant::now);
                self.precompute_direct_spatial_aggregates_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::QueryRows,
                )?;
                if let Some(start) = precompute_start {
                    eprintln!(
                        "ecs_profile direct_f64_precompute elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                collect_start = self.profile.then(Instant::now);
                let preload_start = self.profile.then(Instant::now);
                self.preload_numeric_fields_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::QueryRows,
                )?;
                if let Some(start) = preload_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_preload elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                let rows = self.query_rows.get(&query_name).cloned().ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
                })?;
                let plan = self.plan;
                let numeric_field_cache = &self.numeric_field_cache;
                let numeric_field_cache_rows = &self.numeric_field_cache_rows;
                let spatial_precomputed_f64 = &self.spatial_precomputed_f64;
                let spatial_precomputed_f64_rows = &self.spatial_precomputed_f64_rows;
                let world = &*self.world;
                let compile_start = self.profile.then(Instant::now);
                let compiled = compile_f64_readonly_program(
                    plan,
                    world,
                    &query_name,
                    numeric_field_cache,
                    numeric_field_cache_rows,
                    spatial_precomputed_f64,
                    spatial_precomputed_f64_rows,
                );
                let expr_count = self.plan.expressions.len();
                let spec_count = direct_specs.len();
                let eval_order = compiled_f64_eval_order(
                    &compiled,
                    direct_specs.iter().map(|spec| spec.value_expr),
                );
                if let Some(start) = compile_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_compile elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                if self.profile {
                    eprintln!(
                        "ecs_profile direct_f64_eval linear={} order_len={}",
                        eval_order.is_some(),
                        eval_order.as_ref().map_or(0, Vec::len)
                    );
                }
                let mut flat_values = vec![0.0; rows.len() * spec_count];
                let eval_start = self.profile.then(Instant::now);
                if let Some(eval_order) = eval_order {
                    flat_values
                        .par_chunks_mut(spec_count)
                        .zip(rows.par_iter().enumerate())
                        .try_for_each_init(
                            || {
                                let mut values = vec![0.0; expr_count];
                                for (index, value) in &compiled.initial_values {
                                    values[*index] = *value;
                                }
                                values
                            },
                            |values, (out, (row_index, entity))| {
                                eval_compiled_f64_linear_order(
                                    &eval_order,
                                    row_index,
                                    *entity,
                                    &compiled,
                                    world,
                                    values,
                                )?;
                                for (slot, spec) in direct_specs.iter().enumerate() {
                                    out[slot] = values[compiled.aliases[spec.value_expr]];
                                }
                                Ok::<(), EcsError>(())
                            },
                        )?;
                } else {
                    flat_values
                        .par_chunks_mut(spec_count)
                        .zip(rows.par_iter().enumerate())
                        .try_for_each_init(
                            || vec![None; expr_count],
                            |row_cache, (out, (row_index, entity))| {
                                row_cache.fill(None);
                                for (slot, spec) in direct_specs.iter().enumerate() {
                                    out[slot] = eval_compiled_f64_readonly(
                                        spec.value_expr,
                                        row_index,
                                        *entity,
                                        &compiled,
                                        world,
                                        row_cache,
                                    )?;
                                }
                                Ok::<(), EcsError>(())
                            },
                        )?;
                }
                if let Some(start) = eval_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_eval elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                self.report.rows_scanned += rows.len();
                let row_locations = self.query_locations(&query_name)?;
                dense_apply = Some((rows, row_locations, flat_values, spec_count));
            } else {
                let precompute_start = self.profile.then(Instant::now);
                self.precompute_direct_spatial_aggregates_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::SparseEntity,
                )?;
                if let Some(start) = precompute_start {
                    eprintln!(
                        "ecs_profile direct_f64_precompute elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                collect_start = self.profile.then(Instant::now);
                for base_ctx in contexts {
                    if base_ctx.bindings.contains_key(&query_name) {
                        cache.fill(None);
                        self.report.rows_scanned += 1;
                        self.collect_direct_f64_row_writes(
                            direct_specs,
                            base_ctx,
                            &mut cache,
                            &mut child_writes,
                        )?;
                        continue;
                    }
                    let rows = self.query_rows.get(&query_name).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "query '{query_name}' is not part of the plan"
                        ))
                    })?;
                    let mut ctx = base_ctx.clone();
                    for entity in rows {
                        ctx.bindings.insert(query_name.clone(), entity);
                        cache.fill(None);
                        self.report.rows_scanned += 1;
                        self.collect_direct_f64_row_writes(
                            direct_specs,
                            &ctx,
                            &mut cache,
                            &mut child_writes,
                        )?;
                    }
                }
            }
        } else {
            collect_start = self.profile.then(Instant::now);
            for base_ctx in contexts {
                let joined = self.expand_context_for_queries(base_ctx, query_names)?;
                self.report.rows_scanned += joined.len();
                for ctx in joined {
                    cache.fill(None);
                    self.collect_direct_f64_row_writes(
                        direct_specs,
                        &ctx,
                        &mut cache,
                        &mut child_writes,
                    )?;
                }
            }
        }

        if let Some(start) = collect_start {
            eprintln!(
                "ecs_profile direct_f64_collect elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }

        let apply_start = self.profile.then(Instant::now);
        let mut target_slots = Vec::with_capacity(direct_specs.len());
        let mut unique_targets: Vec<(&str, &str)> = Vec::new();
        for spec in direct_specs {
            let slot = unique_targets
                .iter()
                .position(|(component, field)| {
                    *component == spec.component.as_str() && *field == spec.field.as_str()
                })
                .unwrap_or_else(|| {
                    unique_targets.push((spec.component.as_str(), spec.field.as_str()));
                    unique_targets.len() - 1
                });
            target_slots.push(slot);
        }
        if let Some((rows, locations, flat_values, spec_count)) = dense_apply {
            let duplicate_targets = (0..unique_targets.len())
                .map(|slot| {
                    target_slots
                        .iter()
                        .filter(|target_slot| **target_slot == slot)
                        .count()
                })
                .map(|count| count.saturating_sub(1))
                .sum::<usize>();
            self.report.duplicate_writes += duplicate_targets * rows.len();
            for (child_index, spec) in direct_specs.iter().enumerate() {
                self.report.fields_written += self.world.set_field_f64_resolved_strided(
                    &spec.component,
                    &spec.field,
                    &locations,
                    &flat_values,
                    child_index,
                    spec_count,
                )?;
            }
        } else {
            let mut targets_seen = HashSet::new();
            for (child_index, writes) in child_writes.into_iter().enumerate() {
                let spec = &direct_specs[child_index];
                let target_slot = target_slots[child_index];
                for (entity, _) in &writes {
                    let key = (entity.raw(), target_slot);
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                }
                self.report.fields_written +=
                    self.world
                        .set_field_f64_many(&spec.component, &spec.field, &writes)?;
            }
        }
        if let Some(start) = apply_start {
            eprintln!(
                "ecs_profile direct_f64_apply elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }

    fn query_locations(&mut self, query_name: &str) -> Result<Vec<(usize, usize)>> {
        if let Some(locations) = self.query_location_cache.get(query_name) {
            return Ok(locations.clone());
        }
        let rows = self.query_rows.get(query_name).ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        let locations = self.world.locations_for_entities(rows.iter().copied())?;
        self.query_location_cache
            .insert(query_name.to_string(), locations.clone());
        Ok(locations)
    }

    fn preload_numeric_fields_for_query(
        &mut self,
        query_name: &str,
        layout: SpatialPrecomputeLayout,
    ) -> Result<()> {
        let rows = self.query_rows.get(query_name).cloned().ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        let mut seen = HashSet::new();
        let mut fields = Vec::new();
        for expr in &self.plan.expressions {
            let ExprNode::Field {
                query,
                component,
                field,
            } = expr
            else {
                continue;
            };
            if query != query_name {
                continue;
            }
            if seen.insert((component.clone(), field.clone())) {
                fields.push((component.clone(), field.clone()));
            }
        }
        let locations = self.query_locations(query_name)?;
        for (component, field) in fields {
            match layout {
                SpatialPrecomputeLayout::SparseEntity => {
                    let values = self.world.field_f64_cache_for_resolved_entities(
                        &component, &field, &rows, &locations,
                    )?;
                    self.numeric_field_cache
                        .entry(component)
                        .or_default()
                        .insert(field, values);
                }
                SpatialPrecomputeLayout::QueryRows => {
                    let values = self
                        .world
                        .field_f64_rows_for_resolved_entities(&component, &field, &locations)?;
                    self.numeric_field_cache_rows
                        .entry(component)
                        .or_default()
                        .insert(field, values);
                }
            }
        }
        Ok(())
    }

    fn collect_direct_f64_row_writes(
        &mut self,
        direct_specs: &[DirectF64SetSpec],
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
        child_writes: &mut [Vec<(Entity, f64)>],
    ) -> Result<()> {
        for (child_index, spec) in direct_specs.iter().enumerate() {
            let entity = ctx.bindings.get(&spec.query).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "query '{}' is not bound for set target",
                    spec.query
                ))
            })?;
            let value = self.eval_expr_f64(spec.value_expr, ctx, cache)?;
            child_writes[child_index].push((entity, value));
        }
        Ok(())
    }

    fn direct_f64_set_specs(
        &self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
    ) -> Option<Vec<DirectF64SetSpec>> {
        let mut direct = Vec::with_capacity(specs.len());
        for (_, target, value, _) in specs {
            let ExprNode::Field {
                query,
                component,
                field,
            } = &self.plan.expressions[*target]
            else {
                return None;
            };
            let storage_type = self.world.storage_type_for_field(component, field).ok()?;
            if !matches!(storage_type, StorageType::Float32 | StorageType::Float64) {
                return None;
            }
            direct.push(DirectF64SetSpec {
                query: query.clone(),
                component: component.clone(),
                field: field.clone(),
                value_expr: *value,
            });
        }
        Some(direct)
    }

    fn fused_parallel_specs_support_f64(
        &self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
    ) -> bool {
        specs.iter().all(|(_, target, value, _)| {
            self.target_supports_f64(*target) && self.expr_supports_f64(*value, &mut HashSet::new())
        })
    }

    fn target_supports_f64(&self, target: usize) -> bool {
        match &self.plan.expressions[target] {
            ExprNode::Field {
                component, field, ..
            }
            | ExprNode::ResourceField {
                resource: component,
                field,
            } => self
                .world
                .storage_type_for_field(component, field)
                .is_ok_and(storage_type_is_numeric),
            _ => false,
        }
    }

    fn expr_supports_f64(&self, expr_index: usize, seen: &mut HashSet<usize>) -> bool {
        if !seen.insert(expr_index) {
            return true;
        }
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_) | ExprNode::LiteralI64(_) | ExprNode::LiteralBool(_) => true,
            ExprNode::LiteralValue(value) => matches!(
                value,
                EcsValue::Bool(_) | EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_)
            ),
            ExprNode::Field {
                component, field, ..
            }
            | ExprNode::ResourceField {
                resource: component,
                field,
            } => self
                .world
                .storage_type_for_field(component, field)
                .is_ok_and(storage_type_is_numeric),
            ExprNode::InputState { .. } => true,
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_supports_f64(*input, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_supports_f64(*left, seen) && self.expr_supports_f64(*right, seen)
            }
            ExprNode::ContextJoin { predicate, .. } => self.expr_supports_f64(*predicate, seen),
            ExprNode::Exists { predicate, .. } => self.expr_supports_f64(*predicate, seen),
            ExprNode::Aggregate {
                relation,
                value,
                default,
                ..
            } => {
                self.expr_supports_f64(*relation, seen)
                    && value.is_none_or(|value| self.expr_supports_f64(value, seen))
                    && default.is_none_or(|default| self.expr_supports_f64(default, seen))
            }
            ExprNode::SpatialMetadata { .. } => true,
            ExprNode::SpatialAggregate { value, default, .. } => {
                value.is_none_or(|value| self.expr_supports_f64(value, seen))
                    && default.is_none_or(|default| self.expr_supports_f64(default, seen))
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => false,
        }
    }

    fn execute_when(
        &mut self,
        condition_index: usize,
        then_action: usize,
        otherwise_action: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut condition_queries = BTreeSet::new();
        self.collect_expr_queries(condition_index, &mut condition_queries)?;
        let mut matched = Vec::new();
        let mut remaining = Vec::new();
        for base_ctx in contexts {
            let expanded = self.expand_context_for_queries(base_ctx, &condition_queries)?;
            self.report.rows_scanned += expanded.len();
            let mut branch_matches = Vec::new();
            for ctx in expanded {
                if truthy(&self.eval_expr(condition_index, &ctx)?)? {
                    branch_matches.push(ctx);
                }
            }
            if branch_matches.is_empty() {
                remaining.push(base_ctx.clone());
            } else {
                matched.extend(branch_matches);
            }
        }
        if !matched.is_empty() {
            self.execute_action(then_action, &matched)?;
        }
        if let Some(otherwise_action) = otherwise_action {
            if !remaining.is_empty() {
                self.execute_action(otherwise_action, &remaining)?;
            }
        }
        Ok(())
    }

    fn write_target(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = *ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self
                    .world
                    .coerce_value_for_component_field(component, field, value)?;
                let key = WriteKey::Component {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_field(entity, component, field, value.clone())?;
                self.report.fields_written += 1;
                if self.report_writes {
                    self.report.writes.push(ExecutionWrite::ComponentField {
                        entity,
                        component: component.clone(),
                        field: field.clone(),
                        value,
                    });
                }
                Ok(())
            }
            ExprNode::ResourceField { resource, field } => {
                let value = self
                    .world
                    .coerce_value_for_component_field(resource, field, value)?;
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_resource_field(resource, field, value.clone())?;
                self.report.resource_fields_written += 1;
                if self.report_writes {
                    self.report.writes.push(ExecutionWrite::ResourceField {
                        resource: resource.clone(),
                        field: field.clone(),
                        value,
                    });
                }
                Ok(())
            }
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }

    fn collect_target_write(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        let write = self.collect_target_write_record(target_index, value, ctx, targets_seen)?;
        self.report.writes.push(write);
        Ok(())
    }

    fn collect_target_write_record(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<ExecutionWrite> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = *ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self
                    .world
                    .coerce_value_for_component_field(component, field, value)?;
                let key = WriteKey::Component {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                Ok(ExecutionWrite::ComponentField {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                    value,
                })
            }
            ExprNode::ResourceField { resource, field } => {
                let value = self
                    .world
                    .coerce_value_for_component_field(resource, field, value)?;
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                Ok(ExecutionWrite::ResourceField {
                    resource: resource.clone(),
                    field: field.clone(),
                    value,
                })
            }
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }

    fn expand_context_for_queries(
        &self,
        base_ctx: &EvalContext,
        query_names: &BTreeSet<String>,
    ) -> Result<Vec<EvalContext>> {
        let missing = query_names
            .iter()
            .filter(|name| !base_ctx.bindings.contains_key(*name))
            .cloned()
            .collect::<Vec<_>>();
        if missing.is_empty() {
            return Ok(vec![base_ctx.clone()]);
        }
        let mut out = Vec::new();
        self.expand_query_recursive(base_ctx, &missing, 0, &mut out)?;
        Ok(out)
    }

    fn expand_query_recursive(
        &self,
        ctx: &EvalContext,
        missing: &[String],
        index: usize,
        out: &mut Vec<EvalContext>,
    ) -> Result<()> {
        if index == missing.len() {
            out.push(ctx.clone());
            return Ok(());
        }
        let query_name = &missing[index];
        let rows = self.query_rows.get(query_name).ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        for entity in rows {
            let next = ctx.with_binding(query_name.clone(), *entity);
            self.expand_query_recursive(&next, missing, index + 1, out)?;
        }
        Ok(())
    }

    fn entity_field_f64(&mut self, entity: Entity, component: &str, field: &str) -> Result<f64> {
        if !self.numeric_field_cache_enabled {
            return self.world.get_field_f64(entity, component, field);
        }
        let row = entity.index as usize;
        if let Some(fields) = self.numeric_field_cache.get(component) {
            if let Some(values) = fields.get(field) {
                if let Some(Some((generation, value))) = values.get(row) {
                    if *generation == entity.generation {
                        return Ok(*value);
                    }
                }
            }
        }
        let value = self.world.get_field_f64(entity, component, field)?;
        let values = self
            .numeric_field_cache
            .entry(component.to_string())
            .or_default()
            .entry(field.to_string())
            .or_default();
        if values.len() <= row {
            values.resize(row + 1, None);
        }
        values[row] = Some((entity.generation, value));
        Ok(value)
    }

    fn precomputed_spatial_f64(&self, expr_index: usize, entity: Entity) -> Option<f64> {
        let values = self.spatial_precomputed_f64.get(&expr_index)?;
        let Some(Some((generation, value))) = values.get(entity.index as usize) else {
            return None;
        };
        (*generation == entity.generation).then_some(*value)
    }

    fn store_precomputed_spatial_f64(&mut self, expr_index: usize, entity: Entity, value: f64) {
        let row = entity.index as usize;
        let values = self.spatial_precomputed_f64.entry(expr_index).or_default();
        if values.len() <= row {
            values.resize(row + 1, None);
        }
        values[row] = Some((entity.generation, value));
    }

    fn precompute_direct_spatial_aggregates_for_query(
        &mut self,
        query_name: &str,
        layout: SpatialPrecomputeLayout,
    ) -> Result<()> {
        let mut seen_relations = HashSet::new();
        let mut relations = Vec::new();
        for expr in &self.plan.expressions {
            let ExprNode::SpatialAggregate { relation, .. } = expr else {
                continue;
            };
            if relation.origin_query != query_name {
                continue;
            }
            let key = (relation.id.clone(), relation.radius, relation.exact_filter);
            if seen_relations.insert(key) {
                relations.push(relation.clone());
            }
        }
        let mut groups: Vec<(String, Vec<SpatialRelationNode>)> = Vec::new();
        for relation in relations {
            let index_key = self.spatial_index_cache_key(&relation);
            if let Some((_, group)) = groups
                .iter_mut()
                .find(|(candidate_key, _)| candidate_key == &index_key)
            {
                group.push(relation);
            } else {
                groups.push((index_key, vec![relation]));
            }
        }
        for (_, group) in groups {
            let Some(first_relation) = group.first() else {
                continue;
            };
            let Some((index_key, index)) =
                self.build_direct_spatial_index_for_relation(first_relation)?
            else {
                continue;
            };
            if self.precompute_direct_spatial_relation_group_f64(&group, &index, layout)? {
                self.spatial_indexes.insert(index_key, index);
                continue;
            }
            if self
                .precompute_multi_origin_direct_spatial_relation_group_f64(&group, &index, layout)?
            {
                self.spatial_indexes.insert(index_key, index);
                continue;
            }
            for relation in group {
                if self.precompute_direct_spatial_relation_group_f64(
                    std::slice::from_ref(&relation),
                    &index,
                    layout,
                )? {
                    continue;
                }
                self.precompute_direct_spatial_relation_f64(&relation, &index)?;
            }
            self.spatial_indexes.insert(index_key, index);
        }
        Ok(())
    }

    fn build_direct_spatial_index_for_relation(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Option<(String, BuiltSpatialIndex)>> {
        if relation.target_bounds.is_some() {
            return Ok(None);
        }
        let Some(target_coords) =
            self.match_direct_spatial_coords(&relation.target_position, &relation.item_query)
        else {
            return Ok(None);
        };
        let index_key = self.spatial_index_cache_key(relation);
        if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let item_rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let item_locations = self.query_locations(&relation.item_query)?;
        let mut target_coord_arrays = Vec::with_capacity(target_coords.len());
        for coord in &target_coords {
            target_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                &coord.component,
                &coord.field,
                &item_locations,
            )?);
        }
        let worker_count = rayon::current_num_threads().max(1);
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        if item_rows.len() >= worker_count * 32 {
            self.report.spatial_parallel_chunks += worker_count;
        }
        if relation.algorithm.kind == "hash_grid" {
            let records = item_rows
                .par_iter()
                .enumerate()
                .map(|(row_index, entity)| {
                    Ok(DirectPointRecord {
                        entity: *entity,
                        point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let signature = self.spatial_index_signature(relation);
            let structural_revision = self.world.structural_revision();
            let field_revision = self.spatial_dependency_revision(relation);
            if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
                if cached.signature == signature
                    && cached.structural_revision == structural_revision
                {
                    if let BuiltSpatialIndex::DirectPointHashGrid(direct_index) = &mut cached.index
                    {
                        if direct_index.update_sorted_points(&records)? {
                            self.report.spatial_index_incremental_updates += 1;
                        } else {
                            self.report.spatial_indexes_built += 1;
                            self.report.spatial_index_full_rebuilds += 1;
                        }
                        self.spatial_index_metadata.insert(
                            index_key.clone(),
                            (signature, structural_revision, field_revision),
                        );
                        self.report_algorithm_use(&cached.index);
                        return Ok(Some((index_key, cached.index)));
                    }
                }
            }
            let mut direct_index = DirectPointHashGrid::new(
                dimensions_from_u8(relation.algorithm.dimensions)?,
                relation.algorithm.cell_size.unwrap_or(1.0),
            )?;
            direct_index.build_sorted_points(records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            let index = BuiltSpatialIndex::DirectPointHashGrid(direct_index);
            self.spatial_index_metadata.insert(
                index_key.clone(),
                (signature, structural_revision, field_revision),
            );
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let records = item_rows
            .par_iter()
            .enumerate()
            .map(|(row_index, entity)| {
                Ok(SpatialRecord {
                    entity: *entity,
                    point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    bounds: None,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let index = self.build_or_update_spatial_index(relation, records)?;
        self.report_algorithm_use(&index);
        Ok(Some((index_key, index)))
    }

    fn direct_spatial_relation_batch(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Option<DirectSpatialRelationBatch>> {
        if relation.origin_bounds.is_some() || relation.target_bounds.is_some() {
            return Ok(None);
        }
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() {
            return Ok(None);
        }
        let radius = relation
            .radius
            .and_then(|expr| literal_expr_numeric(&self.plan.expressions[expr]));
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        if relation.exact_filter.is_some() && distance_filter.is_none() {
            return Ok(None);
        }
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let Some(query_radius) = query_radius else {
            return Ok(None);
        };
        Ok(Some(DirectSpatialRelationBatch {
            specs,
            distance_filter,
            query_radius,
        }))
    }

    fn build_fast_field_array_with_locations(
        &self,
        entities: &[Entity],
        locations: &[(usize, usize)],
        component: &str,
        field: &str,
    ) -> Result<FastFieldArray> {
        let values = self
            .world
            .field_f64_cache_for_resolved_entities(component, field, entities, locations)?;
        Ok(FastFieldArray {
            component: component.to_string(),
            field: field.to_string(),
            values,
        })
    }

    fn ensure_fast_field_array_with_locations(
        &self,
        arrays: &mut Vec<FastFieldArray>,
        entities: &[Entity],
        locations: &[(usize, usize)],
        component: &str,
        field: &str,
    ) -> Result<usize> {
        if let Some(index) = arrays
            .iter()
            .position(|array| array.component == component && array.field == field)
        {
            return Ok(index);
        }
        arrays.push(
            self.build_fast_field_array_with_locations(entities, locations, component, field)?,
        );
        Ok(arrays.len() - 1)
    }

    fn precompute_direct_spatial_relation_group_f64(
        &mut self,
        relations: &[SpatialRelationNode],
        index: &BuiltSpatialIndex,
        layout: SpatialPrecomputeLayout,
    ) -> Result<bool> {
        let profile_start = self.profile.then(Instant::now);
        let Some(first) = relations.first() else {
            return Ok(false);
        };
        if relations
            .iter()
            .any(|relation| !spatial_relations_same_direct_precompute_group(first, relation))
        {
            return Ok(false);
        }
        let Some(origin_coords) =
            self.match_direct_spatial_coords(&first.origin_position, &first.origin_query)
        else {
            return Ok(false);
        };
        let origin_rows = self
            .query_rows
            .get(&first.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    first.origin_query
                ))
            })?;
        let item_rows = self
            .query_rows
            .get(&first.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    first.item_query
                ))
            })?;
        let origin_locations = self.query_locations(&first.origin_query)?;
        let item_locations = self.query_locations(&first.item_query)?;
        let mut origin_coord_arrays = Vec::with_capacity(origin_coords.len());
        for coord in &origin_coords {
            origin_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                &coord.component,
                &coord.field,
                &origin_locations,
            )?);
        }
        let target_coords = self
            .match_direct_spatial_coords(&first.target_position, &first.item_query)
            .unwrap_or_default();
        let mut item_field_arrays: Vec<FastFieldArray> = Vec::new();
        let mut batches = Vec::with_capacity(relations.len());
        for relation in relations {
            let Some(batch) = self.direct_spatial_relation_batch(relation)? else {
                return Ok(false);
            };
            let mut specs = Vec::with_capacity(batch.specs.len());
            for spec in batch.specs {
                let value = match spec.value {
                    SpatialBatchValue::Count => FastSpatialBatchValue::Count,
                    SpatialBatchValue::DirectField { component, field } => {
                        if let Some(axis) = target_coords
                            .iter()
                            .position(|coord| coord.component == component && coord.field == field)
                        {
                            FastSpatialBatchValue::DirectPointCoord { axis }
                        } else {
                            let array_index = self.ensure_fast_field_array_with_locations(
                                &mut item_field_arrays,
                                &item_rows,
                                &item_locations,
                                &component,
                                &field,
                            )?;
                            FastSpatialBatchValue::DirectField { array_index }
                        }
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => FastSpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    },
                };
                let Some(kind) = fast_aggregate_kind(&spec.kind) else {
                    return Ok(false);
                };
                specs.push(FastSpatialBatchSpec {
                    expr_index: spec.expr_index,
                    kind,
                    value,
                });
            }
            batches.push(FastDirectSpatialRelationBatch {
                specs,
                distance_filter: batch.distance_filter,
                query_radius: batch.query_radius,
                query_radius_sq: batch.query_radius * batch.query_radius,
            });
        }
        let item_record_field_arrays = if let BuiltSpatialIndex::DirectPointHashGrid(index) = index
        {
            item_field_arrays
                .iter()
                .map(|array| fast_field_array_record_values(array, &index.records))
                .collect::<Result<Vec<_>>>()?
        } else {
            Vec::new()
        };
        let item_record_field_arrays_ref =
            (!item_record_field_arrays.is_empty()).then_some(item_record_field_arrays.as_slice());
        let dimensions = dimensions_len(first.algorithm.dimensions)?;
        let result_exprs = batches
            .iter()
            .flat_map(|batch| batch.specs.iter().map(|spec| spec.expr_index))
            .collect::<Vec<_>>();
        let result_count = result_exprs.len();
        if result_count == 0 {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(&batches);
        let max_entity_index = origin_rows
            .iter()
            .map(|entity| entity.index as usize)
            .max()
            .unwrap_or(0);
        let max_radius = batches
            .iter()
            .map(|batch| batch.query_radius)
            .fold(0.0_f64, f64::max);
        if layout == SpatialPrecomputeLayout::QueryRows {
            if let BuiltSpatialIndex::DirectPointHashGrid(item_index) = index {
                if item_index.regular_grid.is_none()
                    && item_index.records.len() >= 1024
                    && item_index.records.len().saturating_mul(4) < origin_rows.len()
                    && self.precompute_inverted_direct_spatial_relation_group_f64(
                        first,
                        &batches,
                        &origin_rows,
                        &origin_coord_arrays,
                        item_index,
                        &item_field_arrays,
                        item_record_field_arrays_ref,
                        &result_exprs,
                        result_count,
                        max_radius,
                    )?
                {
                    if let Some(start) = profile_start {
                        eprintln!(
                            "ecs_profile direct_spatial_group mode=same_origin_inverted origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                            first.origin_query,
                            first.item_query,
                            relations.len(),
                            result_count,
                            origin_rows.len(),
                            start.elapsed().as_secs_f64() * 1000.0
                        );
                    }
                    return Ok(true);
                }
            }
        }
        let worker_count = rayon::current_num_threads().max(1);
        let chunk_size = (origin_rows.len() / (worker_count * 4))
            .clamp(128, 1024)
            .max(1);
        let chunk_results = origin_rows
            .par_chunks(chunk_size)
            .enumerate()
            .map(|(chunk_index, chunk)| {
                let row_start = chunk_index * chunk_size;
                let mut candidates = Vec::new();
                let mut counters = SpatialLocalCounters::default();
                let mut origins = Vec::with_capacity(chunk.len());
                let mut values = Vec::with_capacity(chunk.len() * result_count);
                let mut present = (!result_values_are_dense)
                    .then(|| Vec::with_capacity(chunk.len() * result_count));
                let mut accumulators = batches
                    .iter()
                    .map(|batch| vec![SpatialBatchAccum::default(); batch.specs.len()])
                    .collect::<Vec<_>>();
                let mut exact_counts = vec![0usize; batches.len()];
                for (chunk_offset, origin_entity) in chunk.iter().copied().enumerate() {
                    let origin_row = row_start + chunk_offset;
                    let origin_point = point_from_row_arrays(&origin_coord_arrays, origin_row)?;
                    for accumulator in &mut accumulators {
                        accumulator.fill(SpatialBatchAccum::default());
                    }
                    exact_counts.fill(0);
                    let before_capacity = candidates.capacity();
                    match index {
                        BuiltSpatialIndex::HashGrid(index) => {
                            index.visit_radius_unordered(
                                &origin_point,
                                max_radius,
                                |record, distance_sq| {
                                    process_fast_spatial_record(
                                        first,
                                        &batches,
                                        &item_field_arrays,
                                        None,
                                        origin_entity,
                                        &origin_point,
                                        None,
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators,
                                        &mut exact_counts,
                                        &mut counters,
                                    )
                                },
                            )?;
                        }
                        BuiltSpatialIndex::DirectPointHashGrid(index) => {
                            index.visit_radius_unordered_indexed(
                                &origin_point,
                                max_radius,
                                |record_index, record, distance_sq| {
                                    process_fast_spatial_record(
                                        first,
                                        &batches,
                                        &item_field_arrays,
                                        item_record_field_arrays_ref,
                                        origin_entity,
                                        &origin_point,
                                        Some(record_index),
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators,
                                        &mut exact_counts,
                                        &mut counters,
                                    )
                                },
                            )?;
                        }
                        _ => {
                            candidates.clear();
                            index.query_radius_unordered(
                                &origin_point,
                                max_radius,
                                &mut candidates,
                            )?;
                            if candidates.capacity() > before_capacity {
                                counters.candidate_buffer_growths += 1;
                            }
                            for record in candidates.iter() {
                                let distance_sq = direct_distance_squared(
                                    &origin_point,
                                    &record.point,
                                    dimensions,
                                );
                                process_fast_spatial_record(
                                    first,
                                    &batches,
                                    &item_field_arrays,
                                    None,
                                    origin_entity,
                                    &origin_point,
                                    None,
                                    record.entity,
                                    &record.point,
                                    distance_sq,
                                    &mut accumulators,
                                    &mut exact_counts,
                                    &mut counters,
                                )?;
                            }
                        }
                    }
                    if layout == SpatialPrecomputeLayout::SparseEntity {
                        origins.push(origin_entity);
                    }
                    for (batch_index, batch) in batches.iter().enumerate() {
                        let exact_count = exact_counts[batch_index];
                        for (spec, accumulator) in
                            batch.specs.iter().zip(accumulators[batch_index].iter())
                        {
                            let value = match spec.kind {
                                FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                                FastAggregateKind::Count => Some(exact_count as f64),
                                FastAggregateKind::Sum => Some(accumulator.sum),
                                FastAggregateKind::Mean if accumulator.count > 0 => {
                                    Some(accumulator.sum / accumulator.count as f64)
                                }
                                FastAggregateKind::Min if accumulator.count > 0 => {
                                    Some(accumulator.min)
                                }
                                FastAggregateKind::Max if accumulator.count > 0 => {
                                    Some(accumulator.max)
                                }
                                _ => None,
                            };
                            if result_values_are_dense {
                                values.push(value.unwrap_or(0.0));
                            } else if let Some(present) = present.as_mut() {
                                match value {
                                    Some(value) => {
                                        values.push(value);
                                        present.push(true);
                                    }
                                    None => {
                                        values.push(0.0);
                                        present.push(false);
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(SpatialChunkResult {
                    row_start,
                    origins,
                    values,
                    present,
                    counters,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        self.report.spatial_parallel_chunks += chunk_results.len();
        self.report.spatial_thread_scratch_reuses +=
            origin_rows.len().saturating_sub(chunk_results.len());
        match layout {
            SpatialPrecomputeLayout::SparseEntity => {
                let mut result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; max_entity_index + 1]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start: _,
                        origins,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let present = present.as_deref();
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for (origin_index, origin) in origins.into_iter().enumerate() {
                        let base = origin_index * result_count;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present.is_none_or(|present| present[base + slot]) {
                                result_arrays[slot].1[origin.index as usize] =
                                    Some((origin.generation, *value));
                            }
                        }
                    }
                }
                for (expr_index, values) in result_arrays {
                    self.spatial_precomputed_f64.insert(expr_index, values);
                }
            }
            SpatialPrecomputeLayout::QueryRows if result_values_are_dense => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present: _,
                        counters,
                    } = chunk;
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            row_result_arrays[slot].1[row_index] = *value;
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Dense(values));
                }
            }
            SpatialPrecomputeLayout::QueryRows => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let Some(present) = present else {
                        return Err(EcsError::InvalidPlan(
                            "optional spatial row results missing presence flags".to_string(),
                        ));
                    };
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present[base + slot] {
                                row_result_arrays[slot].1[row_index] = Some(*value);
                            }
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Optional(values));
                }
            }
        }
        if let Some(start) = profile_start {
            eprintln!(
                "ecs_profile direct_spatial_group mode=same_origin origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                first.origin_query,
                first.item_query,
                relations.len(),
                result_count,
                origin_rows.len(),
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(true)
    }

    #[allow(clippy::too_many_arguments)]
    fn precompute_inverted_direct_spatial_relation_group_f64(
        &mut self,
        relation: &SpatialRelationNode,
        batches: &[FastDirectSpatialRelationBatch],
        origin_rows: &[Entity],
        _origin_coord_arrays: &[Vec<f64>],
        item_index: &DirectPointHashGrid,
        item_field_arrays: &[FastFieldArray],
        item_record_field_arrays: Option<&[Vec<f64>]>,
        result_exprs: &[usize],
        result_count: usize,
        max_radius: f64,
    ) -> Result<bool> {
        if result_count == 0 || origin_rows.is_empty() || item_index.records.is_empty() {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(batches);
        let mut origin_index_relation = relation.clone();
        origin_index_relation.index_id = format!("inverted_origin:{}", relation.index_id);
        origin_index_relation.item_query = relation.origin_query.clone();
        origin_index_relation.target_position = relation.origin_position.clone();
        origin_index_relation.target_bounds = None;
        let Some((origin_index_key, BuiltSpatialIndex::DirectPointHashGrid(origin_index))) =
            self.build_direct_spatial_index_for_relation(&origin_index_relation)?
        else {
            return Ok(false);
        };
        if origin_index.regular_grid.is_none()
            && item_index.records.len().saturating_mul(4) >= origin_rows.len()
        {
            self.spatial_indexes.insert(
                origin_index_key,
                BuiltSpatialIndex::DirectPointHashGrid(origin_index),
            );
            return Ok(false);
        }

        let mut spec_offsets = Vec::with_capacity(batches.len());
        let mut offset = 0usize;
        for batch in batches {
            spec_offsets.push(offset);
            offset += batch.specs.len();
        }
        if offset != result_count {
            return Ok(false);
        }

        let mut accumulators = vec![SpatialBatchAccum::default(); origin_rows.len() * result_count];
        let mut exact_counts = vec![0usize; origin_rows.len() * batches.len()];
        let mut counters = SpatialLocalCounters::default();

        for (item_record_index, item_record) in item_index.records.iter().enumerate() {
            let item_entity = item_record.entity;
            let item_point = &item_record.point;
            origin_index.visit_radius_unordered_indexed(
                item_point,
                max_radius,
                |origin_index, origin_record, distance_sq| {
                    counters.candidate_rows += 1;
                    if !relation.include_self && item_entity == origin_record.entity {
                        return Ok(());
                    }
                    if relation.pair_policy == "unique_unordered"
                        && item_entity.raw() <= origin_record.entity.raw()
                    {
                        counters.deduplicated_pairs += 1;
                        return Ok(());
                    }
                    let mut inverse_distance_cache: Option<(f64, f64)> = None;
                    for (batch_index, batch) in batches.iter().enumerate() {
                        if distance_sq > batch.query_radius_sq {
                            continue;
                        }
                        if let Some(distance_filter) = batch.distance_filter {
                            if !distance_filter.matches(distance_sq) {
                                continue;
                            }
                        }
                        exact_counts[origin_index * batches.len() + batch_index] += 1;
                        counters.rows_scanned += 1;
                        counters.exact_rows += 1;
                        let spec_offset = spec_offsets[batch_index];
                        for (spec_index, spec) in batch.specs.iter().enumerate() {
                            if matches!(
                                spec.kind,
                                FastAggregateKind::Any | FastAggregateKind::Count
                            ) {
                                continue;
                            }
                            let value = match &spec.value {
                                FastSpatialBatchValue::Count => 1.0,
                                FastSpatialBatchValue::DirectField { array_index } => {
                                    if let Some(record_arrays) = item_record_field_arrays {
                                        record_arrays[*array_index][item_record_index]
                                    } else {
                                        fast_field_array_value(
                                            &item_field_arrays[*array_index],
                                            item_entity,
                                        )?
                                    }
                                }
                                FastSpatialBatchValue::DirectPointCoord { axis } => {
                                    item_point.coord(*axis)
                                }
                                FastSpatialBatchValue::NegDeltaOverDistance {
                                    axis,
                                    minimum_distance,
                                } => {
                                    let inverse_distance = match inverse_distance_cache {
                                        Some((cached_minimum, value))
                                            if cached_minimum == *minimum_distance =>
                                        {
                                            value
                                        }
                                        _ => {
                                            let value =
                                                1.0 / distance_sq.sqrt().max(*minimum_distance);
                                            inverse_distance_cache =
                                                Some((*minimum_distance, value));
                                            value
                                        }
                                    };
                                    let delta_axis =
                                        item_point.coord(*axis) - origin_record.point.coord(*axis);
                                    -delta_axis * inverse_distance
                                }
                            };
                            let accumulator = &mut accumulators
                                [origin_index * result_count + spec_offset + spec_index];
                            match spec.kind {
                                FastAggregateKind::Sum => accumulator.sum += value,
                                FastAggregateKind::Mean => {
                                    accumulator.count += 1;
                                    accumulator.sum += value;
                                }
                                FastAggregateKind::Min => {
                                    accumulator.count += 1;
                                    accumulator.min = accumulator.min.min(value);
                                }
                                FastAggregateKind::Max => {
                                    accumulator.count += 1;
                                    accumulator.max = accumulator.max.max(value);
                                }
                                FastAggregateKind::Any | FastAggregateKind::Count => {}
                            }
                        }
                    }
                    Ok(())
                },
            )?;
        }

        if result_values_are_dense {
            let mut row_result_arrays = result_exprs
                .iter()
                .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                .collect::<Vec<_>>();
            for origin_index in 0..origin_rows.len() {
                for (batch_index, batch) in batches.iter().enumerate() {
                    let exact_count = exact_counts[origin_index * batches.len() + batch_index];
                    let spec_offset = spec_offsets[batch_index];
                    for (spec_index, spec) in batch.specs.iter().enumerate() {
                        let accumulator =
                            &accumulators[origin_index * result_count + spec_offset + spec_index];
                        let value = match spec.kind {
                            FastAggregateKind::Any => bool_f64(exact_count > 0),
                            FastAggregateKind::Count => exact_count as f64,
                            FastAggregateKind::Sum => accumulator.sum,
                            _ => 0.0,
                        };
                        row_result_arrays[spec_offset + spec_index].1[origin_index] = value;
                    }
                }
            }
            for (expr_index, values) in row_result_arrays {
                self.spatial_precomputed_f64_rows
                    .insert(expr_index, SpatialF64RowArray::Dense(values));
            }
        } else {
            let mut row_result_arrays = result_exprs
                .iter()
                .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                .collect::<Vec<_>>();
            for origin_index in 0..origin_rows.len() {
                for (batch_index, batch) in batches.iter().enumerate() {
                    let exact_count = exact_counts[origin_index * batches.len() + batch_index];
                    let spec_offset = spec_offsets[batch_index];
                    for (spec_index, spec) in batch.specs.iter().enumerate() {
                        let accumulator =
                            &accumulators[origin_index * result_count + spec_offset + spec_index];
                        let value = match spec.kind {
                            FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                            FastAggregateKind::Count => Some(exact_count as f64),
                            FastAggregateKind::Sum => Some(accumulator.sum),
                            FastAggregateKind::Mean if accumulator.count > 0 => {
                                Some(accumulator.sum / accumulator.count as f64)
                            }
                            FastAggregateKind::Min if accumulator.count > 0 => {
                                Some(accumulator.min)
                            }
                            FastAggregateKind::Max if accumulator.count > 0 => {
                                Some(accumulator.max)
                            }
                            _ => None,
                        };
                        if let Some(value) = value {
                            row_result_arrays[spec_offset + spec_index].1[origin_index] =
                                Some(value);
                        }
                    }
                }
            }
            for (expr_index, values) in row_result_arrays {
                self.spatial_precomputed_f64_rows
                    .insert(expr_index, SpatialF64RowArray::Optional(values));
            }
        }
        self.spatial_indexes.insert(
            origin_index_key,
            BuiltSpatialIndex::DirectPointHashGrid(origin_index),
        );
        self.report.spatial_candidate_rows += counters.candidate_rows;
        self.report.rows_scanned += counters.rows_scanned;
        self.report.spatial_exact_rows += counters.exact_rows;
        self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
        self.report.spatial_candidate_buffer_growths += counters.candidate_buffer_growths;
        Ok(true)
    }

    fn precompute_multi_origin_direct_spatial_relation_group_f64(
        &mut self,
        relations: &[SpatialRelationNode],
        index: &BuiltSpatialIndex,
        layout: SpatialPrecomputeLayout,
    ) -> Result<bool> {
        let profile_start = self.profile.then(Instant::now);
        let Some(first) = relations.first() else {
            return Ok(false);
        };
        if relations.len() < 2
            || relations.iter().any(|relation| {
                !spatial_relations_same_multi_origin_precompute_group(first, relation)
            })
        {
            return Ok(false);
        }
        if first.origin_bounds.is_some() || first.target_bounds.is_some() {
            return Ok(false);
        }
        let origin_rows = self
            .query_rows
            .get(&first.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    first.origin_query
                ))
            })?;
        let item_rows = self
            .query_rows
            .get(&first.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    first.item_query
                ))
            })?;
        let origin_locations = self.query_locations(&first.origin_query)?;
        let item_locations = self.query_locations(&first.item_query)?;
        let target_coords = self
            .match_direct_spatial_coords(&first.target_position, &first.item_query)
            .unwrap_or_default();
        let mut item_field_arrays: Vec<FastFieldArray> = Vec::new();
        let mut origin_coord_arrays_by_relation = Vec::with_capacity(relations.len());
        let mut batches = Vec::with_capacity(relations.len());
        for relation in relations {
            let Some(origin_coords) =
                self.match_direct_spatial_coords(&relation.origin_position, &relation.origin_query)
            else {
                return Ok(false);
            };
            let mut origin_coord_arrays = Vec::with_capacity(origin_coords.len());
            for coord in &origin_coords {
                origin_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                    &coord.component,
                    &coord.field,
                    &origin_locations,
                )?);
            }
            let Some(batch) = self.direct_spatial_relation_batch(relation)? else {
                return Ok(false);
            };
            let mut specs = Vec::with_capacity(batch.specs.len());
            for spec in batch.specs {
                let value = match spec.value {
                    SpatialBatchValue::Count => FastSpatialBatchValue::Count,
                    SpatialBatchValue::DirectField { component, field } => {
                        if let Some(axis) = target_coords
                            .iter()
                            .position(|coord| coord.component == component && coord.field == field)
                        {
                            FastSpatialBatchValue::DirectPointCoord { axis }
                        } else {
                            let array_index = self.ensure_fast_field_array_with_locations(
                                &mut item_field_arrays,
                                &item_rows,
                                &item_locations,
                                &component,
                                &field,
                            )?;
                            FastSpatialBatchValue::DirectField { array_index }
                        }
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => FastSpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    },
                };
                let Some(kind) = fast_aggregate_kind(&spec.kind) else {
                    return Ok(false);
                };
                specs.push(FastSpatialBatchSpec {
                    expr_index: spec.expr_index,
                    kind,
                    value,
                });
            }
            origin_coord_arrays_by_relation.push(origin_coord_arrays);
            batches.push(FastDirectSpatialRelationBatch {
                specs,
                distance_filter: batch.distance_filter,
                query_radius: batch.query_radius,
                query_radius_sq: batch.query_radius * batch.query_radius,
            });
        }
        let item_record_field_arrays = if let BuiltSpatialIndex::DirectPointHashGrid(index) = index
        {
            item_field_arrays
                .iter()
                .map(|array| fast_field_array_record_values(array, &index.records))
                .collect::<Result<Vec<_>>>()?
        } else {
            Vec::new()
        };
        let item_record_field_arrays_ref =
            (!item_record_field_arrays.is_empty()).then_some(item_record_field_arrays.as_slice());
        let dimensions = dimensions_len(first.algorithm.dimensions)?;
        let result_exprs = batches
            .iter()
            .flat_map(|batch| batch.specs.iter().map(|spec| spec.expr_index))
            .collect::<Vec<_>>();
        let result_count = result_exprs.len();
        if result_count == 0 {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(&batches);
        let max_entity_index = origin_rows
            .iter()
            .map(|entity| entity.index as usize)
            .max()
            .unwrap_or(0);
        let worker_count = rayon::current_num_threads().max(1);
        let chunk_size = (origin_rows.len() / (worker_count * 4))
            .clamp(128, 1024)
            .max(1);
        let chunk_results = origin_rows
            .par_chunks(chunk_size)
            .enumerate()
            .map(|(chunk_index, chunk)| {
                let row_start = chunk_index * chunk_size;
                let mut candidates = Vec::new();
                let mut counters = SpatialLocalCounters::default();
                let mut origins = Vec::with_capacity(chunk.len());
                let mut values = Vec::with_capacity(chunk.len() * result_count);
                let mut present = (!result_values_are_dense)
                    .then(|| Vec::with_capacity(chunk.len() * result_count));
                let mut accumulators = batches
                    .iter()
                    .map(|batch| vec![SpatialBatchAccum::default(); batch.specs.len()])
                    .collect::<Vec<_>>();
                let mut exact_counts = vec![0usize; batches.len()];
                for (chunk_offset, origin_entity) in chunk.iter().copied().enumerate() {
                    let origin_row = row_start + chunk_offset;
                    for accumulator in &mut accumulators {
                        accumulator.fill(SpatialBatchAccum::default());
                    }
                    exact_counts.fill(0);
                    for relation_index in 0..batches.len() {
                        let origin_point = point_from_row_arrays(
                            &origin_coord_arrays_by_relation[relation_index],
                            origin_row,
                        )?;
                        let batch = &batches[relation_index];
                        let before_capacity = candidates.capacity();
                        match index {
                            BuiltSpatialIndex::HashGrid(index) => {
                                index.visit_radius_unordered(
                                    &origin_point,
                                    batch.query_radius,
                                    |record, distance_sq| {
                                        process_fast_spatial_record(
                                            &relations[relation_index],
                                            &batches[relation_index..relation_index + 1],
                                            &item_field_arrays,
                                            None,
                                            origin_entity,
                                            &origin_point,
                                            None,
                                            record.entity,
                                            &record.point,
                                            distance_sq,
                                            &mut accumulators[relation_index..relation_index + 1],
                                            &mut exact_counts[relation_index..relation_index + 1],
                                            &mut counters,
                                        )
                                    },
                                )?;
                            }
                            BuiltSpatialIndex::DirectPointHashGrid(index) => {
                                index.visit_radius_unordered_indexed(
                                    &origin_point,
                                    batch.query_radius,
                                    |record_index, record, distance_sq| {
                                        process_fast_spatial_record(
                                            &relations[relation_index],
                                            &batches[relation_index..relation_index + 1],
                                            &item_field_arrays,
                                            item_record_field_arrays_ref,
                                            origin_entity,
                                            &origin_point,
                                            Some(record_index),
                                            record.entity,
                                            &record.point,
                                            distance_sq,
                                            &mut accumulators[relation_index..relation_index + 1],
                                            &mut exact_counts[relation_index..relation_index + 1],
                                            &mut counters,
                                        )
                                    },
                                )?;
                            }
                            _ => {
                                candidates.clear();
                                index.query_radius_unordered(
                                    &origin_point,
                                    batch.query_radius,
                                    &mut candidates,
                                )?;
                                if candidates.capacity() > before_capacity {
                                    counters.candidate_buffer_growths += 1;
                                }
                                for record in candidates.iter() {
                                    let distance_sq = direct_distance_squared(
                                        &origin_point,
                                        &record.point,
                                        dimensions,
                                    );
                                    process_fast_spatial_record(
                                        &relations[relation_index],
                                        &batches[relation_index..relation_index + 1],
                                        &item_field_arrays,
                                        None,
                                        origin_entity,
                                        &origin_point,
                                        None,
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators[relation_index..relation_index + 1],
                                        &mut exact_counts[relation_index..relation_index + 1],
                                        &mut counters,
                                    )?;
                                }
                            }
                        }
                    }
                    if layout == SpatialPrecomputeLayout::SparseEntity {
                        origins.push(origin_entity);
                    }
                    for (relation_index, batch) in batches.iter().enumerate() {
                        let exact_count = exact_counts[relation_index];
                        for (spec, accumulator) in
                            batch.specs.iter().zip(accumulators[relation_index].iter())
                        {
                            let value = match spec.kind {
                                FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                                FastAggregateKind::Count => Some(exact_count as f64),
                                FastAggregateKind::Sum => Some(accumulator.sum),
                                FastAggregateKind::Mean if accumulator.count > 0 => {
                                    Some(accumulator.sum / accumulator.count as f64)
                                }
                                FastAggregateKind::Min if accumulator.count > 0 => {
                                    Some(accumulator.min)
                                }
                                FastAggregateKind::Max if accumulator.count > 0 => {
                                    Some(accumulator.max)
                                }
                                _ => None,
                            };
                            if result_values_are_dense {
                                values.push(value.unwrap_or(0.0));
                            } else if let Some(present) = present.as_mut() {
                                match value {
                                    Some(value) => {
                                        values.push(value);
                                        present.push(true);
                                    }
                                    None => {
                                        values.push(0.0);
                                        present.push(false);
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(SpatialChunkResult {
                    row_start,
                    origins,
                    values,
                    present,
                    counters,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        self.report.spatial_parallel_chunks += chunk_results.len();
        self.report.spatial_thread_scratch_reuses +=
            origin_rows.len().saturating_sub(chunk_results.len());
        match layout {
            SpatialPrecomputeLayout::SparseEntity => {
                let mut result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; max_entity_index + 1]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start: _,
                        origins,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let present = present.as_deref();
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for (origin_index, origin) in origins.into_iter().enumerate() {
                        let base = origin_index * result_count;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present.is_none_or(|present| present[base + slot]) {
                                result_arrays[slot].1[origin.index as usize] =
                                    Some((origin.generation, *value));
                            }
                        }
                    }
                }
                for (expr_index, values) in result_arrays {
                    self.spatial_precomputed_f64.insert(expr_index, values);
                }
            }
            SpatialPrecomputeLayout::QueryRows if result_values_are_dense => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present: _,
                        counters,
                    } = chunk;
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            row_result_arrays[slot].1[row_index] = *value;
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Dense(values));
                }
            }
            SpatialPrecomputeLayout::QueryRows => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let Some(present) = present else {
                        return Err(EcsError::InvalidPlan(
                            "optional spatial row results missing presence flags".to_string(),
                        ));
                    };
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present[base + slot] {
                                row_result_arrays[slot].1[row_index] = Some(*value);
                            }
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Optional(values));
                }
            }
        }
        if let Some(start) = profile_start {
            eprintln!(
                "ecs_profile direct_spatial_group mode=multi_origin origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                first.origin_query,
                first.item_query,
                relations.len(),
                result_count,
                origin_rows.len(),
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(true)
    }

    fn precompute_direct_spatial_relation_f64(
        &mut self,
        relation: &SpatialRelationNode,
        index: &BuiltSpatialIndex,
    ) -> Result<()> {
        if relation.origin_bounds.is_some() || relation.target_bounds.is_some() {
            return Ok(());
        }
        let Some(origin_coords) =
            self.match_direct_spatial_coords(&relation.origin_position, &relation.origin_query)
        else {
            return Ok(());
        };
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() {
            return Ok(());
        }

        let radius = relation
            .radius
            .and_then(|expr| literal_expr_numeric(&self.plan.expressions[expr]));
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        let generic_exact_filter = if relation.exact_filter.is_some() && distance_filter.is_none() {
            relation.exact_filter
        } else {
            None
        };
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let Some(query_radius) = query_radius else {
            return Ok(());
        };

        let origin_rows = self
            .query_rows
            .get(&relation.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    relation.origin_query
                ))
            })?;

        let dimensions = dimensions_len(relation.algorithm.dimensions)?;
        let needs_delta = specs
            .iter()
            .any(|spec| matches!(spec.value, SpatialBatchValue::NegDeltaOverDistance { .. }));
        let mut candidates = Vec::new();
        let mut accumulators = vec![SpatialBatchAccum::default(); specs.len()];
        for origin_entity in origin_rows {
            let origin_point =
                self.direct_spatial_point_for_entity(origin_entity, &origin_coords)?;

            accumulators.fill(SpatialBatchAccum::default());
            let mut exact_count = 0usize;
            let mut process_record = |executor: &mut Self,
                                      record: &SpatialRecord,
                                      visited_distance_sq: f64|
             -> Result<()> {
                executor.report.spatial_candidate_rows += 1;
                if !relation.include_self && record.entity == origin_entity {
                    return Ok(());
                }
                if relation.pair_policy == "unique_unordered"
                    && record.entity.raw() <= origin_entity.raw()
                {
                    executor.report.spatial_deduplicated_pairs += 1;
                    return Ok(());
                }
                let distance_sq = if needs_delta || distance_filter.is_some() {
                    visited_distance_sq
                } else {
                    0.0
                };
                if let Some(distance_filter) = distance_filter {
                    if !distance_filter.matches(distance_sq) {
                        return Ok(());
                    }
                }
                if let Some(filter_expr) = generic_exact_filter {
                    let mut filter_ctx = EvalContext::default();
                    filter_ctx
                        .bindings
                        .insert(relation.origin_query.clone(), origin_entity);
                    filter_ctx
                        .bindings
                        .insert(relation.item_query.clone(), record.entity);
                    let mut filter_cache = vec![None; executor.plan.expressions.len()];
                    if !truthy_f64(executor.eval_expr_f64(
                        filter_expr,
                        &filter_ctx,
                        &mut filter_cache,
                    )?) {
                        return Ok(());
                    }
                }
                exact_count += 1;
                executor.report.rows_scanned += 1;
                executor.report.spatial_exact_rows += 1;
                for (index, spec) in specs.iter().enumerate() {
                    let value = match &spec.value {
                        SpatialBatchValue::Count => 1.0,
                        SpatialBatchValue::DirectField { component, field } => {
                            executor.entity_field_f64(record.entity, component, field)?
                        }
                        SpatialBatchValue::NegDeltaOverDistance {
                            axis,
                            minimum_distance,
                        } => {
                            let delta_axis = record.point.coord(*axis) - origin_point.coord(*axis);
                            -delta_axis / distance_sq.sqrt().max(*minimum_distance)
                        }
                    };
                    let accumulator = &mut accumulators[index];
                    accumulator.count += 1;
                    accumulator.sum += value;
                    accumulator.min = accumulator.min.min(value);
                    accumulator.max = accumulator.max.max(value);
                }
                Ok(())
            };
            match &index {
                BuiltSpatialIndex::HashGrid(index) => {
                    index.visit_radius_unordered(
                        &origin_point,
                        query_radius,
                        |record, distance_sq| process_record(self, record, distance_sq),
                    )?;
                }
                _ => {
                    candidates.clear();
                    index.query_radius_unordered(&origin_point, query_radius, &mut candidates)?;
                    for record in candidates.iter() {
                        let distance_sq = if needs_delta || distance_filter.is_some() {
                            direct_distance_squared(&origin_point, &record.point, dimensions)
                        } else {
                            0.0
                        };
                        process_record(self, record, distance_sq)?;
                    }
                }
            }

            for (spec, accumulator) in specs.iter().zip(accumulators.iter()) {
                let value = match spec.kind.as_str() {
                    "any" => bool_f64(exact_count > 0),
                    "count" => exact_count as f64,
                    "sum" => accumulator.sum,
                    "mean" if accumulator.count > 0 => accumulator.sum / accumulator.count as f64,
                    "min" if accumulator.count > 0 => accumulator.min,
                    "max" if accumulator.count > 0 => accumulator.max,
                    _ => continue,
                };
                self.store_precomputed_spatial_f64(spec.expr_index, origin_entity, value);
            }
        }
        Ok(())
    }

    fn match_direct_spatial_coords(
        &self,
        coords: &[usize],
        query_name: &str,
    ) -> Option<Vec<DirectSpatialCoord>> {
        let mut direct = Vec::with_capacity(coords.len());
        for expr in coords {
            let ExprNode::Field {
                query,
                component,
                field,
            } = &self.plan.expressions[*expr]
            else {
                return None;
            };
            if query != query_name {
                return None;
            }
            direct.push(DirectSpatialCoord {
                component: component.clone(),
                field: field.clone(),
            });
        }
        Some(direct)
    }

    fn direct_spatial_point_for_entity(
        &mut self,
        entity: Entity,
        coords: &[DirectSpatialCoord],
    ) -> Result<SpatialPoint> {
        match coords {
            [x, y] => SpatialPoint::point2(
                self.entity_field_f64(entity, &x.component, &x.field)?,
                self.entity_field_f64(entity, &y.component, &y.field)?,
            ),
            [x, y, z] => SpatialPoint::point3(
                self.entity_field_f64(entity, &x.component, &x.field)?,
                self.entity_field_f64(entity, &y.component, &y.field)?,
                self.entity_field_f64(entity, &z.component, &z.field)?,
            ),
            _ => Err(EcsError::InvalidPlan(
                "spatial points must have 2 or 3 coordinates".to_string(),
            )),
        }
    }

    fn eval_expr_f64(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if let Some(value) = cache[expr_index] {
            return Ok(value);
        }
        let value = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => *value,
            ExprNode::LiteralI64(value) => *value as f64,
            ExprNode::LiteralBool(value) => bool_f64(*value),
            ExprNode::LiteralValue(value) => numeric_f64(value)?,
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.entity_field_f64(*entity, component, field)?
            }
            ExprNode::ResourceField { resource, field } => {
                numeric_f64(&self.world.resource_field(resource, field)?)?
            }
            ExprNode::InputState { name, code } => numeric_f64(
                &self
                    .world
                    .input_state(name, *code)
                    .unwrap_or_else(|| default_input_state_value(name)),
            )?,
            ExprNode::Unary { op, input } => {
                let input = self.eval_expr_f64(*input, ctx, cache)?;
                eval_unary_f64(op, input)?
            }
            ExprNode::Binary { op, left, right } => {
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if !truthy_f64(left) {
                        0.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if truthy_f64(left) {
                        1.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    let right = self.eval_expr_f64(*right, ctx, cache)?;
                    eval_binary_f64(op, left, right)?
                }
            }
            ExprNode::ContextJoin { predicate, .. } => {
                self.eval_expr_f64(*predicate, ctx, cache)?
            }
            ExprNode::Exists { query, predicate } => {
                bool_f64(truthy(&self.eval_exists(query, *predicate, ctx)?)?)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => numeric_f64(&self.eval_grouped_aggregate(
                kind,
                *relation,
                group_query.as_deref(),
                *value,
                *default,
                ctx,
            )?)?,
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => numeric_f64(&self.eval_spatial_metadata(relation, kind, *axis, ctx)?)?,
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => self.eval_spatial_aggregate_f64(
                expr_index, kind, relation, *value, *default, ctx, cache,
            )?,
            ExprNode::Attribute { input, .. } => self.eval_expr_f64(*input, ctx, cache)?,
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {
                return Err(EcsError::InvalidPlan(format!(
                    "expression {expr_index} is not numeric"
                )))
            }
        };
        cache[expr_index] = Some(value);
        Ok(value)
    }

    fn eval_spatial_aggregate_f64(
        &mut self,
        expr_index: usize,
        kind: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if cache[expr_index].is_none() {
            if let Some(origin_entity) = ctx.bindings.get(&relation.origin_query).copied() {
                if let Some(value) = self.precomputed_spatial_f64(expr_index, origin_entity) {
                    cache[expr_index] = Some(value);
                    return Ok(value);
                }
            }
            self.compute_spatial_aggregate_batch_f64(relation, ctx, cache)?;
        }
        if let Some(value) = cache[expr_index] {
            return Ok(value);
        }

        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        match kind {
            "any" => return Ok(bool_f64(count > 0)),
            "count" => return Ok(count as f64),
            _ => {}
        }
        let Some(value_expr) = value else {
            return numeric_f64(&aggregate_finish(
                kind,
                count,
                Vec::new(),
                default,
                self,
                ctx,
            )?);
        };
        if let Some(result) = self.try_direct_spatial_numeric_aggregate(
            kind,
            relation,
            value_expr,
            records.as_ref(),
            default,
            ctx,
        )? {
            return numeric_f64(&result);
        }
        if count == 0 {
            return numeric_f64(&aggregate_empty(kind, default, self, ctx)?);
        }
        let mut sum = 0.0;
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        for record in records.iter() {
            let mut joined = ctx.clone();
            joined
                .bindings
                .insert(relation.item_query.clone(), record.entity);
            let mut item_cache = vec![None; self.plan.expressions.len()];
            let value = self.eval_expr_f64(value_expr, &joined, &mut item_cache)?;
            sum += value;
            min_value = min_value.min(value);
            max_value = max_value.max(value);
        }
        match kind {
            "sum" => Ok(sum),
            "mean" => Ok(sum / count as f64),
            "min" => Ok(min_value),
            "max" => Ok(max_value),
            other => Err(EcsError::InvalidPlan(format!(
                "unsupported aggregate kind '{other}'"
            ))),
        }
    }

    fn spatial_batch_specs_for_relation(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Vec<SpatialBatchSpec>> {
        let spec_cache_key = (relation.id.clone(), relation.radius, relation.exact_filter);
        if let Some(specs) = self.spatial_batch_spec_cache.get(&spec_cache_key) {
            return Ok(specs.clone());
        }

        let mut specs = Vec::new();
        for (expr_index, expr) in self.plan.expressions.iter().enumerate() {
            let ExprNode::SpatialAggregate {
                kind,
                relation: candidate_relation,
                value,
                default,
            } = expr
            else {
                continue;
            };
            if candidate_relation != relation || default.is_some() {
                continue;
            }
            let value = match (kind.as_str(), value) {
                ("any" | "count", None) => SpatialBatchValue::Count,
                (_, Some(value_expr)) => {
                    if let Some((axis, minimum_distance)) =
                        self.match_neg_delta_over_clamped_distance(*value_expr, relation)?
                    {
                        SpatialBatchValue::NegDeltaOverDistance {
                            axis,
                            minimum_distance,
                        }
                    } else if let ExprNode::Field {
                        query,
                        component,
                        field,
                    } = &self.plan.expressions[*value_expr]
                    {
                        if query != &relation.item_query {
                            continue;
                        }
                        SpatialBatchValue::DirectField {
                            component: component.clone(),
                            field: field.clone(),
                        }
                    } else {
                        continue;
                    }
                }
                _ => continue,
            };
            specs.push(SpatialBatchSpec {
                expr_index,
                kind: kind.clone(),
                value,
            });
        }
        self.spatial_batch_spec_cache
            .insert(spec_cache_key, specs.clone());
        Ok(specs)
    }

    fn compute_spatial_aggregate_batch_f64(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<()> {
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() || specs.iter().all(|spec| cache[spec.expr_index].is_some()) {
            return Ok(());
        }

        let origin_entity = ctx
            .bindings
            .get(&relation.origin_query)
            .copied()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        if self.profile {
            self.profile_spatial_relation_misses += 1;
        }
        let records = self.build_spatial_relation_records(relation, ctx, origin_entity)?;
        let count = records.len();
        let dimensions = dimensions_len(relation.algorithm.dimensions)?;
        let needs_delta = specs
            .iter()
            .any(|spec| matches!(spec.value, SpatialBatchValue::NegDeltaOverDistance { .. }));
        let origin = if needs_delta {
            Some(self.eval_spatial_point(&relation.origin_position, ctx)?)
        } else {
            None
        };
        let mut accumulators = vec![SpatialBatchAccum::default(); specs.len()];
        for record in records.iter() {
            let mut distance_sq = 0.0;
            if let Some(origin) = &origin {
                for axis in 0..dimensions {
                    let delta = record.point.coord(axis) - origin.coord(axis);
                    distance_sq += delta * delta;
                }
            }
            for (index, spec) in specs.iter().enumerate() {
                let value = match &spec.value {
                    SpatialBatchValue::Count => 1.0,
                    SpatialBatchValue::DirectField { component, field } => {
                        self.entity_field_f64(record.entity, component, field)?
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => {
                        let origin = origin
                            .as_ref()
                            .expect("origin computed for delta aggregate");
                        let delta_axis = record.point.coord(*axis) - origin.coord(*axis);
                        -delta_axis / distance_sq.sqrt().max(*minimum_distance)
                    }
                };
                let accumulator = &mut accumulators[index];
                accumulator.count += 1;
                accumulator.sum += value;
                accumulator.min = accumulator.min.min(value);
                accumulator.max = accumulator.max.max(value);
            }
        }
        for (spec, accumulator) in specs.into_iter().zip(accumulators) {
            let value = match spec.kind.as_str() {
                "any" => bool_f64(count > 0),
                "count" => count as f64,
                "sum" => accumulator.sum,
                "mean" if accumulator.count > 0 => accumulator.sum / accumulator.count as f64,
                "min" if accumulator.count > 0 => accumulator.min,
                "max" if accumulator.count > 0 => accumulator.max,
                _ => continue,
            };
            cache[spec.expr_index] = Some(value);
        }
        Ok(())
    }

    fn eval_expr(&mut self, expr_index: usize, ctx: &EvalContext) -> Result<EcsValue> {
        if self.profile {
            self.profile_eval_calls += 1;
        }
        let use_local_cache = ctx.loop_items.is_empty()
            && self
                .local_expr_bindings
                .as_ref()
                .is_some_and(|bindings| bindings == &ctx.bindings);
        if use_local_cache {
            if let Some(cache) = self.local_expr_cache.as_ref() {
                if let Some(Some(value)) = cache.get(expr_index) {
                    if self.profile {
                        self.profile_expr_cache_hits += 1;
                    }
                    return Ok(value.clone());
                }
            }
            if self.profile {
                self.profile_expr_cache_misses += 1;
            }
        } else {
            let cache_key = self.expr_cache_key(expr_index, ctx);
            if let Some(key) = &cache_key {
                if let Some(value) = self.expr_cache.get(key) {
                    if self.profile {
                        self.profile_expr_cache_hits += 1;
                    }
                    return Ok(value.clone());
                }
            }
            if self.profile {
                self.profile_expr_cache_misses += 1;
            }
        }
        let result = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Ok(EcsValue::F64(*value)),
            ExprNode::LiteralI64(value) => Ok(EcsValue::I64(*value)),
            ExprNode::LiteralBool(value) => Ok(EcsValue::Bool(*value)),
            ExprNode::LiteralString(value) => Ok(EcsValue::String(value.clone())),
            ExprNode::LiteralValue(value) => Ok(value.clone()),
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.world.get_field(*entity, component, field)
            }
            ExprNode::ResourceField { resource, field } => {
                self.world.resource_field(resource, field)
            }
            ExprNode::Attribute { input, attribute } => {
                let input = *input;
                let attribute = attribute.clone();
                let value = self.eval_expr(input, ctx)?;
                match value {
                    EcsValue::Struct(fields) => fields.get(&attribute).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "struct value has no attribute '{attribute}'"
                        ))
                    }),
                    other => Err(EcsError::InvalidPlan(format!(
                        "attribute access expects a struct value, got {}",
                        other.kind_name()
                    ))),
                }
            }
            ExprNode::EventStream { event_type } => Ok(EcsValue::List(
                self.world
                    .read_events(event_type)?
                    .into_iter()
                    .map(|event| event.payload)
                    .collect(),
            )),
            ExprNode::ForEachItem { slot } => ctx.loop_items.get(slot).cloned().ok_or_else(|| {
                EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
            }),
            ExprNode::Unary { op, input } => {
                let op = op.clone();
                let input = *input;
                let input = self.eval_expr(input, ctx)?;
                eval_unary(&op, input)
            }
            ExprNode::Binary { op, left, right } => {
                let op = op.clone();
                let left = *left;
                let right = *right;
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr(left, ctx)?;
                    if !truthy(&left)? {
                        return Ok(EcsValue::Bool(false));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr(left, ctx)?;
                    if truthy(&left)? {
                        return Ok(EcsValue::Bool(true));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                let left = self.eval_expr(left, ctx)?;
                let right = self.eval_expr(right, ctx)?;
                eval_binary(&op, left, right)
            }
            ExprNode::InputState { name, code } => Ok(self
                .world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name))),
            ExprNode::ContextJoin { predicate, .. } => self.eval_expr(*predicate, ctx),
            ExprNode::Exists { query, predicate } => {
                let query = query.clone();
                self.eval_exists(&query, *predicate, ctx)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => {
                let kind = kind.clone();
                let group_query = group_query.clone();
                self.eval_grouped_aggregate(
                    &kind,
                    *relation,
                    group_query.as_deref(),
                    *value,
                    *default,
                    ctx,
                )
            }
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => {
                let relation = relation.clone();
                let kind = kind.clone();
                self.eval_spatial_metadata(&relation, &kind, *axis, ctx)
            }
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                let kind = kind.clone();
                let relation = relation.clone();
                self.eval_spatial_aggregate(&kind, &relation, *value, *default, ctx)
            }
        };
        if let Ok(value) = &result {
            if use_local_cache {
                if let Some(cache) = self.local_expr_cache.as_mut() {
                    if let Some(slot) = cache.get_mut(expr_index) {
                        *slot = Some(value.clone());
                    }
                }
            } else {
                let cache_key = self.expr_cache_key(expr_index, ctx);
                if let Some(key) = cache_key {
                    self.expr_cache.insert(key, value.clone());
                }
            }
        }
        result
    }

    fn expr_cache_key(&self, expr_index: usize, ctx: &EvalContext) -> Option<ExprCacheKey> {
        if !ctx.loop_items.is_empty() {
            return None;
        }
        match ctx.bindings.len() {
            0 => Some(ExprCacheKey::Empty(expr_index)),
            1 => ctx.bindings.iter().next().map(|(query, entity)| {
                ExprCacheKey::One(
                    expr_index,
                    *self.query_indices.get(query).unwrap_or(&usize::MAX),
                    entity.raw(),
                )
            }),
            _ => {
                let mut bindings = ctx
                    .bindings
                    .iter()
                    .map(|(query, entity)| {
                        (
                            *self.query_indices.get(query).unwrap_or(&usize::MAX),
                            entity.raw(),
                        )
                    })
                    .collect::<Vec<_>>();
                bindings.sort_by_key(|(query_index, _)| *query_index);
                Some(ExprCacheKey::Many(expr_index, bindings))
            }
        }
    }

    fn eval_exists(
        &mut self,
        query: &str,
        predicate: usize,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let mut query_names = BTreeSet::new();
        query_names.insert(query.to_string());
        self.collect_expr_queries(predicate, &mut query_names)?;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            self.report.rows_scanned += 1;
            if truthy(&self.eval_expr(predicate, &joined)?)? {
                return Ok(EcsValue::Bool(true));
            }
        }
        Ok(EcsValue::Bool(false))
    }

    fn eval_grouped_aggregate(
        &mut self,
        kind: &str,
        relation: usize,
        group_query: Option<&str>,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let Some(group_query) = group_query else {
            return Err(EcsError::InvalidPlan(
                "aggregate expressions need a group query".to_string(),
            ));
        };
        let Some(target_entity) = ctx.bindings.get(group_query).copied() else {
            return aggregate_empty(kind, default, self, ctx);
        };
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(relation, &mut query_names)?;
        if let Some(value) = value {
            self.collect_expr_queries(value, &mut query_names)?;
        }
        let mut values = Vec::new();
        let mut count = 0usize;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            if joined.bindings.get(group_query).copied() != Some(target_entity) {
                continue;
            }
            self.report.rows_scanned += 1;
            if !truthy(&self.eval_expr(relation, &joined)?)? {
                continue;
            }
            count += 1;
            if kind == "any" {
                return Ok(EcsValue::Bool(true));
            }
            if let Some(value_expr) = value {
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn eval_spatial_metadata(
        &mut self,
        relation: &SpatialRelationNode,
        kind: &str,
        axis: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let origin = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let item = self.eval_spatial_point(&relation.target_position, ctx)?;
        let mut delta = [0.0_f64; 3];
        for (axis, slot) in delta
            .iter_mut()
            .enumerate()
            .take(dimensions_len(relation.algorithm.dimensions)?)
        {
            *slot = item.coord(axis) - origin.coord(axis);
        }
        if kind == "delta" {
            let axis = axis.ok_or_else(|| {
                EcsError::InvalidPlan("spatial delta metadata requires an axis".to_string())
            })?;
            return Ok(EcsValue::F64(delta[axis]));
        }
        let distance_sq = delta.iter().map(|value| value * value).sum::<f64>();
        match kind {
            "distance_sq" => Ok(EcsValue::F64(distance_sq)),
            "distance" => Ok(EcsValue::F64(distance_sq.sqrt())),
            other => Err(EcsError::InvalidPlan(format!(
                "unsupported spatial metadata kind '{other}'"
            ))),
        }
    }

    fn eval_spatial_aggregate(
        &mut self,
        kind: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        if kind == "any" {
            return Ok(EcsValue::Bool(count > 0));
        }
        if let Some(value_expr) = value {
            if let Some(result) = self.try_direct_spatial_numeric_aggregate(
                kind,
                relation,
                value_expr,
                records.as_ref(),
                default,
                ctx,
            )? {
                return Ok(result);
            }
        }
        let mut values = Vec::new();
        if let Some(value_expr) = value {
            values.reserve(records.len());
            for record in records.iter() {
                let mut joined = ctx.clone();
                joined
                    .bindings
                    .insert(relation.item_query.clone(), record.entity);
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn try_direct_spatial_numeric_aggregate(
        &mut self,
        kind: &str,
        relation: &SpatialRelationNode,
        value_expr: usize,
        records: &[SpatialRecord],
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<Option<EcsValue>> {
        let aggregate_start = self.profile.then(Instant::now);
        if kind == "sum" {
            if let Some((axis, minimum_distance)) =
                self.match_neg_delta_over_clamped_distance(value_expr, relation)?
            {
                let origin = self.eval_spatial_point(&relation.origin_position, ctx)?;
                let dimensions = dimensions_len(relation.algorithm.dimensions)?;
                let mut sum = 0.0;
                for record in records {
                    let mut distance_sq = 0.0_f64;
                    for axis_index in 0..dimensions {
                        let delta = record.point.coord(axis_index) - origin.coord(axis_index);
                        distance_sq += delta * delta;
                    }
                    let delta_axis = record.point.coord(axis) - origin.coord(axis);
                    sum += -delta_axis / distance_sq.sqrt().max(minimum_distance);
                }
                if let Some(start) = &aggregate_start {
                    self.profile_direct_aggregate_hits += 1;
                    self.profile_direct_aggregate_nanos += start.elapsed().as_nanos();
                }
                return Ok(Some(EcsValue::F64(sum)));
            }
        }

        let ExprNode::Field {
            query,
            component,
            field,
        } = &self.plan.expressions[value_expr]
        else {
            return Ok(None);
        };
        if query != &relation.item_query {
            return Ok(None);
        }

        if records.is_empty() {
            return match kind {
                "sum" => Ok(Some(EcsValue::F64(0.0))),
                "min" | "max" | "mean" => aggregate_empty(kind, default, self, ctx).map(Some),
                _ => Ok(None),
            };
        }

        let mut sum = 0.0;
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        for record in records {
            let value = self.entity_field_f64(record.entity, component, field)?;
            sum += value;
            if value < min_value {
                min_value = value;
            }
            if value > max_value {
                max_value = value;
            }
        }

        let result = match kind {
            "sum" => Some(EcsValue::F64(sum)),
            "mean" => Some(EcsValue::F64(sum / records.len() as f64)),
            "min" => Some(EcsValue::F64(min_value)),
            "max" => Some(EcsValue::F64(max_value)),
            _ => None,
        };
        if result.is_some() {
            if let Some(start) = &aggregate_start {
                self.profile_direct_aggregate_hits += 1;
                self.profile_direct_aggregate_nanos += start.elapsed().as_nanos();
            }
        }
        Ok(result)
    }

    fn match_neg_delta_over_clamped_distance(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Result<Option<(usize, f64)>> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return Ok(None);
        };
        if op != "truediv" && op != "/" {
            return Ok(None);
        }

        let Some(axis) = self.match_neg_spatial_delta(*left, relation) else {
            return Ok(None);
        };
        let Some(minimum_distance) = self.match_clamped_spatial_distance(*right, relation)? else {
            return Ok(None);
        };
        Ok(Some((axis, minimum_distance)))
    }

    fn match_neg_spatial_delta(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Option<usize> {
        let ExprNode::Unary { op, input } = &self.plan.expressions[expr_index] else {
            return None;
        };
        if op != "neg" && op != "-" {
            return None;
        }
        let ExprNode::SpatialMetadata {
            relation: metadata_relation,
            kind,
            axis,
        } = &self.plan.expressions[*input]
        else {
            return None;
        };
        if kind == "delta" && spatial_relations_same_base(metadata_relation, relation) {
            *axis
        } else {
            None
        }
    }

    fn match_clamped_spatial_distance(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Result<Option<f64>> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return Ok(None);
        };
        if op != "max" {
            return Ok(None);
        }
        if self.is_spatial_distance(*left, relation) {
            return Ok(literal_expr_numeric(&self.plan.expressions[*right]));
        }
        if self.is_spatial_distance(*right, relation) {
            return Ok(literal_expr_numeric(&self.plan.expressions[*left]));
        }
        Ok(None)
    }

    fn is_spatial_distance(&self, expr_index: usize, relation: &SpatialRelationNode) -> bool {
        matches!(
            &self.plan.expressions[expr_index],
            ExprNode::SpatialMetadata {
                relation: metadata_relation,
                kind,
                axis: None,
            } if kind == "distance" && spatial_relations_same_base(metadata_relation, relation)
        )
    }

    fn match_spatial_distance_filter(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Option<SpatialDistanceFilter> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return None;
        };
        let comparison = comparison_from_op(op)?;
        if let Some(filter) =
            self.match_spatial_distance_filter_side(*left, *right, comparison, relation)
        {
            return Some(filter);
        }
        self.match_spatial_distance_filter_side(
            *right,
            *left,
            reverse_comparison(comparison),
            relation,
        )
    }

    fn match_spatial_distance_filter_side(
        &self,
        metadata_expr: usize,
        literal_expr: usize,
        comparison: NumericComparison,
        relation: &SpatialRelationNode,
    ) -> Option<SpatialDistanceFilter> {
        let threshold = literal_expr_numeric(&self.plan.expressions[literal_expr])?;
        let ExprNode::SpatialMetadata {
            relation: metadata_relation,
            kind,
            axis: None,
        } = &self.plan.expressions[metadata_expr]
        else {
            return None;
        };
        if !spatial_relations_same_base(metadata_relation, relation) {
            return None;
        }
        match kind.as_str() {
            "distance" => Some(SpatialDistanceFilter::Distance {
                comparison,
                threshold,
            }),
            "distance_sq" => Some(SpatialDistanceFilter::DistanceSq {
                comparison,
                threshold,
            }),
            _ => None,
        }
    }

    fn spatial_relation_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Arc<Vec<SpatialRecord>>> {
        let origin_entity = ctx
            .bindings
            .get(&relation.origin_query)
            .copied()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        let cache_key = (
            relation.id.clone(),
            relation.radius,
            relation.exact_filter,
            relation.include_self,
            relation.pair_policy.clone(),
            origin_entity.raw(),
        );
        if let Some(records) = self.spatial_relation_cache.get(&cache_key) {
            if self.profile {
                self.profile_spatial_relation_hits += 1;
            }
            return Ok(Arc::clone(records));
        }
        if self.profile {
            self.profile_spatial_relation_misses += 1;
        }

        let records =
            Arc::new(self.build_spatial_relation_records(relation, ctx, origin_entity)?);
        self.spatial_relation_cache
            .insert(cache_key, Arc::clone(&records));
        Ok(records)
    }

    fn build_spatial_relation_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
        origin_entity: Entity,
    ) -> Result<Vec<SpatialRecord>> {
        let origin_point = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let origin_bounds = relation
            .origin_bounds
            .as_ref()
            .map(|bounds| self.eval_spatial_bounds(bounds, ctx))
            .transpose()?;
        let radius = relation
            .radius
            .map(|expr| {
                self.eval_expr(expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .transpose()?;
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let profile = self.profile;
        let mut candidates = Vec::new();
        let index_start = profile.then(Instant::now);
        let index = self.ensure_spatial_index(relation, ctx)?;
        let index_nanos = index_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        let query_start = profile.then(Instant::now);
        if let Some(bounds) = &origin_bounds {
            index.query_aabb(bounds, &mut candidates)?;
        } else if let Some(radius) = query_radius {
            index.query_radius_unordered(&origin_point, radius, &mut candidates)?;
        } else {
            let bounds = point_bounds(&origin_point)?;
            index.query_aabb(&bounds, &mut candidates)?;
        }
        let query_nanos = query_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        if profile {
            self.profile_spatial_index_nanos += index_nanos;
            self.profile_spatial_query_nanos += query_nanos;
        }
        self.report.spatial_candidate_rows += candidates.len();
        let filter_start = profile.then(Instant::now);
        let mut records = Vec::new();
        for record in candidates {
            if !relation.include_self && record.entity == origin_entity {
                continue;
            }
            if relation.pair_policy == "unique_unordered"
                && record.entity.raw() <= origin_entity.raw()
            {
                self.report.spatial_deduplicated_pairs += 1;
                continue;
            }
            if let Some(bounds) = &origin_bounds {
                let record_bounds = record
                    .bounds
                    .clone()
                    .unwrap_or_else(|| point_bounds(&record.point).expect("point bounds"));
                if !bounds.overlaps(&record_bounds)? {
                    self.report.spatial_false_positive_rows += 1;
                    continue;
                }
            }
            if let Some(distance_filter) = distance_filter {
                if !distance_filter.matches(origin_point.distance_squared(&record.point)?) {
                    continue;
                }
            } else if let Some(exact_filter) = relation.exact_filter {
                let mut joined = ctx.clone();
                joined
                    .bindings
                    .insert(relation.item_query.clone(), record.entity);
                if !truthy(&self.eval_expr(exact_filter, &joined)?)? {
                    continue;
                }
            }
            self.report.rows_scanned += 1;
            self.report.spatial_exact_rows += 1;
            records.push(record);
        }
        if let Some(start) = filter_start {
            self.profile_spatial_filter_nanos += start.elapsed().as_nanos();
        }
        Ok(records)
    }

    fn persist_spatial_index_cache(&mut self) {
        for (index_id, index) in self.spatial_indexes.drain() {
            let Some((signature, structural_revision, field_revision)) =
                self.spatial_index_metadata.remove(&index_id)
            else {
                continue;
            };
            self.world.store_spatial_index_cache(
                index_id,
                CachedSpatialIndex {
                    index,
                    signature,
                    structural_revision,
                    field_revision,
                },
            );
        }
    }

    fn report_algorithm_use(&mut self, index: &BuiltSpatialIndex) {
        match index {
            BuiltSpatialIndex::HashGrid(_) | BuiltSpatialIndex::DirectPointHashGrid(_) => {
                self.report.spatial_algorithm_hash_grid += 1
            }
            BuiltSpatialIndex::Quadtree(_) => self.report.spatial_algorithm_quadtree += 1,
            BuiltSpatialIndex::Octree(_) => self.report.spatial_algorithm_octree += 1,
            BuiltSpatialIndex::Hilbert(_) => self.report.spatial_algorithm_hilbert_curve += 1,
        }
    }

    fn spatial_dependency_revision(&self, relation: &SpatialRelationNode) -> u64 {
        let mut dependencies = Vec::new();
        let mut complete = true;
        for expr in &relation.target_position {
            complete &= self.collect_spatial_field_dependencies(
                *expr,
                &relation.item_query,
                &mut dependencies,
                &mut HashSet::new(),
            );
        }
        if let Some(bounds) = &relation.target_bounds {
            for expr in bounds.minimum.iter().chain(bounds.maximum.iter()) {
                complete &= self.collect_spatial_field_dependencies(
                    *expr,
                    &relation.item_query,
                    &mut dependencies,
                    &mut HashSet::new(),
                );
            }
        }
        if complete && !dependencies.is_empty() {
            dependencies
                .iter()
                .map(|(component, field)| self.world.component_field_revision(component, field))
                .max()
                .unwrap_or(0)
        } else {
            self.world.field_revision()
        }
    }

    fn collect_spatial_field_dependencies(
        &self,
        expr_index: usize,
        query_name: &str,
        dependencies: &mut Vec<(String, String)>,
        visiting: &mut HashSet<usize>,
    ) -> bool {
        if !visiting.insert(expr_index) {
            return true;
        }
        let complete = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_) => true,
            ExprNode::Field {
                query,
                component,
                field,
            } if query == query_name => {
                dependencies.push((component.clone(), field.clone()));
                true
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.collect_spatial_field_dependencies(*input, query_name, dependencies, visiting)
            }
            ExprNode::Binary { left, right, .. } => {
                self.collect_spatial_field_dependencies(*left, query_name, dependencies, visiting)
                    & self.collect_spatial_field_dependencies(
                        *right,
                        query_name,
                        dependencies,
                        visiting,
                    )
            }
            _ => false,
        };
        visiting.remove(&expr_index);
        complete
    }

    fn spatial_index_signature(&self, relation: &SpatialRelationNode) -> String {
        format!(
            "{};item_query_fingerprint={}",
            spatial_index_base_signature(relation),
            self.query_fingerprint(&relation.item_query)
        )
    }

    fn spatial_index_cache_key(&self, relation: &SpatialRelationNode) -> String {
        format!(
            "{}|{}",
            relation.index_id,
            self.spatial_index_signature(relation)
        )
    }

    fn query_fingerprint(&self, query_name: &str) -> u64 {
        let mut hasher = DefaultHasher::new();
        query_name.hash(&mut hasher);
        if let Some(query) = self
            .plan
            .queries
            .iter()
            .find(|query| query.name == query_name)
        {
            query.filter.hash(&mut hasher);
            query.allowed_entities.hash(&mut hasher);
        }
        hasher.finish()
    }

    fn take_fresh_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Option<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let Some(cached) = self.world.take_spatial_index_cache(&index_key) else {
            return None;
        };
        if cached.signature == signature
            && cached.structural_revision == structural_revision
            && cached.field_revision == field_revision
        {
            self.report.spatial_index_reuses += 1;
            self.spatial_index_metadata
                .insert(index_key, (signature, structural_revision, field_revision));
            return Some(cached.index);
        }
        self.world.store_spatial_index_cache(index_key, cached);
        None
    }

    fn build_or_update_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        records: Vec<SpatialRecord>,
    ) -> Result<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let index = if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
            if cached.signature == signature {
                if cached.structural_revision == structural_revision
                    && cached.field_revision == field_revision
                {
                    self.report.spatial_index_reuses += 1;
                    self.spatial_index_metadata
                        .insert(index_key, (signature, structural_revision, field_revision));
                    return Ok(cached.index);
                }
                if should_try_incremental_spatial_update(
                    records.len(),
                    cached.field_revision,
                    field_revision,
                ) {
                    if cached.index.update_incremental(&records)? {
                        self.report.spatial_index_incremental_updates += 1;
                    } else {
                        self.report.spatial_indexes_built += 1;
                        self.report.spatial_index_full_rebuilds += 1;
                    }
                } else {
                    cached.index.build(&records)?;
                    self.report.spatial_indexes_built += 1;
                    self.report.spatial_index_full_rebuilds += 1;
                }
                cached.index
            } else {
                let mut index = build_spatial_index(&relation.algorithm)?;
                index.build(&records)?;
                self.report.spatial_indexes_built += 1;
                self.report.spatial_index_full_rebuilds += 1;
                index
            }
        } else {
            let mut index = build_spatial_index(&relation.algorithm)?;
            index.build(&records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            index
        };
        self.spatial_index_metadata
            .insert(index_key, (signature, structural_revision, field_revision));
        Ok(index)
    }

    fn ensure_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<&BuiltSpatialIndex> {
        let index_key = self.spatial_index_cache_key(relation);
        if self.spatial_indexes.contains_key(&index_key) {
            self.report.spatial_index_reuses += 1;
        } else if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        } else {
            let records = self.build_spatial_records(relation, ctx)?;
            let index = self.build_or_update_spatial_index(relation, records)?;
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        }
        self.spatial_indexes.get(&index_key).ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial index '{}' was not built",
                relation.index_id
            ))
        })
    }

    fn build_spatial_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Vec<SpatialRecord>> {
        let rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let mut records = Vec::with_capacity(rows.len());
        for entity in rows {
            let mut item_ctx = ctx.clone();
            item_ctx
                .bindings
                .insert(relation.item_query.clone(), entity);
            let point = self.eval_spatial_point(&relation.target_position, &item_ctx)?;
            let bounds = relation
                .target_bounds
                .as_ref()
                .map(|bounds| self.eval_spatial_bounds(bounds, &item_ctx))
                .transpose()?;
            records.push(SpatialRecord {
                entity,
                point,
                bounds,
            });
        }
        Ok(records)
    }

    fn eval_spatial_point(&mut self, coords: &[usize], ctx: &EvalContext) -> Result<SpatialPoint> {
        let values = coords
            .iter()
            .map(|expr| {
                self.eval_expr(*expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .collect::<Result<Vec<_>>>()?;
        match values.as_slice() {
            [x, y] => SpatialPoint::point2(*x, *y),
            [x, y, z] => SpatialPoint::point3(*x, *y, *z),
            _ => Err(EcsError::InvalidPlan(
                "spatial points must have 2 or 3 coordinates".to_string(),
            )),
        }
    }

    fn eval_spatial_bounds(
        &mut self,
        bounds: &SpatialBoundsExprNode,
        ctx: &EvalContext,
    ) -> Result<SpatialAabb> {
        let minimum = self.eval_spatial_point(&bounds.minimum, ctx)?;
        let maximum = self.eval_spatial_point(&bounds.maximum, ctx)?;
        SpatialAabb::new(minimum, maximum)
    }

    fn expr_queries_cached(
        &self,
        expr_index: usize,
        cache: &mut HashMap<usize, BTreeSet<String>>,
    ) -> Result<BTreeSet<String>> {
        if let Some(queries) = cache.get(&expr_index) {
            return Ok(queries.clone());
        }
        let mut out = BTreeSet::new();
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                out.extend(self.expr_queries_cached(*input, cache)?);
            }
            ExprNode::Binary { left, right, .. } => {
                out.extend(self.expr_queries_cached(*left, cache)?);
                out.extend(self.expr_queries_cached(*right, cache)?);
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                out.extend(self.expr_queries_cached(*predicate, cache)?);
            }
            ExprNode::Exists { query, predicate } => {
                out.extend(self.expr_queries_cached(*predicate, cache)?);
                out.remove(query);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        cache.insert(expr_index, out.clone());
        Ok(out)
    }

    fn collect_expr_queries(&self, expr_index: usize, out: &mut BTreeSet<String>) -> Result<()> {
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Attribute { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Binary { left, right, .. } => {
                self.collect_expr_queries(*left, out)?;
                self.collect_expr_queries(*right, out)?;
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                self.collect_expr_queries(*predicate, out)?;
            }
            ExprNode::Exists { query, predicate } => {
                let mut inner = BTreeSet::new();
                self.collect_expr_queries(*predicate, &mut inner)?;
                inner.remove(query);
                out.extend(inner);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        Ok(())
    }
}

fn fast_field_array_value(array: &FastFieldArray, entity: Entity) -> Result<f64> {
    let Some(Some((generation, value))) = array.values.get(entity.index as usize) else {
        return Err(EcsError::InvalidPlan(format!(
            "missing cached f64 value for entity {}:{} field {}.{}",
            entity.index, entity.generation, array.component, array.field
        )));
    };
    if *generation != entity.generation {
        return Err(EcsError::InvalidPlan(format!(
            "fast numeric field array has stale entity generation for {}:{}",
            entity.index, entity.generation
        )));
    };
    Ok(*value)
}

fn fast_field_array_record_values(
    array: &FastFieldArray,
    records: &[DirectPointRecord],
) -> Result<Vec<f64>> {
    records
        .iter()
        .map(|record| fast_field_array_value(array, record.entity))
        .collect()
}

fn point_from_row_arrays(arrays: &[Vec<f64>], row_index: usize) -> Result<SpatialPoint> {
    let row_value = |values: &Vec<f64>| -> Result<f64> {
        values.get(row_index).copied().ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial coordinate cache missing query row {row_index}"
            ))
        })
    };
    match arrays {
        [x, y] => SpatialPoint::point2(row_value(x)?, row_value(y)?),
        [x, y, z] => SpatialPoint::point3(row_value(x)?, row_value(y)?, row_value(z)?),
        _ => Err(EcsError::InvalidPlan(
            "spatial points must have 2 or 3 coordinates".to_string(),
        )),
    }
}

fn fast_aggregate_kind(kind: &str) -> Option<FastAggregateKind> {
    match kind {
        "any" => Some(FastAggregateKind::Any),
        "count" => Some(FastAggregateKind::Count),
        "sum" => Some(FastAggregateKind::Sum),
        "mean" => Some(FastAggregateKind::Mean),
        "min" => Some(FastAggregateKind::Min),
        "max" => Some(FastAggregateKind::Max),
        _ => None,
    }
}

fn spatial_result_values_are_dense(batches: &[FastDirectSpatialRelationBatch]) -> bool {
    batches.iter().all(|batch| {
        batch.specs.iter().all(|spec| {
            matches!(
                spec.kind,
                FastAggregateKind::Any | FastAggregateKind::Count | FastAggregateKind::Sum
            )
        })
    })
}

fn add_query_access(map: &mut HashMap<String, Vec<String>>, component: &str, query: &str) {
    let queries = map.entry(component.to_string()).or_default();
    if !queries.iter().any(|candidate| candidate == query) {
        queries.push(query.to_string());
    }
}

fn collect_action_query_access(
    world: &World,
    plan: &PhysicalPlan,
    action_index: usize,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    match &plan.actions[action_index] {
        ActionNode::Noop => {}
        ActionNode::SetField { target, value } => {
            collect_expr_query_reads(plan, *value, access)?;
            match &plan.expressions[*target] {
                ExprNode::Field {
                    query,
                    component,
                    field,
                } => {
                    add_query_access(&mut access.component_writes, component, query);
                    if matches!(
                        world.storage_type_for_field(component, field)?,
                        StorageType::Float32 | StorageType::Float64
                    ) {
                        access.f64_write_targets.push(F64WriteTarget {
                            query: query.clone(),
                            component: component.clone(),
                            field: field.clone(),
                        });
                    } else {
                        access.copyback_eligible = false;
                    }
                }
                ExprNode::ResourceField { resource, .. } => {
                    access.resource_writes.insert(resource.clone());
                    access.copyback_eligible = false;
                }
                _ => access.copyback_eligible = false,
            }
        }
        ActionNode::Sequence(children) | ActionNode::Parallel(children) => {
            for child in children {
                collect_action_query_access(world, plan, *child, access)?;
            }
        }
        ActionNode::When {
            condition,
            then_action,
            otherwise_action,
        } => {
            collect_expr_query_reads(plan, *condition, access)?;
            collect_action_query_access(world, plan, *then_action, access)?;
            if let Some(otherwise_action) = otherwise_action {
                collect_action_query_access(world, plan, *otherwise_action, access)?;
            }
        }
        ActionNode::ForEach { source, action, .. } => {
            collect_expr_query_reads(plan, *source, access)?;
            collect_action_query_access(world, plan, *action, access)?;
        }
        ActionNode::EmitEvent { event_type, value } => {
            collect_expr_query_reads(plan, *value, access)?;
            access.event_writes.insert(event_type.clone());
            access.copyback_eligible = false;
        }
        ActionNode::AddComponent {
            component, value, ..
        } => {
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            access
                .component_writes
                .entry(component.clone())
                .or_default();
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::RemoveComponent { component, .. } => {
            access
                .component_writes
                .entry(component.clone())
                .or_default();
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::AddTag { tag, .. } | ActionNode::RemoveTag { tag, .. } => {
            access.hidden_writes.insert(format!("tag:{tag}"));
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::Despawn { .. } => {
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::Udf {
            descriptor,
            args,
            side_effects,
        } => {
            for arg in args {
                collect_expr_query_reads(plan, *arg, access)?;
            }
            access.hidden_reads.insert(format!("udf:{descriptor}"));
            if *side_effects {
                access.structural = true;
            }
            access.copyback_eligible = false;
        }
    }
    Ok(())
}

fn collect_spatial_relation_query_reads(
    plan: &PhysicalPlan,
    relation: &SpatialRelationNode,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    access
        .hidden_reads
        .insert(format!("spatial:{}", relation.index_id));
    for index in relation
        .origin_position
        .iter()
        .chain(relation.target_position.iter())
    {
        collect_expr_query_reads(plan, *index, access)?;
    }
    if let Some(radius) = relation.radius {
        collect_expr_query_reads(plan, radius, access)?;
    }
    for bounds in relation
        .origin_bounds
        .iter()
        .chain(relation.target_bounds.iter())
    {
        for index in bounds.minimum.iter().chain(bounds.maximum.iter()) {
            collect_expr_query_reads(plan, *index, access)?;
        }
    }
    if let Some(exact_filter) = relation.exact_filter {
        collect_expr_query_reads(plan, exact_filter, access)?;
    }
    Ok(())
}

fn collect_expr_query_reads(
    plan: &PhysicalPlan,
    expr_index: usize,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    match &plan.expressions[expr_index] {
        ExprNode::Field {
            query, component, ..
        } => add_query_access(&mut access.component_reads, component, query),
        ExprNode::ResourceField { resource, .. } => {
            access.resource_reads.insert(resource.clone());
        }
        ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
            collect_expr_query_reads(plan, *input, access)?;
        }
        ExprNode::Binary { left, right, .. } => {
            collect_expr_query_reads(plan, *left, access)?;
            collect_expr_query_reads(plan, *right, access)?;
        }
        ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
            collect_expr_query_reads(plan, *predicate, access)?;
        }
        ExprNode::Aggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_expr_query_reads(plan, *relation, access)?;
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_query_reads(plan, *default, access)?;
            }
        }
        ExprNode::InputState { name, .. } => {
            access.hidden_reads.insert(format!("input:{name}"));
        }
        ExprNode::EventStream { event_type } => {
            access.event_reads.insert(event_type.clone());
        }
        ExprNode::SpatialMetadata { relation, .. } => {
            collect_spatial_relation_query_reads(plan, relation, access)?;
        }
        ExprNode::SpatialAggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_spatial_relation_query_reads(plan, relation, access)?;
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_query_reads(plan, *default, access)?;
            }
        }
        ExprNode::LiteralF64(_)
        | ExprNode::LiteralI64(_)
        | ExprNode::LiteralBool(_)
        | ExprNode::LiteralString(_)
        | ExprNode::LiteralValue(_)
        | ExprNode::ForEachItem { .. } => {}
    }
    Ok(())
}

fn sets_intersect(left: &HashSet<String>, right: &HashSet<String>) -> bool {
    left.iter().any(|value| right.contains(value))
}

fn query_sets_disjoint(
    left_plan: usize,
    left_queries: &[String],
    right_plan: usize,
    right_queries: &[String],
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    if left_queries.is_empty() || right_queries.is_empty() {
        return false;
    }
    for left_query in left_queries {
        let Some(left_rows) = query_sets.get(&(left_plan, left_query.clone())) else {
            return false;
        };
        for right_query in right_queries {
            let Some(right_rows) = query_sets.get(&(right_plan, right_query.clone())) else {
                return false;
            };
            if left_rows.iter().any(|entity| right_rows.contains(entity)) {
                return false;
            }
        }
    }
    true
}

fn component_query_access_conflicts(
    writer: &HashMap<String, Vec<String>>,
    reader: &HashMap<String, Vec<String>>,
    writer_plan: usize,
    reader_plan: usize,
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    for (component, write_queries) in writer {
        if let Some(read_queries) = reader.get(component) {
            if !query_sets_disjoint(
                writer_plan,
                write_queries,
                reader_plan,
                read_queries,
                query_sets,
            ) {
                return true;
            }
        }
    }
    false
}

fn query_access_conflicts(
    left: &QueryAccessSummary,
    left_index: usize,
    right: &QueryAccessSummary,
    right_index: usize,
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    if left.structural || right.structural {
        return true;
    }
    if sets_intersect(&left.resource_writes, &right.resource_writes)
        || sets_intersect(&left.resource_writes, &right.resource_reads)
        || sets_intersect(&right.resource_writes, &left.resource_reads)
        || sets_intersect(&left.event_writes, &right.event_writes)
        || sets_intersect(&left.event_writes, &right.event_reads)
        || sets_intersect(&right.event_writes, &left.event_reads)
        || sets_intersect(&left.hidden_writes, &right.hidden_writes)
        || sets_intersect(&left.hidden_writes, &right.hidden_reads)
        || sets_intersect(&right.hidden_writes, &left.hidden_reads)
    {
        return true;
    }
    component_query_access_conflicts(
        &left.component_writes,
        &right.component_writes,
        left_index,
        right_index,
        query_sets,
    ) || component_query_access_conflicts(
        &left.component_writes,
        &right.component_reads,
        left_index,
        right_index,
        query_sets,
    ) || component_query_access_conflicts(
        &right.component_writes,
        &left.component_reads,
        right_index,
        left_index,
        query_sets,
    )
}

fn query_rows_for_world(
    world: &mut World,
    plan: &PhysicalPlan,
    query_name: &str,
) -> Result<Vec<Entity>> {
    let query = plan
        .queries
        .iter()
        .find(|query| query.name == query_name)
        .ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
    let mut rows = world.query_filter(query.filter.clone())?;
    if let Some(allowed) = &query.allowed_entities {
        let allowed = allowed
            .iter()
            .map(|entity| entity.raw())
            .collect::<HashSet<_>>();
        rows.retain(|entity| allowed.contains(&entity.raw()));
    }
    Ok(rows)
}

fn process_fast_spatial_record(
    relation: &SpatialRelationNode,
    batches: &[FastDirectSpatialRelationBatch],
    item_field_arrays: &[FastFieldArray],
    item_record_field_arrays: Option<&[Vec<f64>]>,
    origin_entity: Entity,
    origin_point: &SpatialPoint,
    record_index: Option<usize>,
    record_entity: Entity,
    record_point: &SpatialPoint,
    distance_sq: f64,
    accumulators: &mut [Vec<SpatialBatchAccum>],
    exact_counts: &mut [usize],
    counters: &mut SpatialLocalCounters,
) -> Result<()> {
    counters.candidate_rows += 1;
    if !relation.include_self && record_entity == origin_entity {
        return Ok(());
    }
    if relation.pair_policy == "unique_unordered" && record_entity.raw() <= origin_entity.raw() {
        counters.deduplicated_pairs += 1;
        return Ok(());
    }
    for (batch_index, batch) in batches.iter().enumerate() {
        if distance_sq > batch.query_radius_sq {
            continue;
        }
        if let Some(distance_filter) = batch.distance_filter {
            if !distance_filter.matches(distance_sq) {
                continue;
            }
        }
        exact_counts[batch_index] += 1;
        counters.rows_scanned += 1;
        counters.exact_rows += 1;
        let mut inverse_distance_cache: Option<(f64, f64)> = None;
        for (spec_index, spec) in batch.specs.iter().enumerate() {
            if matches!(spec.kind, FastAggregateKind::Any | FastAggregateKind::Count) {
                continue;
            }
            let value = match &spec.value {
                FastSpatialBatchValue::Count => 1.0,
                FastSpatialBatchValue::DirectField { array_index } => {
                    if let (Some(record_arrays), Some(record_index)) =
                        (item_record_field_arrays, record_index)
                    {
                        record_arrays[*array_index][record_index]
                    } else {
                        fast_field_array_value(&item_field_arrays[*array_index], record_entity)?
                    }
                }
                FastSpatialBatchValue::DirectPointCoord { axis } => record_point.coord(*axis),
                FastSpatialBatchValue::NegDeltaOverDistance {
                    axis,
                    minimum_distance,
                } => {
                    let inverse_distance = match inverse_distance_cache {
                        Some((cached_minimum, value)) if cached_minimum == *minimum_distance => {
                            value
                        }
                        _ => {
                            let value = 1.0 / distance_sq.sqrt().max(*minimum_distance);
                            inverse_distance_cache = Some((*minimum_distance, value));
                            value
                        }
                    };
                    let delta_axis = record_point.coord(*axis) - origin_point.coord(*axis);
                    -delta_axis * inverse_distance
                }
            };
            let accumulator = &mut accumulators[batch_index][spec_index];
            match spec.kind {
                FastAggregateKind::Sum => {
                    accumulator.sum += value;
                }
                FastAggregateKind::Mean => {
                    accumulator.count += 1;
                    accumulator.sum += value;
                }
                FastAggregateKind::Min => {
                    accumulator.count += 1;
                    accumulator.min = accumulator.min.min(value);
                }
                FastAggregateKind::Max => {
                    accumulator.count += 1;
                    accumulator.max = accumulator.max.max(value);
                }
                FastAggregateKind::Any | FastAggregateKind::Count => {}
            }
        }
    }
    Ok(())
}

fn compile_f64_readonly_program<'a>(
    plan: &PhysicalPlan,
    _world: &World,
    query_name: &str,
    numeric_field_cache: &'a HashMap<String, HashMap<String, Vec<Option<(u32, f64)>>>>,
    numeric_field_cache_rows: &'a HashMap<String, HashMap<String, Vec<f64>>>,
    spatial_precomputed_f64: &'a HashMap<usize, Vec<Option<(u32, f64)>>>,
    spatial_precomputed_f64_rows: &'a HashMap<usize, SpatialF64RowArray>,
) -> CompiledF64ReadOnlyProgram<'a> {
    let mut expressions = Vec::with_capacity(plan.expressions.len());
    let mut field_arrays = Vec::new();
    let mut field_array_slots: HashMap<(String, String), usize> = HashMap::new();
    let mut spatial_arrays = Vec::new();
    for (expr_index, expr) in plan.expressions.iter().enumerate() {
        let compiled = match expr {
            ExprNode::LiteralF64(value) => CompiledF64Expr::Literal(*value),
            ExprNode::LiteralI64(value) => CompiledF64Expr::Literal(*value as f64),
            ExprNode::LiteralBool(value) => CompiledF64Expr::Literal(bool_f64(*value)),
            ExprNode::LiteralValue(value) => match numeric_f64(value) {
                Ok(value) => CompiledF64Expr::Literal(value),
                Err(error) => CompiledF64Expr::Unsupported(error.to_string()),
            },
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                if query != query_name {
                    CompiledF64Expr::Unsupported(format!(
                        "readonly f64 evaluator cannot read unbound query '{query}'"
                    ))
                } else if let Some(values) = numeric_field_cache_rows
                    .get(component)
                    .and_then(|fields| fields.get(field))
                {
                    let key = (component.clone(), field.clone());
                    let slot = if let Some(slot) = field_array_slots.get(&key) {
                        *slot
                    } else {
                        let slot = field_arrays.len();
                        field_arrays.push(CompiledF64Array::QueryRows(values.as_slice()));
                        field_array_slots.insert(key, slot);
                        slot
                    };
                    CompiledF64Expr::Field(slot)
                } else if let Some(values) = numeric_field_cache
                    .get(component)
                    .and_then(|fields| fields.get(field))
                {
                    let key = (component.clone(), field.clone());
                    let slot = if let Some(slot) = field_array_slots.get(&key) {
                        *slot
                    } else {
                        let slot = field_arrays.len();
                        field_arrays.push(CompiledF64Array::SparseEntity(values.as_slice()));
                        field_array_slots.insert(key, slot);
                        slot
                    };
                    CompiledF64Expr::Field(slot)
                } else {
                    CompiledF64Expr::Unsupported(format!(
                        "numeric field cache missing field '{component}.{field}'"
                    ))
                }
            }
            ExprNode::ResourceField { resource, field } => CompiledF64Expr::ResourceField {
                resource: resource.clone(),
                field: field.clone(),
            },
            ExprNode::InputState { name, code } => CompiledF64Expr::InputState {
                name: name.clone(),
                code: *code,
            },
            ExprNode::Unary { op, input } => match f64_unary_op(op) {
                Some(op) => CompiledF64Expr::Unary { op, input: *input },
                None => {
                    CompiledF64Expr::Unsupported(format!("unsupported physical unary op '{op}'"))
                }
            },
            ExprNode::Binary { op, left, right } => match f64_binary_op(op) {
                Some(op) => CompiledF64Expr::Binary {
                    op,
                    left: *left,
                    right: *right,
                },
                None => {
                    CompiledF64Expr::Unsupported(format!("unsupported physical binary op '{op}'"))
                }
            },
            ExprNode::ContextJoin { predicate, .. } => CompiledF64Expr::Passthrough(*predicate),
            ExprNode::SpatialAggregate { .. } => {
                if let Some(values) = spatial_precomputed_f64_rows.get(&expr_index) {
                    let slot = spatial_arrays.len();
                    match values {
                        SpatialF64RowArray::Dense(values) => {
                            spatial_arrays
                                .push(CompiledSpatialF64Array::QueryRows(values.as_slice()));
                        }
                        SpatialF64RowArray::Optional(values) => {
                            spatial_arrays.push(CompiledSpatialF64Array::QueryRowsOptional(
                                values.as_slice(),
                            ));
                        }
                    }
                    CompiledF64Expr::SpatialAggregate(slot)
                } else if let Some(values) = spatial_precomputed_f64.get(&expr_index) {
                    let slot = spatial_arrays.len();
                    spatial_arrays.push(CompiledSpatialF64Array::SparseEntity(values.as_slice()));
                    CompiledF64Expr::SpatialAggregate(slot)
                } else {
                    CompiledF64Expr::Unsupported(format!(
                        "spatial aggregate expression {expr_index} was not precomputed"
                    ))
                }
            }
            ExprNode::Attribute { input, .. } => CompiledF64Expr::Passthrough(*input),
            other => CompiledF64Expr::Unsupported(format!(
                "readonly f64 evaluator does not support expression {expr_index}: {other:?}"
            )),
        };
        expressions.push(compiled);
    }
    let aliases = build_compiled_f64_aliases(&expressions);
    let initial_values = expressions
        .iter()
        .enumerate()
        .filter_map(|(index, expression)| {
            if aliases[index] == index {
                if let CompiledF64Expr::Literal(value) = expression {
                    return Some((index, *value));
                }
            }
            None
        })
        .collect();
    CompiledF64ReadOnlyProgram {
        expressions,
        aliases,
        initial_values,
        field_arrays,
        field_slot_by_key: field_array_slots,
        spatial_arrays,
    }
}

fn build_compiled_f64_aliases(expressions: &[CompiledF64Expr]) -> Vec<usize> {
    let mut aliases = vec![0; expressions.len()];
    let mut seen: HashMap<CompiledF64ExprKey, usize> = HashMap::new();
    for (index, expression) in expressions.iter().enumerate() {
        let key = compiled_f64_expr_key(expression, &aliases, index);
        if let Some(key) = key {
            if let Some(existing) = seen.get(&key) {
                aliases[index] = *existing;
            } else {
                aliases[index] = index;
                seen.insert(key, index);
            }
        } else {
            aliases[index] = index;
        }
    }
    aliases
}

fn compiled_f64_expr_key(
    expression: &CompiledF64Expr,
    aliases: &[usize],
    current_index: usize,
) -> Option<CompiledF64ExprKey> {
    let alias = |index: usize| -> usize {
        if index < current_index {
            aliases[index]
        } else {
            index
        }
    };
    match expression {
        CompiledF64Expr::Literal(value) => Some(CompiledF64ExprKey::Literal(value.to_bits())),
        CompiledF64Expr::Field(slot) => Some(CompiledF64ExprKey::Field(*slot)),
        CompiledF64Expr::SpatialAggregate(slot) => {
            Some(CompiledF64ExprKey::SpatialAggregate(*slot))
        }
        CompiledF64Expr::ResourceField { resource, field } => Some(
            CompiledF64ExprKey::ResourceField(resource.clone(), field.clone()),
        ),
        CompiledF64Expr::InputState { name, code } => {
            Some(CompiledF64ExprKey::InputState(name.clone(), *code))
        }
        CompiledF64Expr::Unary { op, input } => Some(CompiledF64ExprKey::Unary(*op, alias(*input))),
        CompiledF64Expr::Binary { op, left, right } => {
            Some(CompiledF64ExprKey::Binary(*op, alias(*left), alias(*right)))
        }
        CompiledF64Expr::Passthrough(input) => Some(CompiledF64ExprKey::Passthrough(alias(*input))),
        CompiledF64Expr::Unsupported(_) => None,
    }
}

fn compiled_f64_eval_order(
    program: &CompiledF64ReadOnlyProgram<'_>,
    outputs: impl IntoIterator<Item = usize>,
) -> Option<Vec<usize>> {
    let mut order = Vec::new();
    let mut visited = vec![false; program.expressions.len()];
    let mut visiting = vec![false; program.expressions.len()];
    for output in outputs {
        if !collect_compiled_f64_eval_order(
            program.aliases[output],
            program,
            &mut visited,
            &mut visiting,
            &mut order,
        ) {
            return None;
        }
    }
    Some(order)
}

fn collect_compiled_f64_eval_order(
    expr_index: usize,
    program: &CompiledF64ReadOnlyProgram<'_>,
    visited: &mut [bool],
    visiting: &mut [bool],
    order: &mut Vec<usize>,
) -> bool {
    let expr_index = program.aliases[expr_index];
    if visited[expr_index] {
        return true;
    }
    if visiting[expr_index] {
        return false;
    }
    visiting[expr_index] = true;
    let emit = !matches!(program.expressions[expr_index], CompiledF64Expr::Literal(_));
    let supported = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(_)
        | CompiledF64Expr::Field(_)
        | CompiledF64Expr::SpatialAggregate(_)
        | CompiledF64Expr::ResourceField { .. }
        | CompiledF64Expr::InputState { .. } => true,
        CompiledF64Expr::Unary { input, .. } | CompiledF64Expr::Passthrough(input) => {
            collect_compiled_f64_eval_order(
                program.aliases[*input],
                program,
                visited,
                visiting,
                order,
            )
        }
        CompiledF64Expr::Binary { op, left, right } => {
            !matches!(op, F64BinaryOp::And | F64BinaryOp::Or)
                && collect_compiled_f64_eval_order(
                    program.aliases[*left],
                    program,
                    visited,
                    visiting,
                    order,
                )
                && collect_compiled_f64_eval_order(
                    program.aliases[*right],
                    program,
                    visited,
                    visiting,
                    order,
                )
        }
        CompiledF64Expr::Unsupported(_) => false,
    };
    visiting[expr_index] = false;
    if supported {
        visited[expr_index] = true;
        if emit {
            order.push(expr_index);
        }
    }
    supported
}

fn eval_compiled_f64_linear_order(
    order: &[usize],
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    values: &mut [f64],
) -> Result<()> {
    for expr_index in order {
        values[*expr_index] =
            eval_compiled_f64_linear_node(*expr_index, row_index, entity, program, world, values)?;
    }
    Ok(())
}

fn eval_compiled_f64_linear_node(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    values: &[f64],
) -> Result<f64> {
    match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => Ok(*value),
        CompiledF64Expr::Field(slot) => {
            compiled_field_f64_value(program.field_arrays[*slot], row_index, entity)
        }
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)
        }
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        ),
        CompiledF64Expr::Unary { op, input } => {
            Ok(eval_f64_unary_op(*op, values[program.aliases[*input]]))
        }
        CompiledF64Expr::Binary { op, left, right } => Ok(eval_f64_binary_op(
            *op,
            values[program.aliases[*left]],
            values[program.aliases[*right]],
        )),
        CompiledF64Expr::Passthrough(input) => Ok(values[program.aliases[*input]]),
        CompiledF64Expr::Unsupported(message) => Err(EcsError::InvalidPlan(message.clone())),
    }
}

fn compiled_field_f64_value(
    array: CompiledF64Array<'_>,
    row_index: usize,
    entity: Entity,
) -> Result<f64> {
    match array {
        CompiledF64Array::QueryRows(values) => values.get(row_index).copied().ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "numeric field cache missing query row {row_index} for entity {}:{}",
                entity.index, entity.generation
            ))
        }),
        CompiledF64Array::SparseEntity(values) => {
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing entity {}:{}",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache has stale entity generation for {}:{}",
                    entity.index, entity.generation
                )));
            }
            Ok(*value)
        }
    }
}

fn compiled_spatial_f64_value(
    array: CompiledSpatialF64Array<'_>,
    row_index: usize,
    entity: Entity,
) -> Result<f64> {
    match array {
        CompiledSpatialF64Array::QueryRows(values) => {
            values.get(row_index).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial aggregate missing query row {row_index} for entity {}:{}",
                    entity.index, entity.generation
                ))
            })
        }
        CompiledSpatialF64Array::QueryRowsOptional(values) => values
            .get(row_index)
            .and_then(|value| *value)
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial aggregate missing query row {row_index} for entity {}:{}",
                    entity.index, entity.generation
                ))
            }),
        CompiledSpatialF64Array::SparseEntity(values) => {
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate missing entity {}:{}",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(
                    "spatial aggregate has stale entity generation".to_string(),
                ));
            }
            Ok(*value)
        }
    }
}

fn build_row_local_field_dependents(program: &CompiledF64ReadOnlyProgram<'_>) -> Vec<Vec<usize>> {
    let mut dependents = vec![Vec::new(); program.field_arrays.len()];
    let mut memo = vec![None; program.expressions.len()];
    for expr_index in 0..program.expressions.len() {
        let canonical = program.aliases[expr_index];
        let deps = row_local_f64_field_dependencies(canonical, program, &mut memo);
        for field_slot in deps {
            if let Some(field_dependents) = dependents.get_mut(field_slot) {
                field_dependents.push(canonical);
            }
        }
    }
    for field_dependents in &mut dependents {
        field_dependents.sort_unstable();
        field_dependents.dedup();
    }
    dependents
}

fn row_local_f64_field_dependencies(
    expr_index: usize,
    program: &CompiledF64ReadOnlyProgram<'_>,
    memo: &mut [Option<Vec<usize>>],
) -> Vec<usize> {
    let expr_index = program.aliases[expr_index];
    if let Some(deps) = memo[expr_index].clone() {
        return deps;
    }
    let expression = program.expressions[expr_index].clone();
    let mut deps = match expression {
        CompiledF64Expr::Field(slot) => vec![slot],
        CompiledF64Expr::Unary { input, .. } | CompiledF64Expr::Passthrough(input) => {
            row_local_f64_field_dependencies(input, program, memo)
        }
        CompiledF64Expr::Binary { left, right, .. } => {
            let mut deps = row_local_f64_field_dependencies(left, program, memo);
            deps.extend(row_local_f64_field_dependencies(right, program, memo));
            deps
        }
        CompiledF64Expr::Literal(_)
        | CompiledF64Expr::SpatialAggregate(_)
        | CompiledF64Expr::ResourceField { .. }
        | CompiledF64Expr::InputState { .. }
        | CompiledF64Expr::Unsupported(_) => Vec::new(),
    };
    deps.sort_unstable();
    deps.dedup();
    memo[expr_index] = Some(deps.clone());
    deps
}

fn invalidate_row_local_f64_cache(cache_marks: &mut [u32], cache_generation: &mut u32) {
    *cache_generation = cache_generation.wrapping_add(1);
    if *cache_generation == 0 {
        cache_marks.fill(0);
        *cache_generation = 1;
    }
}

fn execute_row_local_f64_action(
    action: &RowLocalAction,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache_values: &mut [f64],
    cache_marks: &mut [u32],
    cache_generation: &mut u32,
    field_values: &mut [f64],
    field_dependents: &[Vec<usize>],
    out: &mut [f64],
    dirty: &mut [bool],
) -> Result<()> {
    match action {
        RowLocalAction::Noop => Ok(()),
        RowLocalAction::Sequence(children) => {
            for child in children {
                execute_row_local_f64_action(
                    child,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                )?;
            }
            Ok(())
        }
        RowLocalAction::SetField {
            field_slot,
            target_slot,
            value_expr,
        } => {
            let value = eval_row_local_f64_expr(
                *value_expr,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                *cache_generation,
                field_values,
            )?;
            field_values[*field_slot] = value;
            if let Some(dependents) = field_dependents.get(*field_slot) {
                for expr_index in dependents {
                    cache_marks[*expr_index] = 0;
                }
            }
            out[*target_slot] = value;
            dirty[*target_slot] = true;
            Ok(())
        }
        RowLocalAction::When {
            condition_expr,
            then_action,
            otherwise_action,
        } => {
            let condition = eval_row_local_f64_expr(
                *condition_expr,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                *cache_generation,
                field_values,
            )?;
            if truthy_f64(condition) {
                execute_row_local_f64_action(
                    then_action,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                )
            } else if let Some(otherwise_action) = otherwise_action {
                execute_row_local_f64_action(
                    otherwise_action,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                )
            } else {
                Ok(())
            }
        }
    }
}

fn eval_row_local_f64_expr(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache_values: &mut [f64],
    cache_marks: &mut [u32],
    cache_generation: u32,
    field_values: &[f64],
) -> Result<f64> {
    let expr_index = program.aliases[expr_index];
    let cacheable = row_local_f64_expr_cacheable(&program.expressions[expr_index]);
    if cacheable && cache_marks[expr_index] == cache_generation {
        return Ok(cache_values[expr_index]);
    }
    let value = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => *value,
        CompiledF64Expr::Field(slot) => field_values[*slot],
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        CompiledF64Expr::Unary { op, input } => {
            let input = eval_row_local_f64_expr(
                *input,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                cache_generation,
                field_values,
            )?;
            eval_f64_unary_op(*op, input)
        }
        CompiledF64Expr::Binary { op, left, right } => match op {
            F64BinaryOp::And => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                )?;
                if truthy_f64(left) {
                    bool_f64(truthy_f64(eval_row_local_f64_expr(
                        *right,
                        row_index,
                        entity,
                        program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                    )?))
                } else {
                    0.0
                }
            }
            F64BinaryOp::Or => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                )?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_row_local_f64_expr(
                        *right,
                        row_index,
                        entity,
                        program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                    )?))
                }
            }
            op => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                )?;
                let right = eval_row_local_f64_expr(
                    *right,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                )?;
                eval_f64_binary_op(*op, left, right)
            }
        },
        CompiledF64Expr::Passthrough(input) => eval_row_local_f64_expr(
            *input,
            row_index,
            entity,
            program,
            world,
            cache_values,
            cache_marks,
            cache_generation,
            field_values,
        )?,
        CompiledF64Expr::Unsupported(message) => {
            return Err(EcsError::InvalidPlan(message.clone()))
        }
    };
    if cacheable {
        cache_values[expr_index] = value;
        cache_marks[expr_index] = cache_generation;
    }
    Ok(value)
}

fn row_local_f64_expr_cacheable(expression: &CompiledF64Expr) -> bool {
    !matches!(expression, CompiledF64Expr::Unsupported(_))
}

fn eval_compiled_f64_readonly(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache: &mut [Option<f64>],
) -> Result<f64> {
    let expr_index = program.aliases[expr_index];
    if let Some(value) = cache[expr_index] {
        return Ok(value);
    }
    let value = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => *value,
        CompiledF64Expr::Field(slot) => {
            compiled_field_f64_value(program.field_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        CompiledF64Expr::Unary { op, input } => {
            let input =
                eval_compiled_f64_readonly(*input, row_index, entity, program, world, cache)?;
            eval_f64_unary_op(*op, input)
        }
        CompiledF64Expr::Binary { op, left, right } => match op {
            F64BinaryOp::And => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                if truthy_f64(left) {
                    bool_f64(truthy_f64(eval_compiled_f64_readonly(
                        *right, row_index, entity, program, world, cache,
                    )?))
                } else {
                    0.0
                }
            }
            F64BinaryOp::Or => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_compiled_f64_readonly(
                        *right, row_index, entity, program, world, cache,
                    )?))
                }
            }
            op => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                let right =
                    eval_compiled_f64_readonly(*right, row_index, entity, program, world, cache)?;
                eval_f64_binary_op(*op, left, right)
            }
        },
        CompiledF64Expr::Passthrough(input) => {
            eval_compiled_f64_readonly(*input, row_index, entity, program, world, cache)?
        }
        CompiledF64Expr::Unsupported(message) => {
            return Err(EcsError::InvalidPlan(message.clone()))
        }
    };
    cache[expr_index] = Some(value);
    Ok(value)
}

#[allow(dead_code)]
fn eval_expr_f64_readonly(
    expr_index: usize,
    entity: Entity,
    query_name: &str,
    plan: &PhysicalPlan,
    world: &World,
    numeric_field_cache: &HashMap<String, HashMap<String, Vec<Option<(u32, f64)>>>>,
    spatial_precomputed_f64: &HashMap<usize, Vec<Option<(u32, f64)>>>,
    cache: &mut [Option<f64>],
) -> Result<f64> {
    if let Some(value) = cache[expr_index] {
        return Ok(value);
    }
    let value = match &plan.expressions[expr_index] {
        ExprNode::LiteralF64(value) => *value,
        ExprNode::LiteralI64(value) => *value as f64,
        ExprNode::LiteralBool(value) => bool_f64(*value),
        ExprNode::LiteralValue(value) => numeric_f64(value)?,
        ExprNode::Field {
            query,
            component,
            field,
        } => {
            if query != query_name {
                return Err(EcsError::InvalidPlan(format!(
                    "readonly f64 evaluator cannot read unbound query '{query}'"
                )));
            }
            let Some(fields) = numeric_field_cache.get(component) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing component '{component}'"
                )));
            };
            let Some(values) = fields.get(field) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing field '{component}.{field}'"
                )));
            };
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing entity {}:{} for '{component}.{field}'",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache has stale entity generation for {}:{}",
                    entity.index, entity.generation
                )));
            }
            *value
        }
        ExprNode::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        ExprNode::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        ExprNode::Unary { op, input } => {
            let input = eval_expr_f64_readonly(
                *input,
                entity,
                query_name,
                plan,
                world,
                numeric_field_cache,
                spatial_precomputed_f64,
                cache,
            )?;
            eval_unary_f64(op, input)?
        }
        ExprNode::Binary { op, left, right } => {
            if matches!(op.as_str(), "and" | "&&") {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                if !truthy_f64(left) {
                    0.0
                } else {
                    bool_f64(truthy_f64(eval_expr_f64_readonly(
                        *right,
                        entity,
                        query_name,
                        plan,
                        world,
                        numeric_field_cache,
                        spatial_precomputed_f64,
                        cache,
                    )?))
                }
            } else if matches!(op.as_str(), "or" | "||") {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_expr_f64_readonly(
                        *right,
                        entity,
                        query_name,
                        plan,
                        world,
                        numeric_field_cache,
                        spatial_precomputed_f64,
                        cache,
                    )?))
                }
            } else {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                let right = eval_expr_f64_readonly(
                    *right,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                eval_binary_f64(op, left, right)?
            }
        }
        ExprNode::ContextJoin { predicate, .. } => eval_expr_f64_readonly(
            *predicate,
            entity,
            query_name,
            plan,
            world,
            numeric_field_cache,
            spatial_precomputed_f64,
            cache,
        )?,
        ExprNode::SpatialAggregate { .. } => {
            let Some(values) = spatial_precomputed_f64.get(&expr_index) else {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} was not precomputed"
                )));
            };
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} missing entity {}:{}",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} has stale entity generation"
                )));
            }
            *value
        }
        ExprNode::Attribute { input, .. } => eval_expr_f64_readonly(
            *input,
            entity,
            query_name,
            plan,
            world,
            numeric_field_cache,
            spatial_precomputed_f64,
            cache,
        )?,
        other => {
            return Err(EcsError::InvalidPlan(format!(
                "readonly f64 evaluator does not support expression {expr_index}: {other:?}"
            )))
        }
    };
    cache[expr_index] = Some(value);
    Ok(value)
}

fn aggregate_empty(
    kind: &str,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if let Some(default_expr) = default {
        return executor.eval_expr(default_expr, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(false)),
        "count" => Ok(EcsValue::I64(0)),
        "sum" => Ok(EcsValue::F64(0.0)),
        "min" | "max" | "mean" => Err(EcsError::InvalidPlan(format!(
            "{kind} aggregate is empty and no default was provided"
        ))),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn aggregate_finish(
    kind: &str,
    count: usize,
    values: Vec<EcsValue>,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if count == 0 && matches!(kind, "min" | "max" | "mean") {
        return aggregate_empty(kind, default, executor, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(count > 0)),
        "count" => Ok(EcsValue::I64(count as i64)),
        "sum" => Ok(EcsValue::F64(
            values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum(),
        )),
        "min" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("min aggregate has no values".to_string()))?;
            for value in iter {
                best = best.min(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "max" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("max aggregate has no values".to_string()))?;
            for value in iter {
                best = best.max(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "mean" => {
            if values.is_empty() {
                return aggregate_empty(kind, default, executor, ctx);
            }
            let sum = values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum::<f64>();
            Ok(EcsValue::F64(sum / values.len() as f64))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn dimensions_from_u8(dimensions: u8) -> Result<Dimensions> {
    match dimensions {
        2 => Ok(Dimensions::D2),
        3 => Ok(Dimensions::D3),
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn dimensions_len(dimensions: u8) -> Result<usize> {
    Ok(dimensions_from_u8(dimensions)?.len())
}

fn point_bounds(point: &SpatialPoint) -> Result<SpatialAabb> {
    SpatialAabb::new(point.clone(), point.clone())
}

fn direct_distance_squared(left: &SpatialPoint, right: &SpatialPoint, dimensions: usize) -> f64 {
    let mut distance_sq = 0.0;
    for axis in 0..dimensions {
        let delta = right.coord(axis) - left.coord(axis);
        distance_sq += delta * delta;
    }
    distance_sq
}

fn should_try_incremental_spatial_update(
    record_count: usize,
    previous_field_revision: u64,
    current_field_revision: u64,
) -> bool {
    let changed_field_writes = current_field_revision.saturating_sub(previous_field_revision);
    let incremental_write_budget = (record_count / 4).max(1) as u64;
    changed_field_writes <= incremental_write_budget
}

fn spatial_index_base_signature(relation: &SpatialRelationNode) -> String {
    format!(
        "item={};target_pos={:?};target_bounds={:?};algorithm={:?}",
        relation.item_query, relation.target_position, relation.target_bounds, relation.algorithm
    )
}

fn spatial_relations_same_direct_precompute_group(
    left: &SpatialRelationNode,
    right: &SpatialRelationNode,
) -> bool {
    left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.origin_position == right.origin_position
        && left.target_position == right.target_position
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn spatial_relations_same_multi_origin_precompute_group(
    left: &SpatialRelationNode,
    right: &SpatialRelationNode,
) -> bool {
    left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.target_position == right.target_position
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn spatial_relations_same_base(left: &SpatialRelationNode, right: &SpatialRelationNode) -> bool {
    left.id == right.id
        && left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.origin_position == right.origin_position
        && left.target_position == right.target_position
        && left.radius == right.radius
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn bounds_from_values(dimensions: u8, values: &[f64]) -> Result<SpatialAabb> {
    match dimensions {
        2 => {
            if values.len() != 4 {
                return Err(EcsError::InvalidPlan(
                    "2D spatial bounds require four values".to_string(),
                ));
            }
            SpatialAabb::point2(values[0], values[1], values[2], values[3])
        }
        3 => {
            if values.len() != 6 {
                return Err(EcsError::InvalidPlan(
                    "3D spatial bounds require six values".to_string(),
                ));
            }
            SpatialAabb::point3(
                values[0], values[1], values[2], values[3], values[4], values[5],
            )
        }
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn build_spatial_index(algorithm: &crate::plan::SpatialAlgorithmNode) -> Result<BuiltSpatialIndex> {
    let dimensions = dimensions_from_u8(algorithm.dimensions)?;
    match algorithm.kind.as_str() {
        "hash_grid" => Ok(BuiltSpatialIndex::HashGrid(HashGridIndex::new(
            dimensions,
            algorithm.cell_size.unwrap_or(1.0),
        )?)),
        "quadtree" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "quadtree spatial algorithm requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("quadtree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Quadtree(QuadtreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "octree" => {
            if dimensions != Dimensions::D3 {
                return Err(EcsError::InvalidPlan(
                    "octree spatial algorithm requires 3D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                3,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("octree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Octree(OctreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "hilbert_curve" | "hilbert" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "Hilbert spatial algorithm currently requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("Hilbert spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Hilbert(HilbertIndex::new(
                bounds,
                algorithm.bits.unwrap_or(16),
            )?))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported spatial algorithm '{other}'"
        ))),
    }
}

fn bool_f64(value: bool) -> f64 {
    if value {
        1.0
    } else {
        0.0
    }
}

fn truthy_f64(value: f64) -> bool {
    value != 0.0
}

fn storage_type_is_numeric(storage_type: StorageType) -> bool {
    matches!(
        storage_type,
        StorageType::Bool
            | StorageType::Int8
            | StorageType::Int16
            | StorageType::Int32
            | StorageType::Int64
            | StorageType::UInt8
            | StorageType::UInt16
            | StorageType::UInt32
            | StorageType::UInt64
            | StorageType::Float32
            | StorageType::Float64
    )
}

fn f64_unary_op(op: &str) -> Option<F64UnaryOp> {
    match op {
        "neg" | "-" => Some(F64UnaryOp::Neg),
        "not" | "!" => Some(F64UnaryOp::Not),
        "abs" => Some(F64UnaryOp::Abs),
        "sqrt" => Some(F64UnaryOp::Sqrt),
        "sin" => Some(F64UnaryOp::Sin),
        "cos" => Some(F64UnaryOp::Cos),
        "floor" => Some(F64UnaryOp::Floor),
        "ceil" => Some(F64UnaryOp::Ceil),
        _ => None,
    }
}

fn eval_f64_unary_op(op: F64UnaryOp, input: f64) -> f64 {
    match op {
        F64UnaryOp::Neg => -input,
        F64UnaryOp::Not => bool_f64(!truthy_f64(input)),
        F64UnaryOp::Abs => input.abs(),
        F64UnaryOp::Sqrt => input.sqrt(),
        F64UnaryOp::Sin => input.sin(),
        F64UnaryOp::Cos => input.cos(),
        F64UnaryOp::Floor => input.floor(),
        F64UnaryOp::Ceil => input.ceil(),
    }
}

fn eval_unary_f64(op: &str, input: f64) -> Result<f64> {
    f64_unary_op(op)
        .map(|op| eval_f64_unary_op(op, input))
        .ok_or_else(|| EcsError::InvalidPlan(format!("unsupported physical unary op '{op}'")))
}

fn f64_binary_op(op: &str) -> Option<F64BinaryOp> {
    match op {
        "add" | "+" => Some(F64BinaryOp::Add),
        "sub" | "-" => Some(F64BinaryOp::Sub),
        "mul" | "*" => Some(F64BinaryOp::Mul),
        "truediv" | "/" => Some(F64BinaryOp::TrueDiv),
        "floordiv" | "//" => Some(F64BinaryOp::FloorDiv),
        "mod" | "%" => Some(F64BinaryOp::Mod),
        "pow" | "**" => Some(F64BinaryOp::Pow),
        "lt" | "<" => Some(F64BinaryOp::Lt),
        "le" | "<=" => Some(F64BinaryOp::Le),
        "gt" | ">" => Some(F64BinaryOp::Gt),
        "ge" | ">=" => Some(F64BinaryOp::Ge),
        "eq" | "==" => Some(F64BinaryOp::Eq),
        "ne" | "!=" => Some(F64BinaryOp::Ne),
        "min" => Some(F64BinaryOp::Min),
        "max" => Some(F64BinaryOp::Max),
        "and" | "&&" => Some(F64BinaryOp::And),
        "or" | "||" => Some(F64BinaryOp::Or),
        _ => None,
    }
}

fn eval_f64_binary_op(op: F64BinaryOp, left: f64, right: f64) -> f64 {
    match op {
        F64BinaryOp::Add => left + right,
        F64BinaryOp::Sub => left - right,
        F64BinaryOp::Mul => left * right,
        F64BinaryOp::TrueDiv => left / right,
        F64BinaryOp::FloorDiv => (left / right).floor(),
        F64BinaryOp::Mod => left % right,
        F64BinaryOp::Pow => left.powf(right),
        F64BinaryOp::Lt => bool_f64(left < right),
        F64BinaryOp::Le => bool_f64(left <= right),
        F64BinaryOp::Gt => bool_f64(left > right),
        F64BinaryOp::Ge => bool_f64(left >= right),
        F64BinaryOp::Eq => bool_f64(left == right),
        F64BinaryOp::Ne => bool_f64(left != right),
        F64BinaryOp::Min => left.min(right),
        F64BinaryOp::Max => left.max(right),
        F64BinaryOp::And => bool_f64(truthy_f64(left) && truthy_f64(right)),
        F64BinaryOp::Or => bool_f64(truthy_f64(left) || truthy_f64(right)),
    }
}

fn eval_binary_f64(op: &str, left: f64, right: f64) -> Result<f64> {
    f64_binary_op(op)
        .map(|op| eval_f64_binary_op(op, left, right))
        .ok_or_else(|| EcsError::InvalidPlan(format!("unsupported physical binary op '{op}'")))
}

fn eval_unary(op: &str, input: EcsValue) -> Result<EcsValue> {
    match op {
        "neg" | "-" => match input {
            EcsValue::I64(value) => Ok(EcsValue::I64(-value)),
            EcsValue::U64(value) => Ok(EcsValue::I64(-(value as i64))),
            EcsValue::F64(value) => Ok(EcsValue::F64(-value)),
            other => Err(EcsError::InvalidPlan(format!(
                "unary neg expects a numeric value, got {}",
                other.kind_name()
            ))),
        },
        "not" | "!" => Ok(EcsValue::Bool(!truthy(&input)?)),
        "abs" => Ok(EcsValue::F64(numeric_f64(&input)?.abs())),
        "sqrt" => Ok(EcsValue::F64(numeric_f64(&input)?.sqrt())),
        "sin" => Ok(EcsValue::F64(numeric_f64(&input)?.sin())),
        "cos" => Ok(EcsValue::F64(numeric_f64(&input)?.cos())),
        "floor" => Ok(EcsValue::F64(numeric_f64(&input)?.floor())),
        "ceil" => Ok(EcsValue::F64(numeric_f64(&input)?.ceil())),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported physical unary op '{other}'"
        ))),
    }
}

fn default_input_state_value(name: &str) -> EcsValue {
    match name {
        "dt" | "delta_time" => EcsValue::F64(0.0),
        "key_down" => EcsValue::Bool(false),
        _ => EcsValue::Bool(false),
    }
}

fn eval_binary(op: &str, left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    match op {
        "add" | "+" => numeric_arithmetic(left, right, |a, b| a + b),
        "sub" | "-" => numeric_arithmetic(left, right, |a, b| a - b),
        "mul" | "*" => numeric_arithmetic(left, right, |a, b| a * b),
        "truediv" | "/" => Ok(EcsValue::F64(numeric_f64(&left)? / numeric_f64(&right)?)),
        "floordiv" | "//" => Ok(EcsValue::F64(
            (numeric_f64(&left)? / numeric_f64(&right)?).floor(),
        )),
        "mod" | "%" => Ok(EcsValue::F64(numeric_f64(&left)? % numeric_f64(&right)?)),
        "pow" | "**" => Ok(EcsValue::F64(
            numeric_f64(&left)?.powf(numeric_f64(&right)?),
        )),
        "lt" | "<" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a < b)?)),
        "le" | "<=" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a <= b
        })?)),
        "gt" | ">" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a > b)?)),
        "ge" | ">=" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a >= b
        })?)),
        "eq" | "==" => Ok(EcsValue::Bool(values_equal(&left, &right)?)),
        "ne" | "!=" => Ok(EcsValue::Bool(!values_equal(&left, &right)?)),
        "min" => Ok(if numeric_f64(&left)? <= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        "max" => Ok(if numeric_f64(&left)? >= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported physical binary op '{other}'"
        ))),
    }
}

fn numeric_arithmetic(
    left: EcsValue,
    right: EcsValue,
    op: impl FnOnce(f64, f64) -> f64,
) -> Result<EcsValue> {
    Ok(EcsValue::F64(op(numeric_f64(&left)?, numeric_f64(&right)?)))
}

fn literal_expr_numeric(expr: &ExprNode) -> Option<f64> {
    match expr {
        ExprNode::LiteralF64(value) => Some(*value),
        ExprNode::LiteralI64(value) => Some(*value as f64),
        ExprNode::LiteralBool(value) => Some(if *value { 1.0 } else { 0.0 }),
        ExprNode::LiteralValue(value) => numeric_f64(value).ok(),
        _ => None,
    }
}

fn numeric_f64(value: &EcsValue) -> Result<f64> {
    match value {
        EcsValue::Bool(value) => Ok(if *value { 1.0 } else { 0.0 }),
        EcsValue::I64(value) => Ok(*value as f64),
        EcsValue::U64(value) => Ok(*value as f64),
        EcsValue::F64(value) => Ok(*value),
        other => Err(EcsError::InvalidPlan(format!(
            "expected numeric ECS value, got {}",
            other.kind_name()
        ))),
    }
}

fn truthy(value: &EcsValue) -> Result<bool> {
    match value {
        EcsValue::Bool(value) => Ok(*value),
        EcsValue::I64(value) => Ok(*value != 0),
        EcsValue::U64(value) => Ok(*value != 0),
        EcsValue::F64(value) => Ok(*value != 0.0),
        other => Err(EcsError::InvalidPlan(format!(
            "expected boolean-compatible ECS value, got {}",
            other.kind_name()
        ))),
    }
}

fn compare_values(
    left: &EcsValue,
    right: &EcsValue,
    op: impl FnOnce(f64, f64) -> bool,
) -> Result<bool> {
    Ok(op(numeric_f64(left)?, numeric_f64(right)?))
}

fn values_equal(left: &EcsValue, right: &EcsValue) -> Result<bool> {
    match (left, right) {
        (EcsValue::Bool(left), EcsValue::Bool(right)) => Ok(left == right),
        (EcsValue::String(left), EcsValue::String(right)) => Ok(left == right),
        (
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
        ) => Ok(numeric_f64(left)? == numeric_f64(right)?),
        _ => Ok(left == right),
    }
}

fn coerce_value_for_storage(storage_type: StorageType, value: EcsValue) -> Result<EcsValue> {
    match storage_type {
        StorageType::Bool => match value {
            EcsValue::Bool(value) => Ok(EcsValue::Bool(value)),
            other => Err(type_mismatch("Bool", other)),
        },
        StorageType::Int8 | StorageType::Int16 | StorageType::Int32 | StorageType::Int64 => {
            match value {
                EcsValue::I64(value) => Ok(EcsValue::I64(value)),
                EcsValue::U64(value) if value <= i64::MAX as u64 => Ok(EcsValue::I64(value as i64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= i64::MIN as f64
                        && value <= i64::MAX as f64 =>
                {
                    Ok(EcsValue::I64(value as i64))
                }
                other => Err(type_mismatch("I64", other)),
            }
        }
        StorageType::UInt8 | StorageType::UInt16 | StorageType::UInt32 | StorageType::UInt64 => {
            match value {
                EcsValue::U64(value) => Ok(EcsValue::U64(value)),
                EcsValue::I64(value) if value >= 0 => Ok(EcsValue::U64(value as u64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= 0.0
                        && value <= u64::MAX as f64 =>
                {
                    Ok(EcsValue::U64(value as u64))
                }
                other => Err(type_mismatch("U64", other)),
            }
        }
        StorageType::Float32 | StorageType::Float64 => match value {
            EcsValue::F64(value) => Ok(EcsValue::F64(value)),
            EcsValue::I64(value) => Ok(EcsValue::F64(value as f64)),
            EcsValue::U64(value) => Ok(EcsValue::F64(value as f64)),
            other => Err(type_mismatch("F64", other)),
        },
        StorageType::String | StorageType::CategoricalString => match value {
            EcsValue::String(value) => Ok(EcsValue::String(value)),
            other => Err(type_mismatch("String", other)),
        },
        StorageType::Vec2F32 => match value {
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F32(value)),
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F32([value[0] as f32, value[1] as f32])),
            other => Err(type_mismatch("Vec2F32", other)),
        },
        StorageType::Vec2F64 => match value {
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F64(value)),
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F64([value[0] as f64, value[1] as f64])),
            other => Err(type_mismatch("Vec2F64", other)),
        },
        StorageType::Vec3F32 => match value {
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F32(value)),
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F32([
                value[0] as f32,
                value[1] as f32,
                value[2] as f32,
            ])),
            other => Err(type_mismatch("Vec3F32", other)),
        },
        StorageType::Vec3F64 => match value {
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F64(value)),
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F64([
                value[0] as f64,
                value[1] as f64,
                value[2] as f64,
            ])),
            other => Err(type_mismatch("Vec3F64", other)),
        },
        StorageType::List => match value {
            EcsValue::List(value) => Ok(EcsValue::List(value)),
            other => Err(type_mismatch("List", other)),
        },
    }
}

fn type_mismatch(expected: &'static str, value: EcsValue) -> EcsError {
    EcsError::ColumnTypeMismatch {
        expected,
        got: value.kind_name(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::plan::{BridgeQueryPayload, BRIDGE_PLAN_VERSION};
    use crate::query::QueryTerm;
    use crate::schema::{ComponentSchema, FieldSchema};

    fn world_with_motion() -> (World, Entity) {
        let mut world = World::new();
        world
            .register_schema(ComponentSchema::new(
                "Position",
                vec![
                    FieldSchema::new("x", StorageType::Float64),
                    FieldSchema::new("y", StorageType::Float64),
                ],
            ))
            .unwrap();
        world
            .register_schema(ComponentSchema::new(
                "Velocity",
                vec![FieldSchema::new("dx", StorageType::Float64)],
            ))
            .unwrap();
        world
            .register_schema(ComponentSchema::new(
                "Clock",
                vec![FieldSchema::new("tick", StorageType::Int64)],
            ))
            .unwrap();
        let entity = world
            .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
            .unwrap();
        world
            .set_field(entity, "Position", "x", EcsValue::F64(2.0))
            .unwrap();
        world
            .set_field(entity, "Velocity", "dx", EcsValue::F64(3.0))
            .unwrap();
        (world, entity)
    }

    fn add_motion_entity(world: &mut World, x: f64, y: f64, dx: f64) -> Entity {
        let entity = world
            .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
            .unwrap();
        world
            .set_field(entity, "Position", "x", EcsValue::F64(x))
            .unwrap();
        world
            .set_field(entity, "Position", "y", EcsValue::F64(y))
            .unwrap();
        world
            .set_field(entity, "Velocity", "dx", EcsValue::F64(dx))
            .unwrap();
        entity
    }

    fn spatial_count_payload(world: &World) -> BridgePlanPayload {
        BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::LiteralF64(2.5),
                ExprNode::SpatialAggregate {
                    kind: "count".to_string(),
                    relation: SpatialRelationNode {
                        id: "nearby".to_string(),
                        index_id: "position_neighbors".to_string(),
                        origin_query: "entity".to_string(),
                        item_query: "entity".to_string(),
                        origin_position: vec![0, 1],
                        target_position: vec![0, 1],
                        radius: Some(2),
                        origin_bounds: None,
                        target_bounds: None,
                        algorithm: crate::plan::SpatialAlgorithmNode {
                            kind: "hash_grid".to_string(),
                            dimensions: 2,
                            cell_size: Some(4.0),
                            bounds: None,
                            capacity: None,
                            bits: None,
                        },
                        include_self: false,
                        pair_policy: "all".to_string(),
                        exact_filter: None,
                    },
                    value: None,
                    default: None,
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 4,
                value: 3,
            }],
            root_action: 0,
        }
    }

    fn spatial_parallel_count_payload(world: &World) -> BridgePlanPayload {
        let mut payload = spatial_count_payload(world);
        payload.actions = vec![
            ActionNode::SetField {
                target: 4,
                value: 3,
            },
            ActionNode::SetField {
                target: 0,
                value: 3,
            },
            ActionNode::Parallel(vec![0, 1]),
        ];
        payload.root_action = 2;
        payload
    }

    #[test]
    fn physical_plan_executes_scalar_set_over_query_rows() {
        let (mut world, entity) = world_with_motion();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 0,
                    right: 1,
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 0,
                value: 2,
            }],
            root_action: 0,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(5.0)
        );
        assert_eq!(report.fields_written, 1);
        assert_eq!(report.writes.len(), 1);
    }

    #[test]
    fn physical_parallel_uses_snapshot_reads_and_stable_merge() {
        let (mut world, entity) = world_with_motion();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![QueryTerm::WithComponent("Position".to_string())],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::LiteralF64(5.0),
            ],
            actions: vec![
                ActionNode::SetField {
                    target: 0,
                    value: 2,
                },
                ActionNode::SetField {
                    target: 1,
                    value: 0,
                },
                ActionNode::Parallel(vec![0, 1]),
            ],
            root_action: 2,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(5.0)
        );
        assert_eq!(
            world.get_field(entity, "Position", "y").unwrap(),
            EcsValue::F64(2.0)
        );
        assert_eq!(report.fields_written, 2);
        assert_eq!(report.duplicate_writes, 0);
    }

    #[test]
    fn optimized_f64_executor_reads_resources_and_input_state() {
        let (mut world, entity) = world_with_motion();
        world
            .register_schema(ComponentSchema::new(
                "Wind",
                vec![FieldSchema::new("x", StorageType::Float64)],
            ))
            .unwrap();
        world.set_input_state("dt", None, EcsValue::F64(16.0));
        let mut wind = HashMap::new();
        wind.insert("x".to_string(), EcsValue::F64(2.0));
        world.insert_resource("Wind", wind).unwrap();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::ResourceField {
                    resource: "Wind".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 1,
                    right: 2,
                },
                ExprNode::InputState {
                    name: "dt".to_string(),
                    code: None,
                },
                ExprNode::LiteralF64(1000.0),
                ExprNode::Binary {
                    op: "truediv".to_string(),
                    left: 4,
                    right: 5,
                },
                ExprNode::Binary {
                    op: "mul".to_string(),
                    left: 3,
                    right: 6,
                },
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 0,
                    right: 7,
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 0,
                value: 8,
            }],
            root_action: 0,
        };
        let handle = world.compile_bridge_plan_handle(payload).unwrap();

        let report = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();

        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(2.08)
        );
        assert_eq!(report.fields_written, 1);
        assert!(report.writes.is_empty());
    }

    #[test]
    fn spatial_aggregate_precomputes_generic_exact_filter() {
        let (mut world, first) = world_with_motion();
        world
            .set_field(first, "Position", "y", EcsValue::F64(0.0))
            .unwrap();
        add_motion_entity(&mut world, 3.0, 0.0, 3.0);
        add_motion_entity(&mut world, 4.0, 0.0, 7.0);
        add_motion_entity(&mut world, 20.0, 0.0, 3.0);
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![
                BridgeQueryPayload {
                    name: "origin".to_string(),
                    terms: vec![
                        QueryTerm::WithComponent("Position".to_string()),
                        QueryTerm::WithComponent("Velocity".to_string()),
                    ],
                    allowed_entities: None,
                },
                BridgeQueryPayload {
                    name: "item".to_string(),
                    terms: vec![
                        QueryTerm::WithComponent("Position".to_string()),
                        QueryTerm::WithComponent("Velocity".to_string()),
                    ],
                    allowed_entities: None,
                },
            ],
            expressions: vec![
                ExprNode::Field {
                    query: "origin".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "origin".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::Field {
                    query: "item".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "item".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::LiteralF64(5.0),
                ExprNode::Field {
                    query: "origin".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::Field {
                    query: "item".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::Binary {
                    op: "eq".to_string(),
                    left: 6,
                    right: 5,
                },
                ExprNode::SpatialAggregate {
                    kind: "count".to_string(),
                    relation: SpatialRelationNode {
                        id: "same_velocity_neighbors".to_string(),
                        index_id: "same_velocity_position_neighbors".to_string(),
                        origin_query: "origin".to_string(),
                        item_query: "item".to_string(),
                        origin_position: vec![0, 1],
                        target_position: vec![2, 3],
                        radius: Some(4),
                        origin_bounds: None,
                        target_bounds: None,
                        algorithm: crate::plan::SpatialAlgorithmNode {
                            kind: "hash_grid".to_string(),
                            dimensions: 2,
                            cell_size: Some(8.0),
                            bounds: None,
                            capacity: None,
                            bits: None,
                        },
                        include_self: false,
                        pair_policy: "all".to_string(),
                        exact_filter: Some(7),
                    },
                    value: None,
                    default: None,
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 1,
                value: 8,
            }],
            root_action: 0,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.get_field(first, "Position", "y").unwrap(),
            EcsValue::F64(1.0)
        );
        assert!(report.spatial_exact_rows > 0);
    }

    #[test]
    fn spatial_index_cache_distinguishes_same_named_relations_with_different_item_filters() {
        let (mut world, marker) = world_with_motion();
        world.add_tag(marker, "Marker").unwrap();
        world
            .set_field(marker, "Position", "x", EcsValue::F64(0.0))
            .unwrap();
        world
            .set_field(marker, "Position", "y", EcsValue::F64(0.0))
            .unwrap();
        let red_near = add_motion_entity(&mut world, 1.0, 0.0, 0.0);
        let red_far = add_motion_entity(&mut world, 100.0, 0.0, 0.0);
        let blue_near_a = add_motion_entity(&mut world, 2.0, 0.0, 0.0);
        let blue_near_b = add_motion_entity(&mut world, 3.0, 0.0, 0.0);
        world.add_tag(red_near, "Red").unwrap();
        world.add_tag(red_far, "Red").unwrap();
        world.add_tag(blue_near_a, "Blue").unwrap();
        world.add_tag(blue_near_b, "Blue").unwrap();

        fn tagged_count_payload(world: &World, tag: &str) -> BridgePlanPayload {
            BridgePlanPayload {
                version: BRIDGE_PLAN_VERSION,
                schema_fingerprint: Some(world.schema_fingerprint()),
                queries: vec![
                    BridgeQueryPayload {
                        name: "origin".to_string(),
                        terms: vec![
                            QueryTerm::WithComponent("Position".to_string()),
                            QueryTerm::WithComponent("Velocity".to_string()),
                            QueryTerm::WithTag("Marker".to_string()),
                        ],
                        allowed_entities: None,
                    },
                    BridgeQueryPayload {
                        name: "item".to_string(),
                        terms: vec![
                            QueryTerm::WithComponent("Position".to_string()),
                            QueryTerm::WithTag(tag.to_string()),
                        ],
                        allowed_entities: None,
                    },
                ],
                expressions: vec![
                    ExprNode::Field {
                        query: "origin".to_string(),
                        component: "Position".to_string(),
                        field: "x".to_string(),
                    },
                    ExprNode::Field {
                        query: "origin".to_string(),
                        component: "Position".to_string(),
                        field: "y".to_string(),
                    },
                    ExprNode::Field {
                        query: "item".to_string(),
                        component: "Position".to_string(),
                        field: "x".to_string(),
                    },
                    ExprNode::Field {
                        query: "item".to_string(),
                        component: "Position".to_string(),
                        field: "y".to_string(),
                    },
                    ExprNode::LiteralF64(5.0),
                    ExprNode::SpatialAggregate {
                        kind: "count".to_string(),
                        relation: SpatialRelationNode {
                            id: "shared_named_neighbors".to_string(),
                            index_id: "shared_named_index".to_string(),
                            origin_query: "origin".to_string(),
                            item_query: "item".to_string(),
                            origin_position: vec![0, 1],
                            target_position: vec![2, 3],
                            radius: Some(4),
                            origin_bounds: None,
                            target_bounds: None,
                            algorithm: crate::plan::SpatialAlgorithmNode {
                                kind: "hash_grid".to_string(),
                                dimensions: 2,
                                cell_size: Some(8.0),
                                bounds: None,
                                capacity: None,
                                bits: None,
                            },
                            include_self: false,
                            pair_policy: "all".to_string(),
                            exact_filter: None,
                        },
                        value: None,
                        default: None,
                    },
                    ExprNode::Field {
                        query: "origin".to_string(),
                        component: "Velocity".to_string(),
                        field: "dx".to_string(),
                    },
                ],
                actions: vec![ActionNode::SetField {
                    target: 6,
                    value: 5,
                }],
                root_action: 0,
            }
        }

        world
            .execute_bridge_plan(tagged_count_payload(&world, "Red"))
            .unwrap();
        assert_eq!(
            world.get_field(marker, "Velocity", "dx").unwrap(),
            EcsValue::F64(1.0)
        );

        world
            .execute_bridge_plan(tagged_count_payload(&world, "Blue"))
            .unwrap();
        assert_eq!(
            world.get_field(marker, "Velocity", "dx").unwrap(),
            EcsValue::F64(2.0)
        );
    }

    #[test]
    fn spatial_index_cache_reuses_valid_snapshot_across_executions() {
        let (mut world, _) = world_with_motion();
        add_motion_entity(&mut world, 1.0, 0.0, 0.0);
        add_motion_entity(&mut world, 20.0, 0.0, 0.0);
        let handle = world
            .compile_bridge_plan_handle(spatial_count_payload(&world))
            .unwrap();

        let first = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();
        assert_eq!(first.spatial_index_full_rebuilds, 1);
        assert_eq!(first.spatial_index_incremental_updates, 0);
        assert_eq!(world.spatial_index_cache_len(), 1);

        let second = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();
        assert_eq!(second.spatial_indexes_built, 0);
        assert_eq!(second.spatial_index_full_rebuilds, 0);
        assert_eq!(second.spatial_index_incremental_updates, 0);
        assert!(second.spatial_index_reuses >= 1);
        assert_eq!(world.spatial_index_cache_len(), 1);
    }

    #[test]
    fn spatial_index_cache_persists_from_fused_parallel_collector() {
        let (mut world, _) = world_with_motion();
        add_motion_entity(&mut world, 1.0, 0.0, 0.0);
        add_motion_entity(&mut world, 20.0, 0.0, 0.0);
        let handle = world
            .compile_bridge_plan_handle(spatial_parallel_count_payload(&world))
            .unwrap();

        let report = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();
        assert_eq!(report.spatial_index_full_rebuilds, 1);
        assert_eq!(world.spatial_index_cache_len(), 1);
    }

    #[test]
    fn spatial_hash_grid_incrementally_updates_after_indexed_field_change() {
        let (mut world, entity) = world_with_motion();
        add_motion_entity(&mut world, 1.0, 0.0, 0.0);
        add_motion_entity(&mut world, 20.0, 0.0, 0.0);
        let handle = world
            .compile_bridge_plan_handle(spatial_count_payload(&world))
            .unwrap();
        world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();

        world
            .set_field(entity, "Position", "x", EcsValue::F64(30.0))
            .unwrap();
        let report = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();
        assert_eq!(report.spatial_index_incremental_updates, 1);
        assert_eq!(report.spatial_index_full_rebuilds, 0);
        assert_eq!(world.spatial_index_cache_len(), 1);
    }

    #[test]
    fn spatial_hash_grid_incrementally_updates_after_structural_churn() {
        let (mut world, _) = world_with_motion();
        add_motion_entity(&mut world, 1.0, 0.0, 0.0);
        let removed = add_motion_entity(&mut world, 20.0, 0.0, 0.0);
        let handle = world
            .compile_bridge_plan_handle(spatial_count_payload(&world))
            .unwrap();
        world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();

        world.despawn(removed).unwrap();
        add_motion_entity(&mut world, 2.0, 0.0, 0.0);
        let report = world
            .execute_compiled_plan_with_options(handle, false)
            .unwrap();
        assert_eq!(report.spatial_index_incremental_updates, 1);
        assert_eq!(report.spatial_index_full_rebuilds, 0);
        assert_eq!(world.spatial_index_cache_len(), 1);
    }

    #[test]
    fn physical_plan_executes_conditionals_and_resources() {
        let (mut world, entity) = world_with_motion();
        let mut clock = HashMap::new();
        clock.insert("tick".to_string(), EcsValue::I64(1));
        world.insert_resource("Clock", clock).unwrap();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![QueryTerm::WithComponent("Position".to_string())],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::LiteralF64(1.0),
                ExprNode::Binary {
                    op: "gt".to_string(),
                    left: 0,
                    right: 1,
                },
                ExprNode::ResourceField {
                    resource: "Clock".to_string(),
                    field: "tick".to_string(),
                },
                ExprNode::LiteralI64(2),
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 3,
                    right: 4,
                },
            ],
            actions: vec![
                ActionNode::SetField {
                    target: 3,
                    value: 5,
                },
                ActionNode::When {
                    condition: 2,
                    then_action: 0,
                    otherwise_action: None,
                },
            ],
            root_action: 1,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.resource_field("Clock", "tick").unwrap(),
            EcsValue::I64(3)
        );
        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(2.0)
        );
        assert_eq!(report.resource_fields_written, 1);
    }
}
