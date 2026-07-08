use crate::entity::Entity;
use crate::error::Result;
use crate::plan::SpatialRelationNode;

use super::super::direct_point_hash_grid::DirectPointHashGrid;
use super::super::spatial_helpers::{
    accumulate_fast_spatial_value, fast_field_array_value, fast_spatial_aggregate_value,
    spatial_result_values_are_dense,
};
use super::super::spatial_support::{
    BuiltSpatialIndex, FastAggregateKind, FastDirectSpatialRelationBatch, FastFieldArray,
    FastSpatialBatchValue, SpatialBatchAccum, SpatialF64RowArray, SpatialLocalCounters,
};

use super::super::PlanExecutor;

impl<'a> PlanExecutor<'a> {
    #[allow(clippy::too_many_arguments)]
    pub(in crate::execution) fn precompute_inverted_direct_spatial_relation_group_f64(
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
        if result_count == 0 || origin_rows.is_empty() || item_index.is_empty() {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(batches);
        let mut origin_index_relation = relation.clone();
        origin_index_relation.index_id = format!("inverted_origin:{}", relation.origin_query);
        origin_index_relation.item_query = relation.origin_query.clone();
        origin_index_relation.target_position = relation.origin_position.clone();
        origin_index_relation.target_bounds = None;
        let Some((origin_index_key, BuiltSpatialIndex::DirectPointHashGrid(origin_index))) =
            self.build_direct_spatial_index_for_relation(&origin_index_relation)?
        else {
            return Ok(false);
        };
        if !origin_index.has_regular_grid()
            && item_index.record_count().saturating_mul(4) >= origin_rows.len()
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

        let dense_sum_only = result_values_are_dense
            && batches.iter().all(|batch| {
                batch
                    .specs
                    .iter()
                    .all(|spec| spec.kind == FastAggregateKind::Sum)
            });
        if dense_sum_only {
            let mut row_result_arrays = result_exprs
                .iter()
                .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                .collect::<Vec<_>>();
            let mut counters = SpatialLocalCounters::default();
            for (item_record_index, item_record) in item_index.records().iter().enumerate() {
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
                            counters.rows_scanned += 1;
                            counters.exact_rows += 1;
                            let spec_offset = spec_offsets[batch_index];
                            for (spec_index, spec) in batch.specs.iter().enumerate() {
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
                                        let delta_axis = item_point.coord(*axis)
                                            - origin_record.point.coord(*axis);
                                        -delta_axis * inverse_distance
                                    }
                                };
                                row_result_arrays[spec_offset + spec_index].1[origin_index] +=
                                    value;
                            }
                        }
                        Ok(())
                    },
                )?;
            }
            for (expr_index, values) in row_result_arrays {
                self.spatial_precomputed_f64_rows
                    .insert(expr_index, SpatialF64RowArray::Dense(values));
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
            return Ok(true);
        }

        let mut accumulators = vec![SpatialBatchAccum::default(); origin_rows.len() * result_count];
        let mut exact_counts = vec![0usize; origin_rows.len() * batches.len()];
        let mut counters = SpatialLocalCounters::default();

        for (item_record_index, item_record) in item_index.records().iter().enumerate() {
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
                            accumulate_fast_spatial_value(spec.kind, value, accumulator);
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
                        let value =
                            fast_spatial_aggregate_value(spec.kind, exact_count, accumulator)
                                .unwrap_or(0.0);
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
                        let value =
                            fast_spatial_aggregate_value(spec.kind, exact_count, accumulator);
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
}
