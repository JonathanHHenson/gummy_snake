use std::collections::{BTreeSet, HashMap, HashSet};
use std::time::Instant;

use rayon::prelude::*;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, CanvasCommandNode, ExprNode, PhysicalPlan};
use crate::world::World;

use super::f64_program::{
    build_row_local_field_dependents, compile_f64_readonly_program, compiled_field_f64_value,
    eval_compiled_f64_readonly, execute_row_local_f64_action, invalidate_row_local_f64_cache,
    CompiledF64ReadOnlyProgram, RowLocalAction, RowLocalTarget,
};
use super::{
    storage_type_is_numeric, truthy_f64, EvalContext, ExecutionCanvasCommand,
    ExecutionCanvasFillBatch, ExecutionCanvasFillRecord, PlanExecutor, SpatialPrecomputeLayout,
};

const CANVAS_FILL_RECT: u8 = 1;
const CANVAS_FILL_TRIANGLE: u8 = 2;
const CANVAS_FILL_ELLIPSE: u8 = 3;

type CanvasFill = [u8; 4];

fn color_channel(value: f64) -> u8 {
    value.clamp(0.0, 255.0).round() as u8
}

fn parse_canvas_fill(args: &[f64]) -> Option<CanvasFill> {
    if !(args.len() == 3 || args.len() == 4) {
        return None;
    }
    Some([
        color_channel(args[0]),
        color_channel(args[1]),
        color_channel(args[2]),
        if args.len() == 4 {
            color_channel(args[3])
        } else {
            255
        },
    ])
}

fn canvas_fill_primitive_supported(command: &str, arg_count: usize) -> bool {
    matches!(
        (command, arg_count),
        ("rect", 4) | ("circle", 3) | ("ellipse", 3 | 4) | ("triangle", 6)
    )
}

fn canvas_fill_record(
    command: &str,
    args: &[f64],
    fill: CanvasFill,
) -> Option<ExecutionCanvasFillRecord> {
    let [r, g, blue, alpha] = fill;
    match command {
        "rect" if args.len() == 4 => Some(ExecutionCanvasFillRecord {
            kind: CANVAS_FILL_RECT,
            a: args[0],
            b: args[1],
            c: args[2],
            d: args[3],
            e: 0.0,
            f: 0.0,
            r,
            g,
            blue,
            alpha,
        }),
        "circle" if args.len() == 3 => {
            let diameter = args[2];
            Some(ExecutionCanvasFillRecord {
                kind: CANVAS_FILL_ELLIPSE,
                a: args[0] - diameter / 2.0,
                b: args[1] - diameter / 2.0,
                c: diameter,
                d: diameter,
                e: 0.0,
                f: 0.0,
                r,
                g,
                blue,
                alpha,
            })
        }
        "ellipse" if args.len() == 3 || args.len() == 4 => {
            let width = args[2];
            let height = if args.len() == 4 { args[3] } else { width };
            Some(ExecutionCanvasFillRecord {
                kind: CANVAS_FILL_ELLIPSE,
                a: args[0] - width / 2.0,
                b: args[1] - height / 2.0,
                c: width,
                d: height,
                e: 0.0,
                f: 0.0,
                r,
                g,
                blue,
                alpha,
            })
        }
        "triangle" if args.len() == 6 => Some(ExecutionCanvasFillRecord {
            kind: CANVAS_FILL_TRIANGLE,
            a: args[0],
            b: args[1],
            c: args[2],
            d: args[3],
            e: args[4],
            f: args[5],
            r,
            g,
            blue,
            alpha,
        }),
        _ => None,
    }
}

fn compiled_canvas_cache_for_program(
    expr_count: usize,
    program: &CompiledF64ReadOnlyProgram<'_>,
) -> Vec<Option<f64>> {
    let mut cache = vec![None; expr_count];
    for (index, value) in &program.initial_values {
        cache[*index] = Some(*value);
    }
    cache
}

