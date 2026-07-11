use std::time::Instant;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, CanvasCommandNode};

use super::super::f64_program::{
    compile_f64_readonly_program, eval_compiled_f64_readonly, CompiledF64ReadOnlyProgram,
};
use super::super::{
    truthy_f64, ExecutionCanvasCommand, ExecutionCanvasFillBatch, PlanExecutor,
    SpatialPrecomputeLayout,
};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn execute_row_local_canvas_action(
        &mut self,
        action_index: usize,
        query_name: &str,
    ) -> Result<()> {
        let rows = self.query_rows.get(query_name).cloned().ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        if rows.is_empty() {
            return Ok(());
        }

        let precompute_start = self.profile.then(Instant::now);
        self.precompute_direct_spatial_aggregates_for_query(
            query_name,
            SpatialPrecomputeLayout::QueryRows,
        )?;
        if let Some(start) = precompute_start {
            eprintln!(
                "ecs_profile row_local_canvas_precompute elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let preload_start = self.profile.then(Instant::now);
        self.preload_numeric_fields_for_query(query_name, SpatialPrecomputeLayout::QueryRows)?;
        if let Some(start) = preload_start {
            eprintln!(
                "ecs_profile row_local_canvas_preload elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let eval_start = self.profile.then(Instant::now);
        let (commands, fill_batch, rows_scanned) = {
            let program = compile_f64_readonly_program(
                self.plan,
                self.world,
                query_name,
                &self.numeric_field_cache,
                &self.numeric_field_cache_rows,
                &self.spatial_precomputed_f64,
                &self.spatial_precomputed_f64_rows,
            );
            if let Some((commands, records, rows_scanned)) = self
                .collect_compiled_row_local_fill_batch(action_index, query_name, &rows, &program)?
            {
                (
                    commands,
                    Some(ExecutionCanvasFillBatch { records }),
                    rows_scanned,
                )
            } else {
                let mut commands = Vec::new();
                let mut rows_scanned = 0;
                self.collect_compiled_row_local_canvas_root(
                    action_index,
                    query_name,
                    &rows,
                    &program,
                    &mut commands,
                    &mut rows_scanned,
                )?;
                (commands, None, rows_scanned)
            }
        };
        self.report.rows_scanned += rows_scanned;
        self.report.canvas_commands.extend(commands);
        if let Some(fill_batch) = fill_batch {
            self.report.canvas_fill_batches.push(fill_batch);
        }
        if let Some(start) = eval_start {
            eprintln!(
                "ecs_profile row_local_canvas_eval elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }
    pub(in crate::execution::row_local) fn eval_canvas_command_f64_args(
        &self,
        command: &CanvasCommandNode,
        row_index: usize,
        entity: Entity,
        program: &CompiledF64ReadOnlyProgram<'_>,
        cache: &mut [Option<f64>],
    ) -> Result<Vec<f64>> {
        command
            .args
            .iter()
            .map(|arg| {
                eval_compiled_f64_readonly(*arg, row_index, entity, program, &*self.world, cache)
            })
            .collect()
    }

    fn collect_compiled_row_local_canvas_root(
        &self,
        action_index: usize,
        query_name: &str,
        rows: &[Entity],
        program: &CompiledF64ReadOnlyProgram<'_>,
        out: &mut Vec<ExecutionCanvasCommand>,
        rows_scanned: &mut usize,
    ) -> Result<()> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(()),
            ActionNode::Sequence(children) => {
                for child in children {
                    self.collect_compiled_row_local_canvas_root(
                        *child,
                        query_name,
                        rows,
                        program,
                        out,
                        rows_scanned,
                    )?;
                }
                Ok(())
            }
            ActionNode::CanvasCommand(command) => {
                if self.canvas_command_uses_query(command, query_name)? {
                    *rows_scanned += rows.len();
                    for (row_index, entity) in rows.iter().copied().enumerate() {
                        self.emit_compiled_row_local_canvas_command(
                            command, row_index, entity, program, out,
                        )?;
                    }
                } else {
                    self.emit_compiled_row_local_canvas_command(command, 0, rows[0], program, out)?;
                }
                Ok(())
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                let row_scoped = self.expr_uses_query(*condition, query_name)?
                    || self.action_uses_query(*then_action, query_name)?
                    || otherwise_action
                        .map(|action| self.action_uses_query(action, query_name))
                        .transpose()?
                        .unwrap_or(false);
                if row_scoped {
                    *rows_scanned += rows.len();
                    for (row_index, entity) in rows.iter().copied().enumerate() {
                        let mut cache = self.compiled_canvas_cache(program);
                        let condition_value = eval_compiled_f64_readonly(
                            *condition,
                            row_index,
                            entity,
                            program,
                            &*self.world,
                            &mut cache,
                        )?;
                        if truthy_f64(condition_value) {
                            self.collect_compiled_row_local_canvas_for_row(
                                *then_action,
                                row_index,
                                entity,
                                program,
                                out,
                                &mut cache,
                            )?;
                        } else if let Some(otherwise_action) = otherwise_action {
                            self.collect_compiled_row_local_canvas_for_row(
                                *otherwise_action,
                                row_index,
                                entity,
                                program,
                                out,
                                &mut cache,
                            )?;
                        }
                    }
                } else {
                    let mut cache = self.compiled_canvas_cache(program);
                    let condition_value = eval_compiled_f64_readonly(
                        *condition,
                        0,
                        rows[0],
                        program,
                        &*self.world,
                        &mut cache,
                    )?;
                    if truthy_f64(condition_value) {
                        self.collect_compiled_row_local_canvas_root(
                            *then_action,
                            query_name,
                            rows,
                            program,
                            out,
                            rows_scanned,
                        )?;
                    } else if let Some(otherwise_action) = otherwise_action {
                        self.collect_compiled_row_local_canvas_root(
                            *otherwise_action,
                            query_name,
                            rows,
                            program,
                            out,
                            rows_scanned,
                        )?;
                    }
                }
                Ok(())
            }
            other => Err(EcsError::InvalidPlan(format!(
                "row-local canvas executor does not support action {other:?}"
            ))),
        }
    }

    fn collect_compiled_row_local_canvas_for_row(
        &self,
        action_index: usize,
        row_index: usize,
        entity: Entity,
        program: &CompiledF64ReadOnlyProgram<'_>,
        out: &mut Vec<ExecutionCanvasCommand>,
        cache: &mut [Option<f64>],
    ) -> Result<()> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(()),
            ActionNode::Sequence(children) => {
                for child in children {
                    self.collect_compiled_row_local_canvas_for_row(
                        *child, row_index, entity, program, out, cache,
                    )?;
                }
                Ok(())
            }
            ActionNode::CanvasCommand(command) => self
                .emit_compiled_row_local_canvas_command(command, row_index, entity, program, out),
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                let condition_value = eval_compiled_f64_readonly(
                    *condition,
                    row_index,
                    entity,
                    program,
                    &*self.world,
                    cache,
                )?;
                if truthy_f64(condition_value) {
                    self.collect_compiled_row_local_canvas_for_row(
                        *then_action,
                        row_index,
                        entity,
                        program,
                        out,
                        cache,
                    )
                } else if let Some(otherwise_action) = otherwise_action {
                    self.collect_compiled_row_local_canvas_for_row(
                        *otherwise_action,
                        row_index,
                        entity,
                        program,
                        out,
                        cache,
                    )
                } else {
                    Ok(())
                }
            }
            other => Err(EcsError::InvalidPlan(format!(
                "row-local canvas executor does not support row action {other:?}"
            ))),
        }
    }

    fn emit_compiled_row_local_canvas_command(
        &self,
        command: &CanvasCommandNode,
        row_index: usize,
        entity: Entity,
        program: &CompiledF64ReadOnlyProgram<'_>,
        out: &mut Vec<ExecutionCanvasCommand>,
    ) -> Result<()> {
        let mut cache = self.compiled_canvas_cache(program);
        let args = command
            .args
            .iter()
            .map(|arg| {
                eval_compiled_f64_readonly(
                    *arg,
                    row_index,
                    entity,
                    program,
                    &*self.world,
                    &mut cache,
                )
                .map(EcsValue::F64)
            })
            .collect::<Result<Vec<_>>>()?;
        out.push(ExecutionCanvasCommand {
            command: command.command.clone(),
            args,
        });
        Ok(())
    }

    pub(in crate::execution::row_local) fn compiled_canvas_cache(
        &self,
        program: &CompiledF64ReadOnlyProgram<'_>,
    ) -> Vec<Option<f64>> {
        let mut cache = vec![None; self.plan.expressions.len()];
        for (index, value) in &program.initial_values {
            cache[*index] = Some(*value);
        }
        cache
    }
}
