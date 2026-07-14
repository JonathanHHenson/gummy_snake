use std::collections::{BTreeSet, HashSet};

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::ExprNode;

use super::super::super::{EvalContext, ExecutionWrite, PlanExecutor, WriteKey};

impl<'a> PlanExecutor<'a> {
    pub(super) fn execute_set(
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
            let mut all_bound = true;
            for query in &query_names {
                all_bound &= self.query_is_bound(base_ctx, query)?;
            }
            if all_bound {
                self.report.rows_scanned += 1;
                let value = self.eval_expr(value_index, base_ctx)?;
                self.write_target(target_index, value, base_ctx, &mut targets_seen)?;
                continue;
            }
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
                let entity = self.bound_entity(ctx, query).map_err(|_| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self.coerce_plan_field_value(component, field, value)?;
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
                let value = self.coerce_plan_field_value(resource, field, value)?;
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
