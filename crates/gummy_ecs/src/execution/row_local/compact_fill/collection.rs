use rayon::prelude::*;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::ActionNode;

use super::super::super::{
    truthy_f64, ExecutionCanvasCommand, ExecutionCanvasFillRecord, PlanExecutor,
};
use super::{
    canvas_fill_primitive_supported, canvas_fill_record, collect_fill_batch_for_row_compiled,
    compiled_canvas_cache_for_program, eval_canvas_command_f64_args_with_world, parse_canvas_fill,
    CanvasFill, RowLocalFillBatch,
};
use crate::execution::optimized::f64_program::{
    eval_compiled_f64_readonly, CompiledF64ReadOnlyProgram,
};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution::row_local) fn collect_compiled_row_local_fill_batch(
        &self,
        action_index: usize,
        query_name: &str,
        rows: &[Entity],
        program: &CompiledF64ReadOnlyProgram<'_>,
    ) -> Result<RowLocalFillBatch> {
        let mut style_commands = Vec::new();
        let mut records = Vec::new();
        let mut rows_scanned = 0;
        let mut fill: Option<CanvasFill> = None;
        if !self.collect_fill_batch_root(
            action_index,
            query_name,
            rows,
            program,
            &mut fill,
            &mut style_commands,
            &mut records,
            &mut rows_scanned,
        )? {
            return Ok(None);
        }
        if records.is_empty() {
            return Ok(None);
        }
        Ok(Some((style_commands, records, rows_scanned)))
    }

    #[allow(clippy::too_many_arguments)]
    fn collect_fill_batch_root(
        &self,
        action_index: usize,
        query_name: &str,
        rows: &[Entity],
        program: &CompiledF64ReadOnlyProgram<'_>,
        fill: &mut Option<CanvasFill>,
        style_commands: &mut Vec<ExecutionCanvasCommand>,
        records: &mut Vec<ExecutionCanvasFillRecord>,
        rows_scanned: &mut usize,
    ) -> Result<bool> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(true),
            ActionNode::Sequence(children) => {
                for child in children {
                    if !self.collect_fill_batch_root(
                        *child,
                        query_name,
                        rows,
                        program,
                        fill,
                        style_commands,
                        records,
                        rows_scanned,
                    )? {
                        return Ok(false);
                    }
                }
                Ok(true)
            }
            ActionNode::CanvasCommand(command) => {
                let uses_query = self.canvas_command_uses_query(command, query_name)?;
                if uses_query {
                    let Some(current_fill) = *fill else {
                        return Ok(false);
                    };
                    if !canvas_fill_primitive_supported(
                        command.command.as_str(),
                        command.args.len(),
                    ) {
                        return Ok(false);
                    }
                    *rows_scanned += rows.len();
                    let expr_count = self.plan.expressions.len();
                    let world = &*self.world;
                    if rows.len() < 2_048 {
                        let mut cache = compiled_canvas_cache_for_program(expr_count, program);
                        for (row_index, entity) in rows.iter().copied().enumerate() {
                            cache.fill(None);
                            let args = eval_canvas_command_f64_args_with_world(
                                command, row_index, entity, program, world, &mut cache,
                            )?;
                            let Some(record) =
                                canvas_fill_record(command.command.as_str(), &args, current_fill)
                            else {
                                return Ok(false);
                            };
                            records.push(record);
                        }
                    } else {
                        let worker_count = rayon::current_num_threads().max(1);
                        let chunk_size = (rows.len() / (worker_count * 4)).clamp(128, 1024).max(1);
                        let chunk_records = rows
                            .par_chunks(chunk_size)
                            .enumerate()
                            .map(|(chunk_index, chunk)| {
                                let row_start = chunk_index * chunk_size;
                                let mut cache =
                                    compiled_canvas_cache_for_program(expr_count, program);
                                let mut out = Vec::with_capacity(chunk.len());
                                for (chunk_offset, entity) in chunk.iter().copied().enumerate() {
                                    cache.fill(None);
                                    let row_index = row_start + chunk_offset;
                                    let args = eval_canvas_command_f64_args_with_world(
                                        command, row_index, entity, program, world, &mut cache,
                                    )?;
                                    let Some(record) = canvas_fill_record(
                                        command.command.as_str(),
                                        &args,
                                        current_fill,
                                    ) else {
                                        return Err(EcsError::InvalidPlan(format!(
                                            "unsupported fill primitive command '{}'",
                                            command.command
                                        )));
                                    };
                                    out.push(record);
                                }
                                Ok(out)
                            })
                            .collect::<Result<Vec<_>>>()?;
                        for mut chunk in chunk_records {
                            records.append(&mut chunk);
                        }
                    }
                    return Ok(true);
                }
                let mut cache = self.compiled_canvas_cache(program);
                let args =
                    self.eval_canvas_command_f64_args(command, 0, rows[0], program, &mut cache)?;
                match command.command.as_str() {
                    "fill" => {
                        let Some(next_fill) = parse_canvas_fill(&args) else {
                            return Ok(false);
                        };
                        *fill = Some(next_fill);
                        style_commands.push(ExecutionCanvasCommand {
                            command: command.command.clone(),
                            args: args.iter().copied().map(EcsValue::F64).collect(),
                        });
                        Ok(true)
                    }
                    "no_fill" => {
                        *fill = None;
                        style_commands.push(ExecutionCanvasCommand {
                            command: command.command.clone(),
                            args: Vec::new(),
                        });
                        Ok(true)
                    }
                    "no_stroke" => {
                        style_commands.push(ExecutionCanvasCommand {
                            command: command.command.clone(),
                            args: Vec::new(),
                        });
                        Ok(true)
                    }
                    _ if canvas_fill_primitive_supported(
                        command.command.as_str(),
                        command.args.len(),
                    ) =>
                    {
                        let Some(current_fill) = *fill else {
                            return Ok(false);
                        };
                        let Some(record) =
                            canvas_fill_record(command.command.as_str(), &args, current_fill)
                        else {
                            return Ok(false);
                        };
                        records.push(record);
                        Ok(true)
                    }
                    _ => Ok(false),
                }
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
                    let expr_count = self.plan.expressions.len();
                    let plan = self.plan;
                    let world = &*self.world;
                    let initial_fill = *fill;
                    if rows.len() < 2_048 {
                        let mut cache = compiled_canvas_cache_for_program(expr_count, program);
                        for (row_index, entity) in rows.iter().copied().enumerate() {
                            cache.fill(None);
                            let condition_value = eval_compiled_f64_readonly(
                                *condition, row_index, entity, program, world, &mut cache,
                            )?;
                            let mut row_fill = initial_fill;
                            let supported = if truthy_f64(condition_value) {
                                collect_fill_batch_for_row_compiled(
                                    *then_action,
                                    plan,
                                    world,
                                    row_index,
                                    entity,
                                    program,
                                    &mut row_fill,
                                    records,
                                    &mut cache,
                                )?
                            } else if let Some(otherwise_action) = otherwise_action {
                                collect_fill_batch_for_row_compiled(
                                    *otherwise_action,
                                    plan,
                                    world,
                                    row_index,
                                    entity,
                                    program,
                                    &mut row_fill,
                                    records,
                                    &mut cache,
                                )?
                            } else {
                                true
                            };
                            if !supported {
                                return Ok(false);
                            }
                        }
                    } else {
                        let worker_count = rayon::current_num_threads().max(1);
                        let chunk_size = (rows.len() / (worker_count * 4)).clamp(128, 1024).max(1);
                        let chunk_records = rows
                            .par_chunks(chunk_size)
                            .enumerate()
                            .map(|(chunk_index, chunk)| {
                                let row_start = chunk_index * chunk_size;
                                let mut cache =
                                    compiled_canvas_cache_for_program(expr_count, program);
                                let mut out = Vec::with_capacity(chunk.len());
                                for (chunk_offset, entity) in chunk.iter().copied().enumerate() {
                                    cache.fill(None);
                                    let row_index = row_start + chunk_offset;
                                    let condition_value = eval_compiled_f64_readonly(
                                        *condition,
                                        row_index,
                                        entity,
                                        program,
                                        world,
                                        &mut cache,
                                    )?;
                                    let mut row_fill = initial_fill;
                                    let supported = if truthy_f64(condition_value) {
                                        collect_fill_batch_for_row_compiled(
                                            *then_action,
                                            plan,
                                            world,
                                            row_index,
                                            entity,
                                            program,
                                            &mut row_fill,
                                            &mut out,
                                            &mut cache,
                                        )?
                                    } else if let Some(otherwise_action) = otherwise_action {
                                        collect_fill_batch_for_row_compiled(
                                            *otherwise_action,
                                            plan,
                                            world,
                                            row_index,
                                            entity,
                                            program,
                                            &mut row_fill,
                                            &mut out,
                                            &mut cache,
                                        )?
                                    } else {
                                        true
                                    };
                                    if !supported {
                                        return Err(EcsError::InvalidPlan(
                                            "row-local fill batch contains an unsupported row action"
                                                .to_string(),
                                        ));
                                    }
                                }
                                Ok(out)
                            })
                            .collect::<Result<Vec<_>>>()?;
                        for mut chunk in chunk_records {
                            records.append(&mut chunk);
                        }
                    }
                    Ok(true)
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
                        self.collect_fill_batch_root(
                            *then_action,
                            query_name,
                            rows,
                            program,
                            fill,
                            style_commands,
                            records,
                            rows_scanned,
                        )
                    } else if let Some(otherwise_action) = otherwise_action {
                        self.collect_fill_batch_root(
                            *otherwise_action,
                            query_name,
                            rows,
                            program,
                            fill,
                            style_commands,
                            records,
                            rows_scanned,
                        )
                    } else {
                        Ok(true)
                    }
                }
            }
            _ => Ok(false),
        }
    }
}
