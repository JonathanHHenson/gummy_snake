use std::collections::{BTreeSet, HashMap};

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::ExprNode;

use super::super::f64_program::{eval_binary_f64, eval_unary_f64};
use super::super::{EvalContext, ExprCacheKey, PlanExecutor, TypedExpr};
use super::aggregate_eval::{aggregate_empty, aggregate_finish};
use super::value_ops::{
    bool_f64, default_input_state_value, eval_binary, eval_unary, numeric_f64, truthy, truthy_f64,
};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn eval_expr_f64(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if let Some(value) = cache[expr_index] {
            return Ok(value);
        }
        let value = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => *value,
            ExprNode::LiteralI64(value) => *value as f64,
            ExprNode::LiteralBool(value) => bool_f64(*value),
            ExprNode::LiteralValue(value) => numeric_f64(value)?,
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = self.bound_entity(ctx, query)?;
                self.entity_field_f64(entity, component, field)?
            }
            ExprNode::ResourceField { resource, field } => {
                numeric_f64(&self.world.resource_field(resource, field)?)?
            }
            ExprNode::InputState { name, code } => numeric_f64(
                &self
                    .world
                    .input_state(name, *code)
                    .unwrap_or_else(|| default_input_state_value(name)),
            )?,
            ExprNode::Unary { op, input } => {
                let TypedExpr::Unary(typed_op) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let input = self.eval_expr_f64(*input, ctx, cache)?;
                eval_unary_f64(typed_op, op, input)?
            }
            ExprNode::Binary { op, left, right } => {
                let TypedExpr::Binary(typed_op) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                if matches!(typed_op, crate::plan::typed_ir::BinaryOp::And) {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if !truthy_f64(left) {
                        0.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else if matches!(typed_op, crate::plan::typed_ir::BinaryOp::Or) {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if truthy_f64(left) {
                        1.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    let right = self.eval_expr_f64(*right, ctx, cache)?;
                    eval_binary_f64(typed_op, op, left, right)?
                }
            }
            ExprNode::ContextJoin { predicate, .. } => {
                self.eval_expr_f64(*predicate, ctx, cache)?
            }
            ExprNode::Exists { query, predicate } => {
                bool_f64(truthy(&self.eval_exists(query, *predicate, ctx)?)?)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => {
                let TypedExpr::Aggregate(typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                numeric_f64(&self.eval_grouped_aggregate(
                    typed_kind,
                    kind,
                    *relation,
                    group_query.as_deref(),
                    *value,
                    *default,
                    ctx,
                )?)?
            }
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => {
                let TypedExpr::SpatialMetadata(_, typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                numeric_f64(&self.eval_spatial_metadata(relation, typed_kind, kind, *axis, ctx)?)?
            }
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                let TypedExpr::SpatialAggregate(_, typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                self.eval_spatial_aggregate_f64(
                    expr_index, typed_kind, kind, relation, *value, *default, ctx, cache,
                )?
            }
            ExprNode::Attribute { input, .. } => self.eval_expr_f64(*input, ctx, cache)?,
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {
                return Err(EcsError::InvalidPlan(format!(
                    "expression {expr_index} is not numeric"
                )))
            }
        };
        cache[expr_index] = Some(value);
        Ok(value)
    }

    pub(in crate::execution) fn eval_expr(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        if self.profile {
            self.profile_eval_calls += 1;
        }
        let use_local_cache = self.should_use_local_expr_cache(ctx);
        if let Some(value) = self.cached_expr_value(expr_index, ctx, use_local_cache) {
            return Ok(value);
        }
        let result = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Ok(EcsValue::F64(*value)),
            ExprNode::LiteralI64(value) => Ok(EcsValue::I64(*value)),
            ExprNode::LiteralBool(value) => Ok(EcsValue::Bool(*value)),
            ExprNode::LiteralString(value) => Ok(EcsValue::String(value.clone())),
            ExprNode::LiteralValue(value) => Ok(value.clone()),
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = self.bound_entity(ctx, query)?;
                self.world.get_field(entity, component, field)
            }
            ExprNode::ResourceField { resource, field } => {
                self.world.resource_field(resource, field)
            }
            ExprNode::Attribute { input, attribute } => {
                let input = *input;
                let attribute = attribute.clone();
                let value = self.eval_expr(input, ctx)?;
                match value {
                    EcsValue::Struct(fields) => fields.get(&attribute).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "struct value has no attribute '{attribute}'"
                        ))
                    }),
                    other => Err(EcsError::InvalidPlan(format!(
                        "attribute access expects a struct value, got {}",
                        other.kind_name()
                    ))),
                }
            }
            ExprNode::EventStream { event_type } => {
                Ok(EcsValue::List(self.world.read_event_payloads(event_type)?))
            }
            ExprNode::ForEachItem { slot } => ctx
                .loop_items
                .get(*slot)
                .and_then(|value| value.clone())
                .ok_or_else(|| {
                    EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
                }),
            ExprNode::Unary { op, input } => {
                let TypedExpr::Unary(typed_op) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let source_name = op.clone();
                let input = self.eval_expr(*input, ctx)?;
                eval_unary(typed_op, &source_name, input)
            }
            ExprNode::Binary { op, left, right } => {
                let TypedExpr::Binary(typed_op) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let source_name = op.clone();
                let left = *left;
                let right = *right;
                if matches!(typed_op, crate::plan::typed_ir::BinaryOp::And) {
                    let left = self.eval_expr(left, ctx)?;
                    if !truthy(&left)? {
                        return Ok(EcsValue::Bool(false));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                if matches!(typed_op, crate::plan::typed_ir::BinaryOp::Or) {
                    let left = self.eval_expr(left, ctx)?;
                    if truthy(&left)? {
                        return Ok(EcsValue::Bool(true));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                let left = self.eval_expr(left, ctx)?;
                let right = self.eval_expr(right, ctx)?;
                eval_binary(typed_op, &source_name, left, right)
            }
            ExprNode::InputState { name, code } => Ok(self
                .world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name))),
            ExprNode::ContextJoin { predicate, .. } => self.eval_expr(*predicate, ctx),
            ExprNode::Exists { query, predicate } => {
                let query = query.clone();
                self.eval_exists(&query, *predicate, ctx)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => {
                let TypedExpr::Aggregate(typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let kind = kind.clone();
                let group_query = group_query.clone();
                self.eval_grouped_aggregate(
                    typed_kind,
                    &kind,
                    *relation,
                    group_query.as_deref(),
                    *value,
                    *default,
                    ctx,
                )
            }
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => {
                let TypedExpr::SpatialMetadata(_, typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let relation = relation.clone();
                let kind = kind.clone();
                self.eval_spatial_metadata(&relation, typed_kind, &kind, *axis, ctx)
            }
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                let TypedExpr::SpatialAggregate(_, typed_kind) = self.typed_expr(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                let kind = kind.clone();
                let relation = relation.clone();
                self.eval_spatial_aggregate(typed_kind, &kind, &relation, *value, *default, ctx)
            }
        };
        if let Ok(value) = &result {
            self.store_expr_value(expr_index, ctx, use_local_cache, value);
        }
        result
    }

    fn should_use_local_expr_cache(&self, ctx: &EvalContext) -> bool {
        !ctx.has_loop_items()
            && self
                .local_expr_bindings
                .as_ref()
                .is_some_and(|bindings| bindings == &ctx.bindings)
    }

    fn cached_expr_value(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
        use_local_cache: bool,
    ) -> Option<EcsValue> {
        let cached = if use_local_cache {
            self.local_expr_cache
                .as_ref()
                .and_then(|cache| cache.get(expr_index))
                .and_then(|slot| slot.as_ref())
                .cloned()
        } else {
            self.expr_cache_key(expr_index, ctx)
                .and_then(|key| self.expr_cache.get(&key).cloned())
        };
        if self.profile {
            if cached.is_some() {
                self.profile_expr_cache_hits += 1;
            } else {
                self.profile_expr_cache_misses += 1;
            }
        }
        cached
    }

    fn store_expr_value(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
        use_local_cache: bool,
        value: &EcsValue,
    ) {
        if use_local_cache {
            if let Some(cache) = self.local_expr_cache.as_mut() {
                if let Some(slot) = cache.get_mut(expr_index) {
                    *slot = Some(value.clone());
                }
            }
        } else if let Some(key) = self.expr_cache_key(expr_index, ctx) {
            self.expr_cache.insert(key, value.clone());
        }
    }

    fn expr_cache_key(&self, expr_index: usize, ctx: &EvalContext) -> Option<ExprCacheKey> {
        if ctx.has_loop_items() {
            return None;
        }
        let mut bindings = ctx
            .bindings
            .iter()
            .enumerate()
            .filter_map(|(query_slot, entity)| entity.map(|entity| (query_slot, entity.raw())));
        let Some(first) = bindings.next() else {
            return Some(ExprCacheKey::Empty(expr_index));
        };
        let Some(second) = bindings.next() else {
            return Some(ExprCacheKey::One(expr_index, first.0, first.1));
        };
        let mut all = vec![first, second];
        all.extend(bindings);
        Some(ExprCacheKey::Many(expr_index, all))
    }

    fn eval_exists(
        &mut self,
        query: &str,
        predicate: usize,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let mut query_names = BTreeSet::new();
        query_names.insert(query.to_string());
        self.collect_expr_queries(predicate, &mut query_names)?;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            self.report.rows_scanned += 1;
            if truthy(&self.eval_expr(predicate, &joined)?)? {
                return Ok(EcsValue::Bool(true));
            }
        }
        Ok(EcsValue::Bool(false))
    }

    #[allow(clippy::too_many_arguments)]
    fn eval_grouped_aggregate(
        &mut self,
        kind: crate::plan::typed_ir::AggregateKind,
        source_name: &str,
        relation: usize,
        group_query: Option<&str>,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let Some(group_query) = group_query else {
            return Err(EcsError::InvalidPlan(
                "aggregate expressions need a group query".to_string(),
            ));
        };
        let group_slot = self.query_slot(group_query)?;
        let Some(target_entity) = ctx.bindings.get(group_slot).copied().flatten() else {
            return aggregate_empty(kind, source_name, default, self, ctx);
        };
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(relation, &mut query_names)?;
        if let Some(value) = value {
            self.collect_expr_queries(value, &mut query_names)?;
        }
        let mut values = Vec::new();
        let mut count = 0usize;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            if self.bound_entity(&joined, group_query)? != target_entity {
                continue;
            }
            self.report.rows_scanned += 1;
            if !truthy(&self.eval_expr(relation, &joined)?)? {
                continue;
            }
            count += 1;
            if matches!(kind, crate::plan::typed_ir::AggregateKind::Any) {
                return Ok(EcsValue::Bool(true));
            }
            if let Some(value_expr) = value {
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, source_name, count, values, default, self, ctx)
    }

    pub(in crate::execution) fn expr_queries_cached(
        &self,
        expr_index: usize,
        cache: &mut HashMap<usize, BTreeSet<String>>,
    ) -> Result<BTreeSet<String>> {
        if let Some(queries) = cache.get(&expr_index) {
            return Ok(queries.clone());
        }
        let mut out = BTreeSet::new();
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                out.extend(self.expr_queries_cached(*input, cache)?);
            }
            ExprNode::Binary { left, right, .. } => {
                out.extend(self.expr_queries_cached(*left, cache)?);
                out.extend(self.expr_queries_cached(*right, cache)?);
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                out.extend(self.expr_queries_cached(*predicate, cache)?);
            }
            ExprNode::Exists { query, predicate } => {
                out.extend(self.expr_queries_cached(*predicate, cache)?);
                out.remove(query);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        cache.insert(expr_index, out.clone());
        Ok(out)
    }

    pub(in crate::execution) fn collect_expr_queries(
        &self,
        expr_index: usize,
        out: &mut BTreeSet<String>,
    ) -> Result<()> {
        let mut cache = HashMap::new();
        out.extend(self.expr_queries_cached(expr_index, &mut cache)?);
        Ok(())
    }
}
