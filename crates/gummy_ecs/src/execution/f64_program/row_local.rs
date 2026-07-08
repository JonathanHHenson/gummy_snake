use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::world::World;

use super::super::{bool_f64, default_input_state_value, numeric_f64, truthy_f64};
use super::compiler::compiled_spatial_f64_value;
use super::ops::{eval_f64_binary_op, eval_f64_unary_op};
use super::{CompiledF64Expr, CompiledF64ReadOnlyProgram, F64BinaryOp, RowLocalAction};

pub(in crate::execution) fn build_row_local_field_dependents(
    program: &CompiledF64ReadOnlyProgram<'_>,
) -> Vec<Vec<usize>> {
    let mut dependents = vec![Vec::new(); program.field_arrays.len()];
    let mut memo = vec![None; program.expressions.len()];
    for expr_index in 0..program.expressions.len() {
        let canonical = program.aliases[expr_index];
        let deps = row_local_f64_field_dependencies(canonical, program, &mut memo);
        for field_slot in deps {
            if let Some(field_dependents) = dependents.get_mut(field_slot) {
                field_dependents.push(canonical);
            }
        }
    }
    for field_dependents in &mut dependents {
        field_dependents.sort_unstable();
        field_dependents.dedup();
    }
    dependents
}

fn row_local_f64_field_dependencies(
    expr_index: usize,
    program: &CompiledF64ReadOnlyProgram<'_>,
    memo: &mut [Option<Vec<usize>>],
) -> Vec<usize> {
    let expr_index = program.aliases[expr_index];
    if let Some(deps) = memo[expr_index].clone() {
        return deps;
    }
    let expression = program.expressions[expr_index].clone();
    let mut deps = match expression {
        CompiledF64Expr::Field(slot) => vec![slot],
        CompiledF64Expr::Unary { input, .. } | CompiledF64Expr::Passthrough(input) => {
            row_local_f64_field_dependencies(input, program, memo)
        }
        CompiledF64Expr::Binary { left, right, .. } => {
            let mut deps = row_local_f64_field_dependencies(left, program, memo);
            deps.extend(row_local_f64_field_dependencies(right, program, memo));
            deps
        }
        CompiledF64Expr::Literal(_)
        | CompiledF64Expr::SpatialAggregate(_)
        | CompiledF64Expr::ForEachItem(_)
        | CompiledF64Expr::ResourceField { .. }
        | CompiledF64Expr::InputState { .. }
        | CompiledF64Expr::Unsupported(_) => Vec::new(),
    };
    deps.sort_unstable();
    deps.dedup();
    memo[expr_index] = Some(deps.clone());
    deps
}

pub(in crate::execution) fn invalidate_row_local_f64_cache(
    cache_marks: &mut [u32],
    cache_generation: &mut u32,
) {
    *cache_generation = cache_generation.wrapping_add(1);
    if *cache_generation == 0 {
        cache_marks.fill(0);
        *cache_generation = 1;
    }
}

