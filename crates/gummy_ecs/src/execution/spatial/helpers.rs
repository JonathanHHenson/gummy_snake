use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::SpatialAlgorithmKind;
use crate::plan::SpatialRelationNode;
use crate::spatial::{
    Dimensions, HashGridIndex, HilbertIndex, OctreeIndex, QuadtreeIndex, SpatialAabb, SpatialPoint,
};

use super::super::value_ops::bool_f64;
use super::point_hash_grid::DirectPointRecord;
use super::support::{
    BuiltSpatialIndex, FastAggregateKind, FastDirectSpatialRelationBatch, FastFieldArray,
    FastSpatialBatchValue, FastSpatialBinaryOp, FastSpatialValueExpr, SpatialBatchAccum,
    SpatialLocalCounters,
};

pub(in crate::execution) fn fast_field_array_value(
    array: &FastFieldArray,
    entity: Entity,
) -> Result<f64> {
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

pub(in crate::execution) fn fast_field_array_record_values(
    array: &FastFieldArray,
    records: &[DirectPointRecord],
) -> Result<Vec<f64>> {
    records
        .iter()
        .map(|record| fast_field_array_value(array, record.entity))
        .collect()
}

pub(in crate::execution) fn point_from_row_arrays(
    arrays: &[Vec<f64>],
    row_index: usize,
) -> Result<SpatialPoint> {
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

pub(in crate::execution) fn fast_aggregate_kind(kind: &str) -> Option<FastAggregateKind> {
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

pub(in crate::execution) fn spatial_result_values_are_dense(
    batches: &[FastDirectSpatialRelationBatch],
) -> bool {
    batches.iter().all(|batch| {
        batch.specs.iter().all(|spec| {
            matches!(
                spec.kind,
                FastAggregateKind::Any | FastAggregateKind::Count | FastAggregateKind::Sum
            )
        })
    })
}

pub(in crate::execution) fn accumulate_fast_spatial_value(
    kind: FastAggregateKind,
    value: f64,
    accumulator: &mut SpatialBatchAccum,
) {
    match kind {
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

pub(in crate::execution) fn fast_spatial_aggregate_value(
    kind: FastAggregateKind,
    exact_count: usize,
    accumulator: &SpatialBatchAccum,
) -> Option<f64> {
    match kind {
        FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
        FastAggregateKind::Count => Some(exact_count as f64),
        FastAggregateKind::Sum => Some(accumulator.sum),
        FastAggregateKind::Mean if accumulator.count > 0 => {
            Some(accumulator.sum / accumulator.count as f64)
        }
        FastAggregateKind::Min if accumulator.count > 0 => Some(accumulator.min),
        FastAggregateKind::Max if accumulator.count > 0 => Some(accumulator.max),
        _ => None,
    }
}

pub(in crate::execution) fn push_fast_spatial_aggregate_value(
    values: &mut Vec<f64>,
    present: &mut Option<Vec<bool>>,
    result_values_are_dense: bool,
    value: Option<f64>,
) {
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

#[allow(clippy::too_many_arguments)]
pub(in crate::execution) fn eval_fast_spatial_value_expr(
    expr: &FastSpatialValueExpr,
    item_field_arrays: &[FastFieldArray],
    item_record_field_arrays: Option<&[Vec<f64>]>,
    origin_point: &SpatialPoint,
    record_index: Option<usize>,
    record_entity: Entity,
    record_point: &SpatialPoint,
    distance_sq: f64,
) -> Result<f64> {
    match expr {
        FastSpatialValueExpr::Literal(value) => Ok(*value),
        FastSpatialValueExpr::OriginPointCoord { axis } => Ok(origin_point.coord(*axis)),
        FastSpatialValueExpr::ItemField { array_index } => {
            if let (Some(record_arrays), Some(record_index)) =
                (item_record_field_arrays, record_index)
            {
                Ok(record_arrays[*array_index][record_index])
            } else {
                fast_field_array_value(&item_field_arrays[*array_index], record_entity)
            }
        }
        FastSpatialValueExpr::ItemPointCoord { axis } => Ok(record_point.coord(*axis)),
        FastSpatialValueExpr::SpatialDelta { axis } => {
            Ok(record_point.coord(*axis) - origin_point.coord(*axis))
        }
        FastSpatialValueExpr::SpatialDistance => Ok(distance_sq.sqrt()),
        FastSpatialValueExpr::SpatialDistanceSq => Ok(distance_sq),
        FastSpatialValueExpr::Neg(input) => Ok(-eval_fast_spatial_value_expr(
            input,
            item_field_arrays,
            item_record_field_arrays,
            origin_point,
            record_index,
            record_entity,
            record_point,
            distance_sq,
        )?),
        FastSpatialValueExpr::Binary { op, left, right } => {
            let left = eval_fast_spatial_value_expr(
                left,
                item_field_arrays,
                item_record_field_arrays,
                origin_point,
                record_index,
                record_entity,
                record_point,
                distance_sq,
            )?;
            let right = eval_fast_spatial_value_expr(
                right,
                item_field_arrays,
                item_record_field_arrays,
                origin_point,
                record_index,
                record_entity,
                record_point,
                distance_sq,
            )?;
            Ok(match op {
                FastSpatialBinaryOp::Add => left + right,
                FastSpatialBinaryOp::Sub => left - right,
                FastSpatialBinaryOp::Mul => left * right,
                FastSpatialBinaryOp::Div => left / right,
                FastSpatialBinaryOp::Min => left.min(right),
                FastSpatialBinaryOp::Max => left.max(right),
            })
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(in crate::execution) fn process_fast_spatial_record(
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
                FastSpatialBatchValue::Expression { expr } => eval_fast_spatial_value_expr(
                    expr,
                    item_field_arrays,
                    item_record_field_arrays,
                    origin_point,
                    record_index,
                    record_entity,
                    record_point,
                    distance_sq,
                )?,
            };
            let accumulator = &mut accumulators[batch_index][spec_index];
            accumulate_fast_spatial_value(spec.kind, value, accumulator);
        }
    }
    Ok(())
}

pub(in crate::execution) fn dimensions_from_u8(dimensions: u8) -> Result<Dimensions> {
    match dimensions {
        2 => Ok(Dimensions::D2),
        3 => Ok(Dimensions::D3),
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

pub(in crate::execution) fn dimensions_len(dimensions: u8) -> Result<usize> {
    Ok(dimensions_from_u8(dimensions)?.len())
}

pub(in crate::execution) fn point_bounds(point: &SpatialPoint) -> Result<SpatialAabb> {
    SpatialAabb::new(point.clone(), point.clone())
}

pub(in crate::execution) fn direct_distance_squared(
    left: &SpatialPoint,
    right: &SpatialPoint,
    dimensions: usize,
) -> f64 {
    let mut distance_sq = 0.0;
    for axis in 0..dimensions {
        let delta = right.coord(axis) - left.coord(axis);
        distance_sq += delta * delta;
    }
    distance_sq
}

pub(in crate::execution) fn should_try_incremental_spatial_update(
    record_count: usize,
    previous_field_revision: u64,
    current_field_revision: u64,
) -> bool {
    let changed_field_writes = current_field_revision.saturating_sub(previous_field_revision);
    let incremental_write_budget = (record_count / 4).max(1) as u64;
    changed_field_writes <= incremental_write_budget
}

pub(in crate::execution) fn spatial_index_base_signature(relation: &SpatialRelationNode) -> String {
    format!(
        "item={};target_pos={:?};target_bounds={:?};algorithm={:?}",
        relation.item_query, relation.target_position, relation.target_bounds, relation.algorithm
    )
}

pub(in crate::execution) fn spatial_relations_same_direct_precompute_group(
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

pub(in crate::execution) fn spatial_relations_same_multi_origin_precompute_group(
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

pub(in crate::execution) fn spatial_relations_same_base(
    left: &SpatialRelationNode,
    right: &SpatialRelationNode,
) -> bool {
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

pub(in crate::execution) fn build_spatial_index(
    algorithm: &crate::plan::SpatialAlgorithmNode,
    kind: SpatialAlgorithmKind,
) -> Result<BuiltSpatialIndex> {
    let dimensions = dimensions_from_u8(algorithm.dimensions)?;
    match kind {
        SpatialAlgorithmKind::HashGrid => Ok(BuiltSpatialIndex::HashGrid(HashGridIndex::new(
            dimensions,
            algorithm.cell_size.unwrap_or(1.0),
        )?)),
        SpatialAlgorithmKind::Quadtree => {
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
        SpatialAlgorithmKind::Octree => {
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
        SpatialAlgorithmKind::Hilbert => {
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
        SpatialAlgorithmKind::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported spatial algorithm '{}'",
            algorithm.kind
        ))),
    }
}
