use crate::entity::Entity;
use crate::error::Result;
use crate::spatial::{
    HashGridIndex, HilbertIndex, OctreeIndex, QuadtreeIndex, SpatialAabb, SpatialIndexBackend,
    SpatialPoint, SpatialRecord,
};

use super::point_hash_grid::DirectPointHashGrid;

#[derive(Debug, Clone)]
pub(crate) enum BuiltSpatialIndex {
    HashGrid(HashGridIndex),
    DirectPointHashGrid(DirectPointHashGrid),
    Quadtree(QuadtreeIndex),
    Octree(OctreeIndex),
    Hilbert(HilbertIndex),
}

#[derive(Debug, Clone)]
pub(crate) struct CachedSpatialIndex {
    pub index: BuiltSpatialIndex,
    pub signature: String,
    pub structural_revision: u64,
    pub field_revision: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(in crate::execution) enum NumericComparison {
    LessThan,
    LessThanOrEqual,
    GreaterThan,
    GreaterThanOrEqual,
}

#[derive(Debug, Clone, Copy)]
pub(in crate::execution) enum SpatialDistanceFilter {
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
pub(in crate::execution) enum SpatialBatchValue {
    Count,
    DirectField { component: String, field: String },
    NegDeltaOverDistance { axis: usize, minimum_distance: f64 },
    Expression { expr_index: usize },
}

#[derive(Debug, Clone)]
pub(in crate::execution) enum FastSpatialBinaryOp {
    Add,
    Sub,
    Mul,
    Div,
    Min,
    Max,
}

#[derive(Debug, Clone)]
pub(in crate::execution) enum FastSpatialValueExpr {
    Literal(f64),
    OriginPointCoord {
        axis: usize,
    },
    ItemField {
        array_index: usize,
    },
    ItemPointCoord {
        axis: usize,
    },
    SpatialDelta {
        axis: usize,
    },
    SpatialDistance,
    SpatialDistanceSq,
    Neg(Box<FastSpatialValueExpr>),
    Binary {
        op: FastSpatialBinaryOp,
        left: Box<FastSpatialValueExpr>,
        right: Box<FastSpatialValueExpr>,
    },
}

#[derive(Debug, Clone)]
pub(in crate::execution) enum FastSpatialBatchValue {
    Count,
    DirectField { array_index: usize },
    DirectPointCoord { axis: usize },
    NegDeltaOverDistance { axis: usize, minimum_distance: f64 },
    Expression { expr: FastSpatialValueExpr },
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct SpatialBatchSpec {
    pub(in crate::execution) expr_index: usize,
    pub(in crate::execution) kind: String,
    pub(in crate::execution) value: SpatialBatchValue,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(in crate::execution) enum FastAggregateKind {
    Any,
    Count,
    Sum,
    Mean,
    Min,
    Max,
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct FastSpatialBatchSpec {
    pub(in crate::execution) expr_index: usize,
    pub(in crate::execution) kind: FastAggregateKind,
    pub(in crate::execution) value: FastSpatialBatchValue,
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct FastFieldArray {
    pub(in crate::execution) component: String,
    pub(in crate::execution) field: String,
    pub(in crate::execution) entities: Vec<Entity>,
    pub(in crate::execution) values: Vec<f64>,
}

#[derive(Debug, Clone, Copy)]
pub(in crate::execution) struct SpatialBatchAccum {
    pub(in crate::execution) count: usize,
    pub(in crate::execution) sum: f64,
    pub(in crate::execution) min: f64,
    pub(in crate::execution) max: f64,
}

#[derive(Debug, Clone, Copy, Default)]
pub(in crate::execution) struct SpatialLocalCounters {
    pub(in crate::execution) candidate_rows: usize,
    pub(in crate::execution) exact_rows: usize,
    pub(in crate::execution) rows_scanned: usize,
    pub(in crate::execution) deduplicated_pairs: usize,
    pub(in crate::execution) candidate_buffer_growths: usize,
}

#[derive(Debug)]
pub(in crate::execution) struct SpatialChunkResult {
    pub(in crate::execution) row_start: usize,
    pub(in crate::execution) origins: Vec<Entity>,
    pub(in crate::execution) values: Vec<f64>,
    pub(in crate::execution) present: Option<Vec<bool>>,
    pub(in crate::execution) counters: SpatialLocalCounters,
}

#[derive(Debug)]
pub(in crate::execution) enum SpatialF64RowArray {
    Dense(Vec<f64>),
    Optional(Vec<Option<f64>>),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(in crate::execution) enum SpatialPrecomputeLayout {
    SparseEntity,
    QueryRows,
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct DirectSpatialCoord {
    pub(in crate::execution) component: String,
    pub(in crate::execution) field: String,
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct DirectSpatialRelationBatch {
    pub(in crate::execution) specs: Vec<SpatialBatchSpec>,
    pub(in crate::execution) distance_filter: Option<SpatialDistanceFilter>,
    pub(in crate::execution) query_radius: f64,
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct FastDirectSpatialRelationBatch {
    pub(in crate::execution) specs: Vec<FastSpatialBatchSpec>,
    pub(in crate::execution) distance_filter: Option<SpatialDistanceFilter>,
    pub(in crate::execution) query_radius: f64,
    pub(in crate::execution) query_radius_sq: f64,
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
    pub(in crate::execution) fn matches(self, distance_sq: f64) -> bool {
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

    pub(in crate::execution) fn upper_radius_bound(self) -> Option<f64> {
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

pub(in crate::execution) fn effective_query_radius(
    radius: Option<f64>,
    distance_filter: Option<SpatialDistanceFilter>,
) -> Option<f64> {
    match (
        radius,
        distance_filter.and_then(SpatialDistanceFilter::upper_radius_bound),
    ) {
        (Some(radius), Some(bound)) => Some(radius.min(bound)),
        (Some(radius), None) => Some(radius),
        (None, Some(bound)) => Some(bound),
        (None, None) => None,
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

pub(in crate::execution) fn comparison_from_op(op: &str) -> Option<NumericComparison> {
    match op {
        "lt" | "<" => Some(NumericComparison::LessThan),
        "le" | "<=" => Some(NumericComparison::LessThanOrEqual),
        "gt" | ">" => Some(NumericComparison::GreaterThan),
        "ge" | ">=" => Some(NumericComparison::GreaterThanOrEqual),
        _ => None,
    }
}

pub(in crate::execution) fn reverse_comparison(comparison: NumericComparison) -> NumericComparison {
    match comparison {
        NumericComparison::LessThan => NumericComparison::GreaterThan,
        NumericComparison::LessThanOrEqual => NumericComparison::GreaterThanOrEqual,
        NumericComparison::GreaterThan => NumericComparison::LessThan,
        NumericComparison::GreaterThanOrEqual => NumericComparison::LessThanOrEqual,
    }
}

impl BuiltSpatialIndex {
    pub(in crate::execution) fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.build(records),
            Self::DirectPointHashGrid(index) => index.build_from_spatial_records(records),
            Self::Quadtree(index) => index.build(records),
            Self::Octree(index) => index.build(records),
            Self::Hilbert(index) => index.build(records),
        }
    }

    pub(in crate::execution) fn update_incremental(
        &mut self,
        records: &[SpatialRecord],
    ) -> Result<bool> {
        match self {
            Self::HashGrid(index) => index.update_incremental(records),
            Self::DirectPointHashGrid(index) => index.update_from_spatial_records(records),
            Self::Quadtree(index) => index.update_incremental(records),
            Self::Octree(index) => index.update_incremental(records),
            Self::Hilbert(index) => index.update_incremental(records),
        }
    }

    pub(in crate::execution) fn query_radius(
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

    pub(in crate::execution) fn query_radius_unordered(
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

    pub(in crate::execution) fn query_aabb(
        &self,
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_aabb(bounds, out),
            Self::DirectPointHashGrid(index) => index.query_aabb(bounds, out),
            Self::Quadtree(index) => index.query_aabb(bounds, out),
            Self::Octree(index) => index.query_aabb(bounds, out),
            Self::Hilbert(index) => index.query_aabb(bounds, out),
        }
    }

    pub(in crate::execution) fn visit_aabb_unordered<F>(
        &self,
        bounds: &SpatialAabb,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(&SpatialRecord) -> Result<()>,
    {
        match self {
            Self::Quadtree(index) => index.visit_aabb_unordered(bounds, visit),
            Self::Octree(index) => index.visit_aabb_unordered(bounds, visit),
            _ => {
                let mut records = Vec::new();
                self.query_aabb(bounds, &mut records)?;
                for record in &records {
                    visit(record)?;
                }
                Ok(())
            }
        }
    }
}
