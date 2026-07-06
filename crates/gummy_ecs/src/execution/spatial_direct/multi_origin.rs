use std::time::Instant;

use rayon::prelude::*;

use crate::error::{EcsError, Result};
use crate::plan::SpatialRelationNode;

use super::super::spatial_helpers::{
    dimensions_len, direct_distance_squared, fast_aggregate_kind, fast_field_array_record_values,
    point_from_row_arrays, process_fast_spatial_record,
    spatial_relations_same_multi_origin_precompute_group, spatial_result_values_are_dense,
};
use super::super::spatial_support::{
    BuiltSpatialIndex, FastAggregateKind, FastDirectSpatialRelationBatch, FastFieldArray,
    FastSpatialBatchSpec, FastSpatialBatchValue, SpatialBatchAccum, SpatialBatchValue,
    SpatialChunkResult, SpatialF64RowArray, SpatialLocalCounters, SpatialPrecomputeLayout,
};
use super::super::value_ops::bool_f64;
use super::super::PlanExecutor;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn precompute_multi_origin_direct_spatial_relation_group_f64(
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
}
