use std::collections::BTreeSet;

use crate::column::EcsValue;
use crate::error::{EcsError, Result};

use super::super::super::{truthy, EvalContext, PlanExecutor};

impl<'a> PlanExecutor<'a> {
    pub(super) fn execute_for_each(
        &mut self,
        source: usize,
        item_slot: usize,
        action: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        if self.try_execute_event_resource_accumulator(source, item_slot, action, contexts)? {
            return Ok(());
        }
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
            let mut loop_ctx = ctx.clone();
            if loop_ctx.loop_items.len() <= item_slot {
                loop_ctx.loop_items.resize(item_slot + 1, None);
            }
            for item in items {
                loop_ctx.loop_items[item_slot] = Some(item);
                self.execute_action(action, std::slice::from_ref(&loop_ctx))?;
            }
        }
        Ok(())
    }
    pub(super) fn execute_when(
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
            let mut all_bound = true;
            for query in &condition_queries {
                all_bound &= self.query_is_bound(base_ctx, query)?;
            }
            if all_bound {
                self.report.rows_scanned += 1;
                if truthy(&self.eval_expr(condition_index, base_ctx)?)? {
                    self.execute_action(then_action, std::slice::from_ref(base_ctx))?;
                } else if let Some(otherwise_action) = otherwise_action {
                    self.execute_action(otherwise_action, std::slice::from_ref(base_ctx))?;
                }
                continue;
            }
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
}
