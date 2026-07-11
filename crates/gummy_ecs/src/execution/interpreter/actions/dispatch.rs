use std::collections::HashSet;

use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, ExprNode};

use super::super::super::{EvalContext, PlanExecutor};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn execute_action(
        &mut self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        if let ActionNode::Sequence(children) = &self.plan.actions[action_index] {
            if self.sequence_set_fields_can_execute_fused(children) {
                return self.execute_parallel_set_fields(children, contexts);
            }
        }
        if !self.report_writes {
            if let Some(query_name) = self.row_local_numeric_action_query(action_index, contexts) {
                return self.execute_row_local_numeric_action(action_index, &query_name);
            }
        }
        if let Some(query_name) = self.row_local_canvas_action_query(action_index, contexts) {
            return self.execute_row_local_canvas_action(action_index, &query_name);
        }

        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(()),
            ActionNode::Sequence(children) => {
                for child in children {
                    self.expr_cache.clear();
                    self.numeric_field_cache.clear();
                    self.numeric_field_cache_rows.clear();
                    self.persist_spatial_index_cache();
                    self.spatial_relation_cache.clear();
                    self.execute_action(*child, contexts)?;
                }
                Ok(())
            }
            ActionNode::Parallel(children) => self.execute_parallel(children, contexts),
            ActionNode::SetField { target, value } => self.execute_set(*target, *value, contexts),
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => self.execute_when(*condition, *then_action, *otherwise_action, contexts),
            ActionNode::ForEach {
                source,
                item_slot,
                action,
            } => self.execute_for_each(*source, *item_slot, *action, contexts),
            ActionNode::EmitEvent { event_type, value } => {
                self.execute_emit_event(event_type, *value, contexts)
            }
            ActionNode::AddComponent {
                query,
                component,
                value,
            } => self.execute_add_component(query, component, *value, contexts),
            ActionNode::RemoveComponent { query, component } => {
                self.execute_remove_component(query, component, contexts)
            }
            ActionNode::AddTag { query, tag } => self.execute_add_tag(query, tag, contexts),
            ActionNode::RemoveTag { query, tag } => self.execute_remove_tag(query, tag, contexts),
            ActionNode::Despawn { query } => self.execute_despawn(query, contexts),
            ActionNode::CanvasCommand(command) => self.execute_canvas_command(command, contexts),
            ActionNode::Udf { descriptor, .. } => Err(EcsError::InvalidPlan(format!(
                "physical execution cannot call Python UDF '{descriptor}'"
            ))),
        }
    }

    fn sequence_set_fields_can_execute_fused(&self, children: &[usize]) -> bool {
        if children.is_empty()
            || !children
                .iter()
                .all(|child| matches!(self.plan.actions[*child], ActionNode::SetField { .. }))
        {
            return false;
        }
        let mut previous_writes: HashSet<(String, String, String)> = HashSet::new();
        for child in children {
            let ActionNode::SetField { target, value } = self.plan.actions[*child] else {
                return false;
            };
            let ExprNode::Field {
                query,
                component,
                field,
            } = &self.plan.expressions[target]
            else {
                return false;
            };
            let target_key = (query.clone(), component.clone(), field.clone());
            if previous_writes.contains(&target_key) {
                return false;
            }
            let mut reads = HashSet::new();
            if !self.collect_expr_field_reads(value, &mut reads) {
                return false;
            }
            if reads.iter().any(|read| previous_writes.contains(read)) {
                return false;
            }
            previous_writes.insert(target_key);
        }
        true
    }

    fn collect_expr_field_reads(
        &self,
        expr_index: usize,
        reads: &mut HashSet<(String, String, String)>,
    ) -> bool {
        match &self.plan.expressions[expr_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                reads.insert((query.clone(), component.clone(), field.clone()));
                true
            }
            ExprNode::Attribute { input, .. } | ExprNode::Unary { input, .. } => {
                self.collect_expr_field_reads(*input, reads)
            }
            ExprNode::Binary { left, right, .. } => {
                self.collect_expr_field_reads(*left, reads)
                    && self.collect_expr_field_reads(*right, reads)
            }
            ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
                self.collect_expr_field_reads(*predicate, reads)
            }
            ExprNode::Aggregate { value, default, .. } => {
                value.is_none_or(|value| self.collect_expr_field_reads(value, reads))
                    && default.is_none_or(|default| self.collect_expr_field_reads(default, reads))
            }
            ExprNode::SpatialAggregate {
                relation,
                value,
                default,
                ..
            } => {
                self.collect_spatial_relation_field_reads(relation, reads)
                    && value.is_none_or(|value| self.collect_expr_field_reads(value, reads))
                    && default.is_none_or(|default| self.collect_expr_field_reads(default, reads))
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                self.collect_spatial_relation_field_reads(relation, reads)
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::InputState { .. }
            | ExprNode::ForEachItem { .. } => true,
        }
    }

    fn collect_spatial_relation_field_reads(
        &self,
        relation: &crate::plan::SpatialRelationNode,
        reads: &mut HashSet<(String, String, String)>,
    ) -> bool {
        relation
            .origin_position
            .iter()
            .chain(relation.target_position.iter())
            .all(|expr| self.collect_expr_field_reads(*expr, reads))
            && relation.origin_bounds.as_ref().is_none_or(|bounds| {
                bounds
                    .minimum
                    .iter()
                    .chain(bounds.maximum.iter())
                    .all(|expr| self.collect_expr_field_reads(*expr, reads))
            })
            && relation.target_bounds.as_ref().is_none_or(|bounds| {
                bounds
                    .minimum
                    .iter()
                    .chain(bounds.maximum.iter())
                    .all(|expr| self.collect_expr_field_reads(*expr, reads))
            })
            && relation
                .radius
                .is_none_or(|expr| self.collect_expr_field_reads(expr, reads))
            && relation
                .exact_filter
                .is_none_or(|expr| self.collect_expr_field_reads(expr, reads))
    }
}
