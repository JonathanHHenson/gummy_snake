use std::collections::{BTreeSet, HashMap};

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::ExprNode;

use super::aggregate_eval::{aggregate_empty, aggregate_finish};
use super::f64_program::{eval_binary_f64, eval_unary_f64};
use super::value_ops::{
    bool_f64, default_input_state_value, eval_binary, eval_unary, numeric_f64, truthy, truthy_f64,
};
use super::{EvalContext, ExprCacheKey, PlanExecutor};

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
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.entity_field_f64(*entity, component, field)?
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
                let input = self.eval_expr_f64(*input, ctx, cache)?;
                eval_unary_f64(op, input)?
            }
            ExprNode::Binary { op, left, right } => {
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if !truthy_f64(left) {
                        0.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if truthy_f64(left) {
                        1.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    let right = self.eval_expr_f64(*right, ctx, cache)?;
                    eval_binary_f64(op, left, right)?
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
            } => numeric_f64(&self.eval_grouped_aggregate(
                kind,
                *relation,
                group_query.as_deref(),
                *value,
                *default,
                ctx,
            )?)?,
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => numeric_f64(&self.eval_spatial_metadata(relation, kind, *axis, ctx)?)?,
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => self.eval_spatial_aggregate_f64(
                expr_index, kind, relation, *value, *default, ctx, cache,
            )?,
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
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.world.get_field(*entity, component, field)
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
            ExprNode::EventStream { event_type } => Ok(EcsValue::List(
                self.world
                    .read_events(event_type)?
                    .into_iter()
                    .map(|event| event.payload)
                    .collect(),
            )),
            ExprNode::ForEachItem { slot } => ctx.loop_items.get(slot).cloned().ok_or_else(|| {
                EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
            }),
            ExprNode::Unary { op, input } => {
                let op = op.clone();
                let input = *input;
                let input = self.eval_expr(input, ctx)?;
                eval_unary(&op, input)
            }
            ExprNode::Binary { op, left, right } => {
                let op = op.clone();
                let left = *left;
                let right = *right;
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr(left, ctx)?;
                    if !truthy(&left)? {
                        return Ok(EcsValue::Bool(false));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr(left, ctx)?;
                    if truthy(&left)? {
                        return Ok(EcsValue::Bool(true));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                let left = self.eval_expr(left, ctx)?;
                let right = self.eval_expr(right, ctx)?;
                eval_binary(&op, left, right)
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
                let kind = kind.clone();
                let group_query = group_query.clone();
                self.eval_grouped_aggregate(
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
                let relation = relation.clone();
                let kind = kind.clone();
                self.eval_spatial_metadata(&relation, &kind, *axis, ctx)
            }
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                let kind = kind.clone();
                let relation = relation.clone();
                self.eval_spatial_aggregate(&kind, &relation, *value, *default, ctx)
            }
        };
        if let Ok(value) = &result {
            self.store_expr_value(expr_index, ctx, use_local_cache, value);
        }
        result
    }

    fn should_use_local_expr_cache(&self, ctx: &EvalContext) -> bool {
        ctx.loop_items.is_empty()
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
        if !ctx.loop_items.is_empty() {
            return None;
        }
        match ctx.bindings.len() {
            0 => Some(ExprCacheKey::Empty(expr_index)),
            1 => ctx.bindings.iter().next().map(|(query, entity)| {
                ExprCacheKey::One(
                    expr_index,
                    *self.query_indices.get(query).unwrap_or(&usize::MAX),
                    entity.raw(),
                )
            }),
            _ => {
                let mut bindings = ctx
                    .bindings
                    .iter()
                    .map(|(query, entity)| {
                        (
                            *self.query_indices.get(query).unwrap_or(&usize::MAX),
                            entity.raw(),
                        )
                    })
                    .collect::<Vec<_>>();
                bindings.sort_by_key(|(query_index, _)| *query_index);
                Some(ExprCacheKey::Many(expr_index, bindings))
            }
        }
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

    fn eval_grouped_aggregate(
        &mut self,
        kind: &str,
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
        let Some(target_entity) = ctx.bindings.get(group_query).copied() else {
            return aggregate_empty(kind, default, self, ctx);
        };
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(relation, &mut query_names)?;
        if let Some(value) = value {
            self.collect_expr_queries(value, &mut query_names)?;
        }
        let mut values = Vec::new();
        let mut count = 0usize;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            if joined.bindings.get(group_query).copied() != Some(target_entity) {
                continue;
            }
            self.report.rows_scanned += 1;
            if !truthy(&self.eval_expr(relation, &joined)?)? {
                continue;
            }
            count += 1;
            if kind == "any" {
                return Ok(EcsValue::Bool(true));
            }
            if let Some(value_expr) = value {
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
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
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Attribute { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Binary { left, right, .. } => {
                self.collect_expr_queries(*left, out)?;
                self.collect_expr_queries(*right, out)?;
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                self.collect_expr_queries(*predicate, out)?;
            }
            ExprNode::Exists { query, predicate } => {
                let mut inner = BTreeSet::new();
                self.collect_expr_queries(*predicate, &mut inner)?;
                inner.remove(query);
                out.extend(inner);
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
        Ok(())
    }
}
