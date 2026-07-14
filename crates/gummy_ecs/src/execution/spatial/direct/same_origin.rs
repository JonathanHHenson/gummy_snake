use std::time::Instant;

use rayon::prelude::*;

use crate::error::{EcsError, Result};
use crate::plan::SpatialRelationNode;

use super::super::super::PlanExecutor;
use super::super::helpers::{
    dimensions_len, direct_distance_squared, fast_aggregate_kind, fast_field_array_record_values,
    fast_spatial_aggregate_value, point_from_row_arrays, process_fast_spatial_record,
    push_fast_spatial_aggregate_value, spatial_relations_same_direct_precompute_group,
    spatial_result_values_are_dense,
};
use super::super::support::{
    BuiltSpatialIndex, FastDirectSpatialRelationBatch, FastFieldArray, FastSpatialBatchSpec,
    FastSpatialBatchValue, SpatialBatchAccum, SpatialBatchValue, SpatialChunkResult,
    SpatialLocalCounters, SpatialPrecomputeLayout,
};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn precompute_direct_spatial_relation_group_f64(
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
                    SpatialBatchValue::Expression { expr_index } => {
                        let Some(expr) = self.compile_fast_spatial_value_expr(
                            expr_index,
                            relation,
                            &origin_coords,
                            &target_coords,
                            &mut item_field_arrays,
                            &item_rows,
                            &item_locations,
                        )?
                        else {
                            return Ok(false);
                        };
                        FastSpatialBatchValue::Expression { expr }
                    }
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
                .map(|array| fast_field_array_record_values(array, index.records()))
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

        let max_radius = batches
            .iter()
            .map(|batch| batch.query_radius)
            .fold(0.0_f64, f64::max);
        if layout == SpatialPrecomputeLayout::QueryRows {
            if let BuiltSpatialIndex::DirectPointHashGrid(item_index) = index {
                if !item_index.has_regular_grid()
                    && item_index.record_count() >= 1024
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
                            let value =
                                fast_spatial_aggregate_value(spec.kind, exact_count, accumulator);
                            push_fast_spatial_aggregate_value(
                                &mut values,
                                &mut present,
                                result_values_are_dense,
                                value,
                            );
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
        let chunk_count = chunk_results.len();
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        self.report.spatial_parallel_chunks += chunk_count;
        self.report.spatial_thread_scratch_reuses += origin_rows.len().saturating_sub(chunk_count);
        self.store_spatial_chunk_results_f64(
            layout,
            chunk_results,
            &result_exprs,
            result_count,
            origin_rows.len(),
            result_values_are_dense,
        )?;
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
}
