use std::collections::BTreeSet;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};

use super::super::super::{EvalContext, ExecutionCanvasCommand, PlanExecutor};

impl<'a> PlanExecutor<'a> {
    pub(super) fn execute_canvas_command(
        &mut self,
        command: &crate::plan::CanvasCommandNode,
        contexts: &[EvalContext],
    ) -> Result<()> {
        if command.command.is_empty() {
            return Err(EcsError::InvalidPlan(
                "canvas command name cannot be empty".to_string(),
            ));
        }
        let mut query_names = BTreeSet::new();
        for arg in &command.args {
            self.collect_expr_queries(*arg, &mut query_names)?;
        }
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let args = command
                    .args
                    .iter()
                    .map(|arg| self.eval_expr(*arg, &ctx))
                    .collect::<Result<Vec<_>>>()?;
                self.report.canvas_commands.push(ExecutionCanvasCommand {
                    command: command.command.clone(),
                    args,
                });
            }
        }
        Ok(())
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

    fn execute_structural_contexts(
        &mut self,
        query: &str,
        contexts: &[EvalContext],
        operation: &str,
        mut apply: impl FnMut(&mut Self, Entity, &EvalContext) -> Result<()>,
    ) -> Result<()> {
        for ctx in self.structural_contexts(query, contexts)? {
            let entity = *ctx.bindings.get(query).ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not bound for {operation}"))
            })?;
            apply(self, entity, &ctx)?;
            self.report.structural_commands += 1;
        }
        Ok(())
    }

    pub(super) fn execute_add_component(
        &mut self,
        query: &str,
        component: &str,
        value: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        self.execute_structural_contexts(
            query,
            contexts,
            "add_component",
            |executor, entity, ctx| {
                let value = value
                    .map(|expr| executor.eval_expr(expr, ctx))
                    .transpose()?;
                executor
                    .world
                    .add_component_default(entity, component.to_string())?;
                if let Some(EcsValue::Struct(fields)) = value {
                    for (field, field_value) in fields {
                        executor
                            .world
                            .set_field(entity, component, &field, field_value)?;
                    }
                }
                Ok(())
            },
        )
    }

    pub(super) fn execute_remove_component(
        &mut self,
        query: &str,
        component: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        self.execute_structural_contexts(
            query,
            contexts,
            "remove_component",
            |executor, entity, _| executor.world.remove_component(entity, component),
        )
    }

    pub(super) fn execute_add_tag(
        &mut self,
        query: &str,
        tag: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        self.execute_structural_contexts(query, contexts, "add_tag", |executor, entity, _| {
            executor.world.add_tag(entity, tag)
        })
    }

    pub(super) fn execute_remove_tag(
        &mut self,
        query: &str,
        tag: &str,
        contexts: &[EvalContext],
    ) -> Result<()> {
        self.execute_structural_contexts(query, contexts, "remove_tag", |executor, entity, _| {
            executor.world.remove_tag(entity, tag)
        })
    }

    pub(super) fn execute_despawn(&mut self, query: &str, contexts: &[EvalContext]) -> Result<()> {
        self.execute_structural_contexts(query, contexts, "despawn", |executor, entity, _| {
            executor.world.despawn(entity)
        })
    }
}
