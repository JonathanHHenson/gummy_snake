use std::collections::{HashMap, HashSet};

use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::{SpatialAabb, SpatialPoint, SpatialRecord};

use super::super::spatial_helpers::{dimensions_len, direct_distance_squared};
use super::super::spatial_support::{
    effective_query_radius, BuiltSpatialIndex, SpatialBatchAccum, SpatialBatchValue,
    SpatialDistanceFilter, SpatialF64RowArray, SpatialPrecomputeLayout,
};
use super::super::value_ops::{bool_f64, literal_expr_numeric, truthy_f64};
use super::super::{EvalContext, PlanExecutor};

#[derive(Clone, Copy)]
enum DirectRowBinaryOp {
    Add,
    Sub,
    Mul,
    Div,
    Min,
    Max,
}

#[derive(Clone)]
enum DirectRowF64Expr {
    Literal(f64),
    Field(usize),
    Neg(Box<DirectRowF64Expr>),
    Binary {
        op: DirectRowBinaryOp,
        left: Box<DirectRowF64Expr>,
        right: Box<DirectRowF64Expr>,
    },
}

struct DirectRowSpatialInput {
    point: Vec<DirectRowF64Expr>,
    minimum: Vec<DirectRowF64Expr>,
    maximum: Vec<DirectRowF64Expr>,
    fields: Vec<Vec<f64>>,
}

