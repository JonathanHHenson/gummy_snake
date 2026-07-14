use std::time::Instant;

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::{AggregateKind, SpatialMetadataKind};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::SpatialRecord;

use super::super::{EvalContext, PlanExecutor};
use super::helpers::{dimensions_len, spatial_relations_same_base};
use super::support::{
    comparison_from_op, reverse_comparison, NumericComparison, SpatialDistanceFilter,
};
use crate::execution::interpreter::aggregate_eval::{aggregate_empty, aggregate_finish};
use crate::execution::interpreter::value_ops::literal_expr_numeric;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn eval_spatial_metadata(
        &mut self,
        relation: &SpatialRelationNode,
        kind: SpatialMetadataKind,
        source_name: &str,
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
        if matches!(kind, SpatialMetadataKind::Delta) {
            let axis = axis.ok_or_else(|| {
                EcsError::InvalidPlan("spatial delta metadata requires an axis".to_string())
            })?;
            return Ok(EcsValue::F64(delta[axis]));
        }
        let distance_sq = delta.iter().map(|value| value * value).sum::<f64>();
        match kind {
            SpatialMetadataKind::DistanceSq => Ok(EcsValue::F64(distance_sq)),
            SpatialMetadataKind::Distance => Ok(EcsValue::F64(distance_sq.sqrt())),
            SpatialMetadataKind::Delta => Err(EcsError::InvalidPlan(
                "spatial delta metadata requires an axis".to_string(),
            )),
            SpatialMetadataKind::Unknown => Err(EcsError::InvalidPlan(format!(
                "unsupported spatial metadata kind '{source_name}'"
            ))),
        }
    }

    pub(in crate::execution) fn eval_spatial_aggregate(
        &mut self,
        kind: AggregateKind,
        source_name: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        if matches!(kind, AggregateKind::Any) {
            return Ok(EcsValue::Bool(count > 0));
        }
        if let Some(value_expr) = value {
            if let Some(result) = self.try_direct_spatial_numeric_aggregate(
                kind,
                source_name,
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
            let item_slot = self.query_slot(&relation.item_query)?;
            for record in records.iter() {
                let mut joined = ctx.clone();
                joined.bindings[item_slot] = Some(record.entity);
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, source_name, count, values, default, self, ctx)
    }

    pub(in crate::execution) fn try_count_spatial_relation(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Option<usize>> {
        let Some(origin_bounds_expr) = &relation.origin_bounds else {
            return Ok(None);
        };
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        if relation.exact_filter.is_some() && distance_filter.is_none() {
            return Ok(None);
        }
        let origin_entity = self
            .bound_entity(ctx, &relation.origin_query)
            .map_err(|_| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        let origin_point = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let origin_bounds = self.eval_spatial_bounds(origin_bounds_expr, ctx)?;
        let profile = self.profile;
        let index_start = profile.then(Instant::now);
        let index = self.ensure_spatial_index(relation, ctx)?;
        let index_nanos = index_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        let query_start = profile.then(Instant::now);
        let mut count = 0usize;
        let mut candidate_rows = 0usize;
        let mut exact_rows = 0usize;
        let mut rows_scanned = 0usize;
        let mut deduplicated_pairs = 0usize;
        let mut false_positive_rows = 0usize;
        let dimensions = origin_bounds.dimensions().len();
        index.visit_aabb_unordered(&origin_bounds, &mut |record| {
            candidate_rows += 1;
            if !relation.include_self && record.entity == origin_entity {
                return Ok(());
            }
            if relation.pair_policy == "unique_unordered"
                && record.entity.raw() <= origin_entity.raw()
            {
                deduplicated_pairs += 1;
                return Ok(());
            }
            let overlaps = if let Some(record_bounds) = &record.bounds {
                origin_bounds.overlaps(record_bounds)?
            } else if record.point.dimensions() == origin_bounds.dimensions() {
                (0..dimensions).all(|axis| {
                    let coord = record.point.coord(axis);
                    origin_bounds.minimum().coord(axis) <= coord
                        && coord <= origin_bounds.maximum().coord(axis)
                })
            } else {
                return Err(EcsError::InvalidSpatialInput(
                    "spatial AABB dimensions must match".to_string(),
                ));
            };
            if !overlaps {
                false_positive_rows += 1;
                return Ok(());
            }
            if let Some(distance_filter) = distance_filter {
                if !distance_filter.matches(origin_point.distance_squared(&record.point)?) {
                    return Ok(());
                }
            }
            rows_scanned += 1;
            exact_rows += 1;
            count += 1;
            Ok(())
        })?;
        let query_nanos = query_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        if profile {
            self.profile_spatial_index_nanos += index_nanos;
            self.profile_spatial_query_nanos += query_nanos;
        }
        self.report.spatial_candidate_rows += candidate_rows;
        self.report.spatial_deduplicated_pairs += deduplicated_pairs;
        self.report.spatial_false_positive_rows += false_positive_rows;
        self.report.rows_scanned += rows_scanned;
        self.report.spatial_exact_rows += exact_rows;
        Ok(Some(count))
    }

    #[allow(clippy::too_many_arguments)]
    pub(in crate::execution) fn try_direct_spatial_numeric_aggregate(
        &mut self,
        kind: AggregateKind,
        source_name: &str,
        relation: &SpatialRelationNode,
        value_expr: usize,
        records: &[SpatialRecord],
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<Option<EcsValue>> {
        let aggregate_start = self.profile.then(Instant::now);
        if matches!(kind, AggregateKind::Sum) {
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
                AggregateKind::Sum => Ok(Some(EcsValue::F64(0.0))),
                AggregateKind::Min | AggregateKind::Max | AggregateKind::Mean => {
                    aggregate_empty(kind, source_name, default, self, ctx).map(Some)
                }
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
            AggregateKind::Sum => Some(EcsValue::F64(sum)),
            AggregateKind::Mean => Some(EcsValue::F64(sum / records.len() as f64)),
            AggregateKind::Min => Some(EcsValue::F64(min_value)),
            AggregateKind::Max => Some(EcsValue::F64(max_value)),
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

    pub(in crate::execution) fn match_neg_delta_over_clamped_distance(
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

    pub(in crate::execution) fn match_neg_spatial_delta(
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

    pub(in crate::execution) fn match_clamped_spatial_distance(
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

    pub(in crate::execution) fn is_spatial_distance(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> bool {
        matches!(
            &self.plan.expressions[expr_index],
            ExprNode::SpatialMetadata {
                relation: metadata_relation,
                kind,
                axis: None,
            } if kind == "distance" && spatial_relations_same_base(metadata_relation, relation)
        )
    }

    pub(in crate::execution) fn match_spatial_distance_filter(
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

    pub(in crate::execution) fn match_spatial_distance_filter_side(
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
}
