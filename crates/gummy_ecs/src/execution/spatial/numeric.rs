use crate::error::{EcsError, Result};
use crate::plan::typed_ir::AggregateKind;
use crate::plan::{ExprNode, SpatialRelationNode};

use super::super::{EvalContext, PlanExecutor};
use super::helpers::dimensions_len;
use super::support::{SpatialBatchAccum, SpatialBatchSpec, SpatialBatchValue};
use crate::execution::interpreter::aggregate_eval::{aggregate_empty, aggregate_finish};
use crate::execution::interpreter::value_ops::{bool_f64, numeric_f64};

impl<'a> PlanExecutor<'a> {
    #[allow(clippy::too_many_arguments)]
    pub(in crate::execution) fn eval_spatial_aggregate_f64(
        &mut self,
        expr_index: usize,
        kind: AggregateKind,
        source_name: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if cache[expr_index].is_none() {
            let origin_slot = self.query_slot(&relation.origin_query)?;
            if let Some(origin_entity) = ctx.bindings.get(origin_slot).copied().flatten() {
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
            AggregateKind::Any => return Ok(bool_f64(count > 0)),
            AggregateKind::Count => return Ok(count as f64),
            _ => {}
        }
        let Some(value_expr) = value else {
            return numeric_f64(&aggregate_finish(
                kind,
                source_name,
                count,
                Vec::new(),
                default,
                self,
                ctx,
            )?);
        };
        if let Some(result) = self.try_direct_spatial_numeric_aggregate(
            kind,
            source_name,
            relation,
            value_expr,
            records.as_ref(),
            default,
            ctx,
        )? {
            return numeric_f64(&result);
        }
        if count == 0 {
            return numeric_f64(&aggregate_empty(kind, source_name, default, self, ctx)?);
        }
        let mut sum = 0.0;
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        let item_slot = self.query_slot(&relation.item_query)?;
        for record in records.iter() {
            let mut joined = ctx.clone();
            joined.bindings[item_slot] = Some(record.entity);
            let mut item_cache = vec![None; self.plan.expressions.len()];
            let value = self.eval_expr_f64(value_expr, &joined, &mut item_cache)?;
            sum += value;
            min_value = min_value.min(value);
            max_value = max_value.max(value);
        }
        match kind {
            AggregateKind::Sum => Ok(sum),
            AggregateKind::Mean => Ok(sum / count as f64),
            AggregateKind::Min => Ok(min_value),
            AggregateKind::Max => Ok(max_value),
            _ => Err(EcsError::InvalidPlan(format!(
                "unsupported aggregate kind '{source_name}'"
            ))),
        }
    }

    pub(in crate::execution) fn spatial_batch_specs_for_relation(
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
                            SpatialBatchValue::Expression {
                                expr_index: *value_expr,
                            }
                        } else {
                            SpatialBatchValue::DirectField {
                                component: component.clone(),
                                field: field.clone(),
                            }
                        }
                    } else if self
                        .expr_supports_f64(*value_expr, &mut std::collections::HashSet::new())
                    {
                        SpatialBatchValue::Expression {
                            expr_index: *value_expr,
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

        let origin_entity = self
            .bound_entity(ctx, &relation.origin_query)
            .map_err(|_| {
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
        let item_slot = self.query_slot(&relation.item_query)?;
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
                    SpatialBatchValue::Expression { expr_index } => {
                        let mut joined = ctx.clone();
                        joined.bindings[item_slot] = Some(record.entity);
                        let mut item_cache = vec![None; self.plan.expressions.len()];
                        self.eval_expr_f64(*expr_index, &joined, &mut item_cache)?
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
}