fn eval_direct_row_f64(expr: &DirectRowF64Expr, fields: &[Vec<f64>], row_index: usize) -> f64 {
    match expr {
        DirectRowF64Expr::Literal(value) => *value,
        DirectRowF64Expr::Field(slot) => fields[*slot][row_index],
        DirectRowF64Expr::Neg(input) => -eval_direct_row_f64(input, fields, row_index),
        DirectRowF64Expr::Binary { op, left, right } => {
            let left = eval_direct_row_f64(left, fields, row_index);
            let right = eval_direct_row_f64(right, fields, row_index);
            match op {
                DirectRowBinaryOp::Add => left + right,
                DirectRowBinaryOp::Sub => left - right,
                DirectRowBinaryOp::Mul => left * right,
                DirectRowBinaryOp::Div => left / right,
                DirectRowBinaryOp::Min => left.min(right),
                DirectRowBinaryOp::Max => left.max(right),
            }
        }
    }
}

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

    pub(in crate::execution) fn precompute_aabb_count_spatial_relation_f64(
        &mut self,
        relation: &SpatialRelationNode,
        layout: SpatialPrecomputeLayout,
    ) -> Result<bool> {
        if relation.origin_bounds.is_none() {
            return Ok(false);
        }
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty()
            || specs.iter().any(|spec| {
                !matches!(spec.kind.as_str(), "any" | "count")
                    || !matches!(spec.value, SpatialBatchValue::Count)
            })
        {
            return Ok(false);
        }
        if relation.exact_filter.is_some()
            && relation
                .exact_filter
                .and_then(|expr| self.match_spatial_distance_filter(expr, relation))
                .is_none()
        {
            return Ok(false);
        }
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
        if origin_rows.is_empty() {
            return Ok(true);
        }
        let small_target_records = self
            .query_rows
            .get(&relation.item_query)
            .is_some_and(|rows| rows.len() <= 128)
            .then(|| self.build_spatial_records(relation, &EvalContext::default()))
            .transpose()?;
        let direct_origin = if small_target_records.is_some() {
            self.compile_direct_row_spatial_input(relation, &origin_rows)?
        } else {
            None
        };
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        match layout {
            SpatialPrecomputeLayout::QueryRows => {
                let mut result_arrays = specs
                    .iter()
                    .map(|spec| (spec.expr_index, vec![0.0; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for (row_index, origin_entity) in origin_rows.iter().copied().enumerate() {
                    let count = self.precompute_aabb_count_for_origin(
                        relation,
                        origin_entity,
                        row_index,
                        small_target_records.as_deref(),
                        direct_origin.as_ref(),
                        distance_filter,
                    )?;
                    for (spec, (_, values)) in specs.iter().zip(result_arrays.iter_mut()) {
                        values[row_index] = match spec.kind.as_str() {
                            "any" => bool_f64(count > 0),
                            "count" => count as f64,
                            _ => unreachable!("spec kind checked above"),
                        };
                    }
                }
                for (expr_index, values) in result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Dense(values));
                }
            }
            SpatialPrecomputeLayout::SparseEntity => {
                for (row_index, origin_entity) in origin_rows.into_iter().enumerate() {
                    let count = self.precompute_aabb_count_for_origin(
                        relation,
                        origin_entity,
                        row_index,
                        small_target_records.as_deref(),
                        direct_origin.as_ref(),
                        distance_filter,
                    )?;
                    for spec in &specs {
                        let value = match spec.kind.as_str() {
                            "any" => bool_f64(count > 0),
                            "count" => count as f64,
                            _ => unreachable!("spec kind checked above"),
                        };
                        self.store_precomputed_spatial_f64(spec.expr_index, origin_entity, value);
                    }
                }
            }
        }
        Ok(true)
    }

    fn compile_direct_row_spatial_input(
        &mut self,
        relation: &SpatialRelationNode,
        origin_rows: &[crate::entity::Entity],
    ) -> Result<Option<DirectRowSpatialInput>> {
        let Some(origin_bounds) = &relation.origin_bounds else {
            return Ok(None);
        };
        let origin_locations = self.query_locations(&relation.origin_query)?;
        let mut fields = Vec::new();
        let mut slots = HashMap::new();
        let mut compile_expr = |executor: &Self, expr| {
            executor.compile_direct_row_f64_expr(
                expr,
                &relation.origin_query,
                origin_rows,
                &origin_locations,
                &mut fields,
                &mut slots,
                &mut HashSet::new(),
            )
        };
        let point = relation
            .origin_position
            .iter()
            .map(|expr| compile_expr(self, *expr))
            .collect::<Result<Option<Vec<_>>>>()?;
        let Some(point) = point else {
            return Ok(None);
        };
        let minimum = origin_bounds
            .minimum
            .iter()
            .map(|expr| compile_expr(self, *expr))
            .collect::<Result<Option<Vec<_>>>>()?;
        let Some(minimum) = minimum else {
            return Ok(None);
        };
        let maximum = origin_bounds
            .maximum
            .iter()
            .map(|expr| compile_expr(self, *expr))
            .collect::<Result<Option<Vec<_>>>>()?;
        let Some(maximum) = maximum else {
            return Ok(None);
        };
        Ok(Some(DirectRowSpatialInput {
            point,
            minimum,
            maximum,
            fields,
        }))
    }

    #[allow(clippy::too_many_arguments)]
    fn compile_direct_row_f64_expr(
        &self,
        expr_index: usize,
        query_name: &str,
        rows: &[crate::entity::Entity],
        locations: &[(usize, usize)],
        fields: &mut Vec<Vec<f64>>,
        slots: &mut HashMap<(String, String), usize>,
        seen: &mut HashSet<usize>,
    ) -> Result<Option<DirectRowF64Expr>> {
        if !seen.insert(expr_index) {
            return Ok(None);
        }
        let result = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Some(DirectRowF64Expr::Literal(*value)),
            ExprNode::LiteralI64(value) => Some(DirectRowF64Expr::Literal(*value as f64)),
            ExprNode::LiteralBool(value) => Some(DirectRowF64Expr::Literal(bool_f64(*value))),
            ExprNode::LiteralValue(value) => {
                literal_expr_numeric(&ExprNode::LiteralValue(value.clone()))
                    .map(DirectRowF64Expr::Literal)
            }
            ExprNode::Field {
                query,
                component,
                field,
            } if query == query_name => {
                let key = (component.clone(), field.clone());
                let slot = if let Some(slot) = slots.get(&key) {
                    *slot
                } else {
                    let slot = fields.len();
                    fields.push(
                        self.world
                            .field_f64_rows_for_resolved_entities(component, field, locations)?,
                    );
                    debug_assert_eq!(fields[slot].len(), rows.len());
                    slots.insert(key, slot);
                    slot
                };
                Some(DirectRowF64Expr::Field(slot))
            }
            ExprNode::Unary { op, input } if matches!(op.as_str(), "neg" | "-") => {
                let input = self.compile_direct_row_f64_expr(
                    *input, query_name, rows, locations, fields, slots, seen,
                )?;
                input.map(|input| DirectRowF64Expr::Neg(Box::new(input)))
            }
            ExprNode::Binary { op, left, right } => {
                let op = match op.as_str() {
                    "add" | "+" => Some(DirectRowBinaryOp::Add),
                    "sub" | "-" => Some(DirectRowBinaryOp::Sub),
                    "mul" | "*" => Some(DirectRowBinaryOp::Mul),
                    "truediv" | "/" => Some(DirectRowBinaryOp::Div),
                    "min" => Some(DirectRowBinaryOp::Min),
                    "max" => Some(DirectRowBinaryOp::Max),
                    _ => None,
                };
                if let Some(op) = op {
                    let left = self.compile_direct_row_f64_expr(
                        *left, query_name, rows, locations, fields, slots, seen,
                    )?;
                    let right = self.compile_direct_row_f64_expr(
                        *right, query_name, rows, locations, fields, slots, seen,
                    )?;
                    match (left, right) {
                        (Some(left), Some(right)) => Some(DirectRowF64Expr::Binary {
                            op,
                            left: Box::new(left),
                            right: Box::new(right),
                        }),
                        _ => None,
                    }
                } else {
                    None
                }
            }
            _ => None,
        };
        seen.remove(&expr_index);
        Ok(result)
    }

    fn direct_origin_point_and_bounds(
        &self,
        direct: &DirectRowSpatialInput,
        row_index: usize,
    ) -> Result<(SpatialPoint, SpatialAabb)> {
        let point_values = direct
            .point
            .iter()
            .map(|expr| eval_direct_row_f64(expr, &direct.fields, row_index))
            .collect::<Vec<_>>();
        let minimum_values = direct
            .minimum
            .iter()
            .map(|expr| eval_direct_row_f64(expr, &direct.fields, row_index))
            .collect::<Vec<_>>();
        let maximum_values = direct
            .maximum
            .iter()
            .map(|expr| eval_direct_row_f64(expr, &direct.fields, row_index))
            .collect::<Vec<_>>();
        let point = match point_values.as_slice() {
            [x, y] => SpatialPoint::point2(*x, *y)?,
            [x, y, z] => SpatialPoint::point3(*x, *y, *z)?,
            _ => {
                return Err(EcsError::InvalidPlan(
                    "spatial points must have 2 or 3 coordinates".to_string(),
                ))
            }
        };
        let bounds = match (minimum_values.as_slice(), maximum_values.as_slice()) {
            ([min_x, min_y], [max_x, max_y]) => {
                SpatialAabb::point2(*min_x, *min_y, *max_x, *max_y)?
            }
            ([min_x, min_y, min_z], [max_x, max_y, max_z]) => {
                SpatialAabb::point3(*min_x, *min_y, *min_z, *max_x, *max_y, *max_z)?
            }
            _ => {
                return Err(EcsError::InvalidPlan(
                    "spatial bounds must have 2 or 3 dimensions".to_string(),
                ))
            }
        };
        Ok((point, bounds))
    }

    fn precompute_aabb_count_for_origin(
        &mut self,
        relation: &SpatialRelationNode,
        origin_entity: crate::entity::Entity,
        row_index: usize,
        small_target_records: Option<&[SpatialRecord]>,
        direct_origin: Option<&DirectRowSpatialInput>,
        distance_filter: Option<SpatialDistanceFilter>,
    ) -> Result<usize> {
        let Some(target_records) = small_target_records else {
            let mut ctx = EvalContext::default();
            ctx.bindings
                .insert(relation.origin_query.clone(), origin_entity);
            return self
                .try_count_spatial_relation(relation, &ctx)?
                .ok_or_else(|| {
                    EcsError::InvalidPlan("AABB count relation was not countable".to_string())
                });
        };
        let (origin_point, origin_bounds) = if let Some(direct_origin) = direct_origin {
            self.direct_origin_point_and_bounds(direct_origin, row_index)?
        } else {
            let mut ctx = EvalContext::default();
            ctx.bindings
                .insert(relation.origin_query.clone(), origin_entity);
            let origin_point = self.eval_spatial_point(&relation.origin_position, &ctx)?;
            let origin_bounds = relation
                .origin_bounds
                .as_ref()
                .map(|bounds| self.eval_spatial_bounds(bounds, &ctx))
                .transpose()?
                .ok_or_else(|| {
                    EcsError::InvalidPlan(
                        "AABB count precompute requires origin bounds".to_string(),
                    )
                })?;
            (origin_point, origin_bounds)
        };
        let dimensions = origin_bounds.dimensions().len();
        let mut count = 0usize;
        for record in target_records {
            self.report.spatial_candidate_rows += 1;
            if !relation.include_self && record.entity == origin_entity {
                continue;
            }
            if relation.pair_policy == "unique_unordered"
                && record.entity.raw() <= origin_entity.raw()
            {
                self.report.spatial_deduplicated_pairs += 1;
                continue;
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
                self.report.spatial_false_positive_rows += 1;
                continue;
            }
            if let Some(distance_filter) = distance_filter {
                if !distance_filter.matches(origin_point.distance_squared(&record.point)?) {
                    continue;
                }
            }
            self.report.rows_scanned += 1;
            self.report.spatial_exact_rows += 1;
            count += 1;
        }
        Ok(count)
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
}