fn eval_canvas_command_f64_args_with_world(
    command: &CanvasCommandNode,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache: &mut [Option<f64>],
) -> Result<Vec<f64>> {
    command
        .args
        .iter()
        .map(|arg| eval_compiled_f64_readonly(*arg, row_index, entity, program, world, cache))
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn collect_fill_batch_for_row_compiled(
    action_index: usize,
    plan: &PhysicalPlan,
    world: &World,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    fill: &mut Option<CanvasFill>,
    records: &mut Vec<ExecutionCanvasFillRecord>,
    cache: &mut [Option<f64>],
) -> Result<bool> {
    match &plan.actions[action_index] {
        ActionNode::Noop => Ok(true),
        ActionNode::Sequence(children) => {
            for child in children {
                if !collect_fill_batch_for_row_compiled(
                    *child, plan, world, row_index, entity, program, fill, records, cache,
                )? {
                    return Ok(false);
                }
            }
            Ok(true)
        }
        ActionNode::CanvasCommand(command) => {
            if !canvas_fill_primitive_supported(command.command.as_str(), command.args.len()) {
                return Ok(false);
            }
            let Some(current_fill) = *fill else {
                return Ok(false);
            };
            let args = eval_canvas_command_f64_args_with_world(
                command, row_index, entity, program, world, cache,
            )?;
            let Some(record) = canvas_fill_record(command.command.as_str(), &args, current_fill)
            else {
                return Ok(false);
            };
            records.push(record);
            Ok(true)
        }
        ActionNode::When {
            condition,
            then_action,
            otherwise_action,
        } => {
            let condition_value =
                eval_compiled_f64_readonly(*condition, row_index, entity, program, world, cache)?;
            if truthy_f64(condition_value) {
                collect_fill_batch_for_row_compiled(
                    *then_action,
                    plan,
                    world,
                    row_index,
                    entity,
                    program,
                    fill,
                    records,
                    cache,
                )
            } else if let Some(otherwise_action) = otherwise_action {
                collect_fill_batch_for_row_compiled(
                    *otherwise_action,
                    plan,
                    world,
                    row_index,
                    entity,
                    program,
                    fill,
                    records,
                    cache,
                )
            } else {
                Ok(true)
            }
        }
        _ => Ok(false),
    }
}

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn row_local_numeric_action_query(
        &self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Option<String> {
        if contexts.len() != 1
            || !contexts[0].bindings.is_empty()
            || !contexts[0].loop_items.is_empty()
        {
            return None;
        }
        if !self.action_contains_when(action_index) {
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
        if contexts.len() != 1
            || !contexts[0].bindings.is_empty()
            || !contexts[0].loop_items.is_empty()
        {
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
                    .is_ok_and(storage_type_is_numeric)
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
                let Some(primary_query) = query_name.as_deref() else {
                    return false;
                };
                self.expr_supports_f64(*condition, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*condition, primary_query)
                    && self.row_local_numeric_action_supported(*then_action, query_name)
                    && otherwise_action.is_none_or(|action| {
                        self.row_local_numeric_action_supported(action, query_name)
                    })
            }
            ActionNode::Parallel(_)
            | ActionNode::ForEach { .. }
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
            | ExprNode::SpatialAggregate { .. } => true,
            ExprNode::Field { query, .. } => query == query_name,
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*input, query_name, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*left, query_name, seen)
                    && self.expr_uses_only_row_local_direct_fields_inner(*right, query_name, seen)
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. }
            | ExprNode::ContextJoin { .. }
            | ExprNode::Exists { .. }
            | ExprNode::Aggregate { .. }
            | ExprNode::SpatialMetadata { .. } => false,
        }
    }

    fn compile_row_local_action(
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
            } => Ok(RowLocalAction::When {
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
            }),
            other => Err(EcsError::InvalidPlan(format!(
                "row-local numeric executor does not support action {other:?}"
            ))),
        }
    }

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

    fn collect_compiled_row_local_fill_batch(
        &self,
        action_index: usize,
        query_name: &str,
        rows: &[Entity],
        program: &CompiledF64ReadOnlyProgram<'_>,
    ) -> Result<
        Option<(
            Vec<ExecutionCanvasCommand>,
            Vec<ExecutionCanvasFillRecord>,
            usize,
        )>,
    > {
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

    fn eval_canvas_command_f64_args(
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

    fn compiled_canvas_cache(&self, program: &CompiledF64ReadOnlyProgram<'_>) -> Vec<Option<f64>> {
        let mut cache = vec![None; self.plan.expressions.len()];
        for (index, value) in &program.initial_values {
            cache[*index] = Some(*value);
        }
        cache
    }

    fn canvas_command_uses_query(
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

    fn action_uses_query(&self, action_index: usize, query_name: &str) -> Result<bool> {
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

    fn expr_uses_query(&self, expr_index: usize, query_name: &str) -> Result<bool> {
        let mut queries = BTreeSet::new();
        self.collect_expr_queries(expr_index, &mut queries)?;
        Ok(queries.contains(query_name))
    }

    pub(in crate::execution) fn execute_row_local_numeric_action(
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
                "ecs_profile row_local_f64_precompute elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let preload_start = self.profile.then(Instant::now);
        self.preload_numeric_fields_for_query(query_name, SpatialPrecomputeLayout::QueryRows)?;
        if let Some(start) = preload_start {
            eprintln!(
                "ecs_profile row_local_f64_preload elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let locations = self.query_locations(query_name)?;
        let program = compile_f64_readonly_program(
            self.plan,
            self.world,
            query_name,
            &self.numeric_field_cache,
            &self.numeric_field_cache_rows,
            &self.spatial_precomputed_f64,
            &self.spatial_precomputed_f64_rows,
        );
        let mut targets = Vec::new();
        let mut target_slots = HashMap::new();
        let action = self.compile_row_local_action(
            action_index,
            query_name,
            &program,
            &mut targets,
            &mut target_slots,
        )?;
        let target_count = targets.len();
        if target_count == 0 {
            return Ok(());
        }

        let expr_count = self.plan.expressions.len();
        let field_count = program.field_arrays.len();
        let field_dependents = build_row_local_field_dependents(&program);
        let mut flat_values = vec![0.0; rows.len() * target_count];
        let mut dirty = vec![false; rows.len() * target_count];
        let eval_start = self.profile.then(Instant::now);
        let world = &*self.world;
        flat_values
            .par_chunks_mut(target_count)
            .zip(dirty.par_chunks_mut(target_count))
            .zip(rows.par_iter().enumerate())
            .try_for_each_init(
                || {
                    (
                        vec![0.0; expr_count],
                        vec![0_u32; expr_count],
                        1_u32,
                        vec![0.0; field_count],
                    )
                },
                |(cache_values, cache_marks, cache_generation, field_values),
                 ((out, dirty_row), (row_index, entity))| {
                    invalidate_row_local_f64_cache(cache_marks, cache_generation);
                    for (slot, value) in field_values.iter_mut().enumerate() {
                        *value = compiled_field_f64_value(
                            program.field_arrays[slot],
                            row_index,
                            *entity,
                        )?;
                    }
                    execute_row_local_f64_action(
                        &action,
                        row_index,
                        *entity,
                        &program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        &field_dependents,
                        out,
                        dirty_row,
                    )
                },
            )?;
        if let Some(start) = eval_start {
            eprintln!(
                "ecs_profile row_local_f64_eval elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        self.report.rows_scanned += rows.len();

        let apply_start = self.profile.then(Instant::now);
        for (target_index, target) in targets.iter().enumerate() {
            let all_dirty = (0..rows.len()).all(|row| dirty[row * target_count + target_index]);
            if all_dirty {
                self.report.fields_written += self.world.set_field_f64_resolved_strided(
                    &target.component,
                    &target.field,
                    &locations,
                    &flat_values,
                    target_index,
                    target_count,
                )?;
                continue;
            }
            let mut writes = Vec::new();
            for (row_index, entity) in rows.iter().enumerate() {
                if dirty[row_index * target_count + target_index] {
                    writes.push((
                        *entity,
                        flat_values[row_index * target_count + target_index],
                    ));
                }
            }
            if !writes.is_empty() {
                self.report.fields_written +=
                    self.world
                        .set_field_f64_many(&target.component, &target.field, &writes)?;
            }
        }
        if let Some(start) = apply_start {
            eprintln!(
                "ecs_profile row_local_f64_apply elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }
}
