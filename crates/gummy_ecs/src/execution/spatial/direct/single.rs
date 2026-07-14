use std::collections::HashSet;

use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::SpatialRecord;

use super::super::super::{EvalContext, PlanExecutor};
use super::super::helpers::{dimensions_len, direct_distance_squared};
use super::super::support::{
    effective_query_radius, BuiltSpatialIndex, SpatialBatchAccum, SpatialBatchValue,
    SpatialPrecomputeLayout,
};
use crate::execution::interpreter::value_ops::{bool_f64, literal_expr_numeric, truthy_f64};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn precompute_direct_spatial_aggregates_for_query(
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
                for relation in group {
                    self.precompute_aabb_count_spatial_relation_f64(&relation, layout)?;
                }
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
    pub(in crate::execution) fn precompute_direct_spatial_relation_f64(
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
        let query_radius = effective_query_radius(radius, distance_filter);
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
        let needs_delta = specs.iter().any(|spec| {
            matches!(
                spec.value,
                SpatialBatchValue::NegDeltaOverDistance { .. }
                    | SpatialBatchValue::Expression { .. }
            )
        });
        let origin_slot = self.query_slot(&relation.origin_query)?;
        let item_slot = self.query_slot(&relation.item_query)?;
        let query_slot_count = self.prepared.query_slot_count();
        let loop_slot_count = self.prepared.loop_slot_count();
        let mut candidates = Vec::new();
        let mut accumulators = vec![SpatialBatchAccum::default(); specs.len()];
        for origin_entity in origin_rows.iter().copied() {
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
                    let mut filter_ctx = EvalContext::new(query_slot_count, loop_slot_count);
                    filter_ctx.bindings[origin_slot] = Some(origin_entity);
                    filter_ctx.bindings[item_slot] = Some(record.entity);
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
                let mut joined: Option<EvalContext> = None;
                let mut item_cache: Option<Vec<Option<f64>>> = None;
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
                        SpatialBatchValue::Expression { expr_index } => {
                            let joined = joined.get_or_insert_with(|| {
                                let mut joined =
                                    EvalContext::new(query_slot_count, loop_slot_count);
                                joined.bindings[origin_slot] = Some(origin_entity);
                                joined.bindings[item_slot] = Some(record.entity);
                                joined
                            });
                            let item_cache = item_cache
                                .get_or_insert_with(|| vec![None; executor.plan.expressions.len()]);
                            executor.eval_expr_f64(*expr_index, joined, item_cache)?
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
}
