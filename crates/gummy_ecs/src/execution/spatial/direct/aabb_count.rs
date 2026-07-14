use std::collections::{HashMap, HashSet};

use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::{SpatialAabb, SpatialPoint, SpatialRecord};

use super::super::super::value_ops::{bool_f64, literal_expr_numeric};
use super::super::super::{EvalContext, PlanExecutor};

use super::super::support::{
    SpatialBatchValue, SpatialDistanceFilter, SpatialF64RowArray, SpatialPrecomputeLayout,
};

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
        let empty_context = EvalContext::new(
            self.prepared.query_slot_count(),
            self.prepared.loop_slot_count(),
        );
        let small_target_records = self
            .query_rows
            .get(&relation.item_query)
            .is_some_and(|rows| rows.len() <= 128)
            .then(|| self.build_spatial_records(relation, &empty_context))
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
                for (row_index, origin_entity) in origin_rows.iter().copied().enumerate() {
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
        let origin_slot = self.query_slot(&relation.origin_query)?;
        let Some(target_records) = small_target_records else {
            let mut ctx = EvalContext::new(
                self.prepared.query_slot_count(),
                self.prepared.loop_slot_count(),
            );
            ctx.bindings[origin_slot] = Some(origin_entity);
            return self
                .try_count_spatial_relation(relation, &ctx)?
                .ok_or_else(|| {
                    EcsError::InvalidPlan("AABB count relation was not countable".to_string())
                });
        };
        let (origin_point, origin_bounds) = if let Some(direct_origin) = direct_origin {
            self.direct_origin_point_and_bounds(direct_origin, row_index)?
        } else {
            let mut ctx = EvalContext::new(
                self.prepared.query_slot_count(),
                self.prepared.loop_slot_count(),
            );
            ctx.bindings[origin_slot] = Some(origin_entity);
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
}
