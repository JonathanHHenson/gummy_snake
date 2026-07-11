use crate::column::EcsValue;
use crate::error::Result;
use crate::plan::{ActionNode, ExprNode};

use super::super::super::{numeric_f64, EvalContext, ExecutionEvent, PlanExecutor};

impl<'a> PlanExecutor<'a> {
    pub(super) fn execute_emit_event(
        &mut self,
        event_type: &str,
        value: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in contexts {
            let payload = self.eval_expr(value, ctx)?;
            self.world.emit_event(event_type, payload.clone())?;
            self.report.events_emitted += 1;
            if self.report_writes {
                self.report.events.push(ExecutionEvent {
                    event_type: event_type.to_owned(),
                    payload,
                });
            }
        }
        Ok(())
    }
    pub(super) fn try_execute_event_resource_accumulator(
        &mut self,
        source: usize,
        item_slot: usize,
        action: usize,
        contexts: &[EvalContext],
    ) -> Result<bool> {
        if contexts.len() != 1
            || !contexts[0].bindings.is_empty()
            || !contexts[0].loop_items.is_empty()
        {
            return Ok(false);
        }
        let ExprNode::EventStream { event_type } = &self.plan.expressions[source] else {
            return Ok(false);
        };
        let Some((resource, field, event_field)) =
            self.event_resource_accumulator_pattern(item_slot, action)
        else {
            return Ok(false);
        };
        let (event_count, sum) = self
            .world
            .sum_event_numeric_payload_field(event_type, &event_field)?;
        if event_count == 0 {
            return Ok(true);
        }
        let current = self.world.resource_field(&resource, &field)?;
        self.world.set_resource_field(
            &resource,
            &field,
            EcsValue::F64(numeric_f64(&current)? + sum),
        )?;
        self.report.rows_scanned += event_count;
        self.report.resource_fields_written += event_count;
        Ok(true)
    }

    fn event_resource_accumulator_pattern(
        &self,
        item_slot: usize,
        action: usize,
    ) -> Option<(String, String, String)> {
        let action = match &self.plan.actions[action] {
            ActionNode::Sequence(children) if children.len() == 1 => children[0],
            ActionNode::SetField { .. } => action,
            _ => return None,
        };
        let ActionNode::SetField { target, value } = self.plan.actions[action] else {
            return None;
        };
        let ExprNode::ResourceField { resource, field } = &self.plan.expressions[target] else {
            return None;
        };
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[value] else {
            return None;
        };
        if !matches!(op.as_str(), "add" | "+") {
            return None;
        }
        let left_matches = self.resource_field_expr_matches(*left, resource, field);
        let right_matches = self.resource_field_expr_matches(*right, resource, field);
        if left_matches {
            return self
                .event_item_attribute(*right, item_slot)
                .map(|event_field| (resource.clone(), field.clone(), event_field.to_string()));
        }
        if right_matches {
            return self
                .event_item_attribute(*left, item_slot)
                .map(|event_field| (resource.clone(), field.clone(), event_field.to_string()));
        }
        None
    }

    fn resource_field_expr_matches(&self, expr: usize, resource: &str, field: &str) -> bool {
        matches!(
            &self.plan.expressions[expr],
            ExprNode::ResourceField {
                resource: expr_resource,
                field: expr_field,
            } if expr_resource == resource && expr_field == field
        )
    }

    fn event_item_attribute(&self, expr: usize, item_slot: usize) -> Option<&str> {
        let ExprNode::Attribute { input, attribute } = &self.plan.expressions[expr] else {
            return None;
        };
        match &self.plan.expressions[*input] {
            ExprNode::ForEachItem { slot } if *slot == item_slot => Some(attribute.as_str()),
            _ => None,
        }
    }
}