pub(in crate::execution) fn execute_row_local_f64_action(
    action: &RowLocalAction,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache_values: &mut [f64],
    cache_marks: &mut [u32],
    cache_generation: &mut u32,
    field_values: &mut [f64],
    field_dependents: &[Vec<usize>],
    out: &mut [f64],
    dirty: &mut [bool],
    event_out: &mut Vec<(String, EcsValue)>,
    loop_items: &mut Vec<Option<f64>>,
) -> Result<()> {
    match action {
        RowLocalAction::Noop => Ok(()),
        RowLocalAction::Sequence(children) => {
            for child in children {
                execute_row_local_f64_action(
                    child,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                    event_out,
                    loop_items,
                )?;
            }
            Ok(())
        }
        RowLocalAction::SetField {
            field_slot,
            target_slot,
            value_expr,
        } => {
            let value = eval_row_local_f64_expr(
                *value_expr,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                *cache_generation,
                field_values,
                loop_items,
            )?;
            field_values[*field_slot] = value;
            if let Some(dependents) = field_dependents.get(*field_slot) {
                for expr_index in dependents {
                    cache_marks[*expr_index] = 0;
                }
            }
            out[*target_slot] = value;
            dirty[*target_slot] = true;
            Ok(())
        }
        RowLocalAction::ForEachListField {
            component,
            field,
            item_slot,
            action,
        } => {
            let value = world.get_field(entity, component, field)?;
            let EcsValue::List(items) = value else {
                return Err(EcsError::InvalidPlan(format!(
                    "row-local for_each source {component}.{field} must be a list"
                )));
            };
            if loop_items.len() <= *item_slot {
                loop_items.resize(*item_slot + 1, None);
            }
            let previous = loop_items[*item_slot];
            for item in items {
                invalidate_row_local_f64_cache(cache_marks, cache_generation);
                loop_items[*item_slot] = Some(numeric_f64(&item)?);
                execute_row_local_f64_action(
                    action,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                    event_out,
                    loop_items,
                )?;
            }
            loop_items[*item_slot] = previous;
            Ok(())
        }
        RowLocalAction::EmitConstEvent {
            event_type,
            payload,
        } => {
            event_out.push((event_type.clone(), payload.clone()));
            Ok(())
        }
        RowLocalAction::When {
            condition_expr,
            then_action,
            otherwise_action,
        } => {
            let condition = eval_row_local_f64_expr(
                *condition_expr,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                *cache_generation,
                field_values,
                loop_items,
            )?;
            if truthy_f64(condition) {
                execute_row_local_f64_action(
                    then_action,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                    event_out,
                    loop_items,
                )
            } else if let Some(otherwise_action) = otherwise_action {
                execute_row_local_f64_action(
                    otherwise_action,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    field_dependents,
                    out,
                    dirty,
                    event_out,
                    loop_items,
                )
            } else {
                Ok(())
            }
        }
    }
}

fn eval_row_local_f64_expr(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache_values: &mut [f64],
    cache_marks: &mut [u32],
    cache_generation: u32,
    field_values: &[f64],
    loop_items: &[Option<f64>],
) -> Result<f64> {
    let expr_index = program.aliases[expr_index];
    let cacheable = row_local_f64_expr_cacheable(&program.expressions[expr_index]);
    if cacheable && cache_marks[expr_index] == cache_generation {
        return Ok(cache_values[expr_index]);
    }
    let value = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => *value,
        CompiledF64Expr::Field(slot) => field_values[*slot],
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::ForEachItem(slot) => loop_items
            .get(*slot)
            .and_then(|value| *value)
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
            })?,
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        CompiledF64Expr::Unary { op, input } => {
            let input = eval_row_local_f64_expr(
                *input,
                row_index,
                entity,
                program,
                world,
                cache_values,
                cache_marks,
                cache_generation,
                field_values,
                loop_items,
            )?;
            eval_f64_unary_op(*op, input)
        }
        CompiledF64Expr::Binary { op, left, right } => match op {
            F64BinaryOp::And => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    loop_items,
                )?;
                if truthy_f64(left) {
                    bool_f64(truthy_f64(eval_row_local_f64_expr(
                        *right,
                        row_index,
                        entity,
                        program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        loop_items,
                    )?))
                } else {
                    0.0
                }
            }
            F64BinaryOp::Or => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    loop_items,
                )?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_row_local_f64_expr(
                        *right,
                        row_index,
                        entity,
                        program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        loop_items,
                    )?))
                }
            }
            op => {
                let left = eval_row_local_f64_expr(
                    *left,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    loop_items,
                )?;
                let right = eval_row_local_f64_expr(
                    *right,
                    row_index,
                    entity,
                    program,
                    world,
                    cache_values,
                    cache_marks,
                    cache_generation,
                    field_values,
                    loop_items,
                )?;
                eval_f64_binary_op(*op, left, right)
            }
        },
        CompiledF64Expr::Passthrough(input) => eval_row_local_f64_expr(
            *input,
            row_index,
            entity,
            program,
            world,
            cache_values,
            cache_marks,
            cache_generation,
            field_values,
            loop_items,
        )?,
        CompiledF64Expr::Unsupported(message) => {
            return Err(EcsError::InvalidPlan(message.clone()))
        }
    };
    if cacheable {
        cache_values[expr_index] = value;
        cache_marks[expr_index] = cache_generation;
    }
    Ok(value)
}

fn row_local_f64_expr_cacheable(expression: &CompiledF64Expr) -> bool {
    !matches!(expression, CompiledF64Expr::Unsupported(_))
}
