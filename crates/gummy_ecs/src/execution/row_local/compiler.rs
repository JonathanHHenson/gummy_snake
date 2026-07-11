use std::collections::HashMap;

use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, ExprNode};

use super::super::f64_program::{CompiledF64ReadOnlyProgram, RowLocalAction, RowLocalTarget};
use super::super::PlanExecutor;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution::row_local) fn compile_row_local_action(
        &self,
        action_index: usize,
        query_name: &str,
        program: &CompiledF64ReadOnlyProgram<'_>,
        targets: &mut Vec<RowLocalTarget>,
        target_slots: &mut HashMap<(String, String), usize>,
    ) -> Result<RowLocalAction> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(RowLocalAction::Noop),
            ActionNode::Sequence(children) => children
                .iter()
                .map(|child| {
                    self.compile_row_local_action(
                        *child,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    )
                })
                .collect::<Result<Vec<_>>>()
                .map(RowLocalAction::Sequence),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return Err(EcsError::InvalidPlan(
                        "row-local numeric action target must be a field".to_string(),
                    ));
                };
                if query != query_name {
                    return Err(EcsError::InvalidPlan(format!(
                        "row-local numeric action cannot write query '{query}' from primary query '{query_name}'"
                    )));
                }
                let key = (component.clone(), field.clone());
                let field_slot = *program.field_slot_by_key.get(&key).ok_or_else(|| {
                    EcsError::InvalidPlan(format!(
                        "row-local numeric field cache missing target '{component}.{field}'"
                    ))
                })?;
                let target_slot = if let Some(slot) = target_slots.get(&key) {
                    *slot
                } else {
                    let slot = targets.len();
                    target_slots.insert(key, slot);
                    targets.push(RowLocalTarget {
                        component: component.clone(),
                        field: field.clone(),
                    });
                    slot
                };
                Ok(RowLocalAction::SetField {
                    field_slot,
                    target_slot,
                    value_expr: *value,
                })
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                if self.expr_is_always_truthy(*condition) {
                    return self.compile_row_local_action(
                        *then_action,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    );
                }
                Ok(RowLocalAction::When {
                    condition_expr: *condition,
                    then_action: Box::new(self.compile_row_local_action(
                        *then_action,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    )?),
                    otherwise_action: otherwise_action
                        .map(|action| {
                            self.compile_row_local_action(
                                action,
                                query_name,
                                program,
                                targets,
                                target_slots,
                            )
                            .map(Box::new)
                        })
                        .transpose()?,
                })
            }
            ActionNode::ForEach {
                source,
                item_slot,
                action,
            } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*source]
                else {
                    return Err(EcsError::InvalidPlan(
                        "row-local for_each source must be a field".to_string(),
                    ));
                };
                if query != query_name {
                    return Err(EcsError::InvalidPlan(format!(
                        "row-local for_each cannot read query '{query}' from primary query '{query_name}'"
                    )));
                }
                Ok(RowLocalAction::ForEachListField {
                    component: component.clone(),
                    field: field.clone(),
                    item_slot: *item_slot,
                    action: Box::new(self.compile_row_local_action(
                        *action,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    )?),
                })
            }
            ActionNode::EmitEvent { event_type, value } => {
                let payload = self.row_local_const_event_payload(*value).ok_or_else(|| {
                    EcsError::InvalidPlan(
                        "row-local numeric executor only supports constant event payloads"
                            .to_string(),
                    )
                })?;
                Ok(RowLocalAction::EmitConstEvent {
                    event_type: event_type.clone(),
                    payload,
                })
            }
            other => Err(EcsError::InvalidPlan(format!(
                "row-local numeric executor does not support action {other:?}"
            ))),
        }
    }
}
