use std::collections::{BTreeSet, HashSet};

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, ExprNode};

use super::{truthy, EvalContext, ExecutionEvent, ExecutionWrite, PlanExecutor, WriteKey};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn execute_action(
        &mut self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        if !self.report_writes {
            if let Some(query_name) = self.row_local_numeric_action_query(action_index, contexts) {
                return self.execute_row_local_numeric_action(action_index, &query_name);
            }
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
                for ctx in contexts {
                    let payload = self.eval_expr(*value, ctx)?;
                    self.world.emit_event(event_type, payload.clone())?;
                    self.report.events_emitted += 1;
                    self.report.events.push(ExecutionEvent {
                        event_type: event_type.clone(),
                        payload,
                    });
                }
                Ok(())
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
            ActionNode::Udf { descriptor, .. } => Err(EcsError::InvalidPlan(format!(
                "physical execution cannot call Python UDF '{descriptor}'"
            ))),
        }
    }

    fn structural_contexts(
        &self,
        query: &str,
        contexts: &[EvalContext],
    ) -> Result<Vec<EvalContext>> {
        let mut queries = BTreeSet::new();
        queries.insert(query.to_string());
        let mut out = Vec::new();
        for ctx in contexts {
            out.extend(self.expand_context_for_queries(ctx, &queries)?);
        }
        Ok(out)
    }

    fn execute_add_component(
        &mut self,
        query: &str,
        component: &str,
        value: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for add_component"))
            })?;
            let value = value.map(|expr| self.eval_expr(expr, &ctx)).transpose()?;
            self.world
                .add_component_default(entity, component.to_string())?;
            if let Some(EcsValue::Struct(fields)) = value {
                for (field, field_value) in fields {
                    self.world
                        .set_field(entity, component, &field, field_value)?;
                }
            }
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_remove_component(
        &mut self,
        query: &str,
        component: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for remove_component"))
            })?;
            self.world.remove_component(entity, component)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_add_tag(&mut self, query: &str, tag: &str, contexts: &[EvalContext]) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for add_tag"))
            })?;
            self.world.add_tag(entity, tag)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_remove_tag(
        &mut self,
        query: &str,
        tag: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for remove_tag"))
            })?;
            self.world.remove_tag(entity, tag)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_despawn(&mut self, query: &str, contexts: &[EvalContext]) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for despawn"))
            })?;
            self.world.despawn(entity)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    fn execute_for_each(
        &mut self,
        source: usize,
        item_slot: usize,
        action: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in contexts {
            let value = self.eval_expr(source, ctx)?;
            let items = match value {
                EcsValue::List(values) => values,
                other => {
                    return Err(EcsError::InvalidPlan(format!(
                        "for_each source must evaluate to a list, got {}",
                        other.kind_name()
                    )))
                }
            };
            for item in items {
                let mut loop_ctx = ctx.clone();
                loop_ctx.loop_items.insert(item_slot, item);
                self.execute_action(action, &[loop_ctx])?;
            }
        }
        Ok(())
    }

    fn execute_set(
        &mut self,
        target_index: usize,
        value_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(value_index, &mut query_names)?;
        self.add_set_target_query(target_index, &mut query_names)?;

        let mut targets_seen = HashSet::new();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let value = self.eval_expr(value_index, &ctx)?;
                self.write_target(target_index, value, &ctx, &mut targets_seen)?;
            }
        }
        Ok(())
    }

    pub(in crate::execution) fn add_set_target_query(
        &self,
        target_index: usize,
        query_names: &mut BTreeSet<String>,
    ) -> Result<()> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field { query, .. } => {
                query_names.insert(query.clone());
                Ok(())
            }
            ExprNode::ResourceField { .. } => Ok(()),
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }

    fn execute_when(
        &mut self,
        condition_index: usize,
        then_action: usize,
        otherwise_action: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut condition_queries = BTreeSet::new();
        self.collect_expr_queries(condition_index, &mut condition_queries)?;
        let mut matched = Vec::new();
        let mut remaining = Vec::new();
        for base_ctx in contexts {
            let expanded = self.expand_context_for_queries(base_ctx, &condition_queries)?;
            self.report.rows_scanned += expanded.len();
            let mut branch_matches = Vec::new();
            for ctx in expanded {
                if truthy(&self.eval_expr(condition_index, &ctx)?)? {
                    branch_matches.push(ctx);
                }
            }
            if branch_matches.is_empty() {
                remaining.push(base_ctx.clone());
            } else {
                matched.extend(branch_matches);
            }
        }
        if !matched.is_empty() {
            self.execute_action(then_action, &matched)?;
        }
        if let Some(otherwise_action) = otherwise_action {
            if !remaining.is_empty() {
                self.execute_action(otherwise_action, &remaining)?;
            }
        }
        Ok(())
    }

    fn write_target(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = *ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self
                    .world
                    .coerce_value_for_component_field(component, field, value)?;
                let key = WriteKey::Component {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_field(entity, component, field, value.clone())?;
                self.report.fields_written += 1;
                if self.report_writes {
                    self.report.writes.push(ExecutionWrite::ComponentField {
                        entity,
                        component: component.clone(),
                        field: field.clone(),
                        value,
                    });
                }
                Ok(())
            }
            ExprNode::ResourceField { resource, field } => {
                let value = self
                    .world
                    .coerce_value_for_component_field(resource, field, value)?;
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_resource_field(resource, field, value.clone())?;
                self.report.resource_fields_written += 1;
                if self.report_writes {
                    self.report.writes.push(ExecutionWrite::ResourceField {
                        resource: resource.clone(),
                        field: field.clone(),
                        value,
                    });
                }
                Ok(())
            }
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }
}
