use std::collections::{BTreeSet, HashSet};

use crate::column::EcsValue;
use crate::error::Result;
use crate::plan::{ActionNode, CanvasCommandNode, ExprNode};
use crate::schema::StorageType;

use super::super::{EvalContext, PlanExecutor};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn row_local_numeric_action_query(
        &self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Option<String> {
        if contexts.len() != 1 || contexts[0].has_bindings() || contexts[0].has_loop_items() {
            return None;
        }
        if !self.action_contains_when(action_index) && self.action_set_field_count(action_index) < 2
        {
            return None;
        }
        let mut query_name = None;
        if self.row_local_numeric_action_supported(action_index, &mut query_name) {
            query_name
        } else {
            None
        }
    }

    pub(in crate::execution) fn row_local_canvas_action_query(
        &self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Option<String> {
        if contexts.len() != 1 || contexts[0].has_bindings() || contexts[0].has_loop_items() {
            return None;
        }
        let mut query_name = None;
        if self.row_local_canvas_action_supported(action_index, &mut query_name) {
            query_name
        } else {
            None
        }
    }

    fn row_local_canvas_action_supported(
        &self,
        action_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => true,
            ActionNode::Sequence(children) => children
                .iter()
                .all(|child| self.row_local_canvas_action_supported(*child, query_name)),
            ActionNode::CanvasCommand(command) => {
                !command.command.is_empty()
                    && command
                        .args
                        .iter()
                        .all(|arg| self.row_local_canvas_expr_supported(*arg, query_name))
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                self.row_local_canvas_expr_supported(*condition, query_name)
                    && self.row_local_canvas_action_supported(*then_action, query_name)
                    && otherwise_action.is_none_or(|action| {
                        self.row_local_canvas_action_supported(action, query_name)
                    })
            }
            ActionNode::Parallel(_)
            | ActionNode::SetField { .. }
            | ActionNode::ForEach { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::Udf { .. } => false,
        }
    }

    fn row_local_canvas_expr_supported(
        &self,
        expr_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        if !self.expr_supports_f64(expr_index, &mut HashSet::new()) {
            return false;
        }
        let mut queries = BTreeSet::new();
        if self.collect_expr_queries(expr_index, &mut queries).is_err() || queries.len() > 1 {
            return false;
        }
        if let Some(query) = queries.iter().next() {
            if !self.note_row_local_query(query_name, query) {
                return false;
            }
        }
        query_name.as_deref().is_none_or(|query| {
            queries.is_empty() || self.expr_uses_only_row_local_direct_fields(expr_index, query)
        })
    }

    fn row_local_numeric_expr_supported(
        &self,
        expr_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        if !self.expr_supports_f64(expr_index, &mut HashSet::new()) {
            return false;
        }
        let mut queries = BTreeSet::new();
        if self.collect_expr_queries(expr_index, &mut queries).is_err() || queries.len() > 1 {
            return false;
        }
        if let Some(query) = queries.iter().next() {
            if !self.note_row_local_query(query_name, query) {
                return false;
            }
        }
        query_name.as_deref().is_none_or(|query| {
            queries.is_empty() || self.expr_uses_only_row_local_direct_fields(expr_index, query)
        })
    }

    pub(in crate::execution::row_local) fn row_local_const_event_payload(
        &self,
        expr_index: usize,
    ) -> Option<EcsValue> {
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Some(EcsValue::F64(*value)),
            ExprNode::LiteralI64(value) => Some(EcsValue::I64(*value)),
            ExprNode::LiteralBool(value) => Some(EcsValue::Bool(*value)),
            ExprNode::LiteralString(value) => Some(EcsValue::String(value.clone())),
            ExprNode::LiteralValue(value) => Some(value.clone()),
            _ => None,
        }
    }

    fn row_local_list_field_source_supported(
        &self,
        expr_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        let ExprNode::Field { query, .. } = &self.plan.expressions[expr_index] else {
            return false;
        };
        self.note_row_local_query(query_name, query)
    }

    pub(in crate::execution::row_local) fn expr_is_always_truthy(&self, expr_index: usize) -> bool {
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralBool(value) => *value,
            ExprNode::LiteralI64(value) => *value != 0,
            ExprNode::LiteralF64(value) => *value != 0.0,
            ExprNode::Binary { op, left, right } if matches!(op.as_str(), "or" | "||") => {
                self.expr_is_always_truthy(*left) || self.expr_is_always_truthy(*right)
            }
            _ => false,
        }
    }

    fn action_contains_when(&self, action_index: usize) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::When { .. } => true,
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => children
                .iter()
                .any(|child| self.action_contains_when(*child)),
            ActionNode::ForEach { action, .. } => self.action_contains_when(*action),
            ActionNode::Noop
            | ActionNode::SetField { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::CanvasCommand(_)
            | ActionNode::Udf { .. } => false,
        }
    }

    fn action_set_field_count(&self, action_index: usize) -> usize {
        match &self.plan.actions[action_index] {
            ActionNode::SetField { .. } => 1,
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => children
                .iter()
                .map(|child| self.action_set_field_count(*child))
                .sum(),
            ActionNode::When {
                then_action,
                otherwise_action,
                ..
            } => {
                self.action_set_field_count(*then_action)
                    + otherwise_action
                        .map(|action| self.action_set_field_count(action))
                        .unwrap_or(0)
            }
            ActionNode::ForEach { action, .. } => self.action_set_field_count(*action),
            ActionNode::Noop
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::CanvasCommand(_)
            | ActionNode::Udf { .. } => 0,
        }
    }

    fn row_local_numeric_action_supported(
        &self,
        action_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => true,
            ActionNode::Sequence(children) => children
                .iter()
                .all(|child| self.row_local_numeric_action_supported(*child, query_name)),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return false;
                };
                if !self.note_row_local_query(query_name, query) {
                    return false;
                }
                if !self
                    .world
                    .storage_type_for_field(component, field)
                    .is_ok_and(|storage_type| {
                        matches!(storage_type, StorageType::Float32 | StorageType::Float64)
                    })
                {
                    return false;
                }
                self.expr_supports_f64(*value, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*value, query)
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                (self.expr_is_always_truthy(*condition)
                    || self.row_local_numeric_expr_supported(*condition, query_name))
                    && self.row_local_numeric_action_supported(*then_action, query_name)
                    && otherwise_action.is_none_or(|action| {
                        self.row_local_numeric_action_supported(action, query_name)
                    })
            }
            ActionNode::ForEach { source, action, .. } => {
                self.row_local_list_field_source_supported(*source, query_name)
                    && self.row_local_numeric_action_supported(*action, query_name)
            }
            ActionNode::EmitEvent { value, .. } => {
                self.row_local_const_event_payload(*value).is_some()
            }
            ActionNode::Parallel(_)
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::CanvasCommand(_)
            | ActionNode::Udf { .. } => false,
        }
    }

    fn note_row_local_query(&self, query_name: &mut Option<String>, candidate: &str) -> bool {
        match query_name {
            Some(existing) => existing == candidate,
            None => {
                *query_name = Some(candidate.to_string());
                true
            }
        }
    }

    fn expr_uses_only_row_local_direct_fields(&self, expr_index: usize, query_name: &str) -> bool {
        self.expr_uses_only_row_local_direct_fields_inner(
            expr_index,
            query_name,
            &mut HashSet::new(),
        )
    }

    fn expr_uses_only_row_local_direct_fields_inner(
        &self,
        expr_index: usize,
        query_name: &str,
        seen: &mut HashSet<usize>,
    ) -> bool {
        if !seen.insert(expr_index) {
            return true;
        }
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::ForEachItem { .. } => true,
            ExprNode::Field { query, .. } => query == query_name,
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                relation.origin_query == query_name
                    && self.spatial_aggregate_precomputable_for_row_local(
                        kind, relation, *value, *default, query_name, seen,
                    )
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*input, query_name, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*left, query_name, seen)
                    && self.expr_uses_only_row_local_direct_fields_inner(*right, query_name, seen)
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ContextJoin { .. }
            | ExprNode::Exists { .. }
            | ExprNode::Aggregate { .. }
            | ExprNode::SpatialMetadata { .. } => false,
        }
    }

    fn spatial_aggregate_precomputable_for_row_local(
        &self,
        kind: &str,
        relation: &crate::plan::SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        query_name: &str,
        seen: &mut HashSet<usize>,
    ) -> bool {
        if relation.origin_bounds.is_some() || relation.target_bounds.is_some() {
            return matches!(kind, "any" | "count")
                && value.is_none()
                && default.is_none()
                && relation.exact_filter.is_none()
                && self
                    .spatial_origin_expressions_use_row_local_fields(relation, query_name, seen);
        }
        self.spatial_origin_expressions_use_row_local_fields(relation, query_name, seen)
    }

    fn spatial_origin_expressions_use_row_local_fields(
        &self,
        relation: &crate::plan::SpatialRelationNode,
        query_name: &str,
        seen: &mut HashSet<usize>,
    ) -> bool {
        relation
            .origin_position
            .iter()
            .all(|expr| self.expr_uses_only_row_local_direct_fields_inner(*expr, query_name, seen))
            && relation.origin_bounds.as_ref().is_none_or(|bounds| {
                bounds
                    .minimum
                    .iter()
                    .chain(bounds.maximum.iter())
                    .all(|expr| {
                        self.expr_uses_only_row_local_direct_fields_inner(*expr, query_name, seen)
                    })
            })
            && relation.radius.is_none_or(|expr| {
                self.expr_uses_only_row_local_direct_fields_inner(expr, query_name, seen)
            })
    }

    pub(in crate::execution::row_local) fn canvas_command_uses_query(
        &self,
        command: &CanvasCommandNode,
        query_name: &str,
    ) -> Result<bool> {
        for arg in &command.args {
            if self.expr_uses_query(*arg, query_name)? {
                return Ok(true);
            }
        }
        Ok(false)
    }

    pub(in crate::execution::row_local) fn action_uses_query(
        &self,
        action_index: usize,
        query_name: &str,
    ) -> Result<bool> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(false),
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => {
                for child in children {
                    if self.action_uses_query(*child, query_name)? {
                        return Ok(true);
                    }
                }
                Ok(false)
            }
            ActionNode::SetField { target, value } => Ok(self
                .expr_uses_query(*target, query_name)?
                || self.expr_uses_query(*value, query_name)?),
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => Ok(self.expr_uses_query(*condition, query_name)?
                || self.action_uses_query(*then_action, query_name)?
                || otherwise_action
                    .map(|action| self.action_uses_query(action, query_name))
                    .transpose()?
                    .unwrap_or(false)),
            ActionNode::ForEach { source, action, .. } => Ok(self
                .expr_uses_query(*source, query_name)?
                || self.action_uses_query(*action, query_name)?),
            ActionNode::EmitEvent { value, .. } => self.expr_uses_query(*value, query_name),
            ActionNode::AddComponent { query, value, .. } => Ok(query == query_name
                || value
                    .map(|expr| self.expr_uses_query(expr, query_name))
                    .transpose()?
                    .unwrap_or(false)),
            ActionNode::RemoveComponent { query, .. }
            | ActionNode::AddTag { query, .. }
            | ActionNode::RemoveTag { query, .. }
            | ActionNode::Despawn { query } => Ok(query == query_name),
            ActionNode::CanvasCommand(command) => {
                self.canvas_command_uses_query(command, query_name)
            }
            ActionNode::Udf { args, .. } => {
                for arg in args {
                    if self.expr_uses_query(*arg, query_name)? {
                        return Ok(true);
                    }
                }
                Ok(false)
            }
        }
    }

    pub(in crate::execution::row_local) fn expr_uses_query(
        &self,
        expr_index: usize,
        query_name: &str,
    ) -> Result<bool> {
        let mut queries = BTreeSet::new();
        self.collect_expr_queries(expr_index, &mut queries)?;
        Ok(queries.contains(query_name))
    }
}
