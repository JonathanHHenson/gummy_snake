use crate::entity::Entity;
use crate::error::Result;
use crate::plan::{ActionNode, CanvasCommandNode, PhysicalPlan};
use crate::world::World;

use super::super::f64_program::{eval_compiled_f64_readonly, CompiledF64ReadOnlyProgram};
use super::super::{truthy_f64, ExecutionCanvasCommand, ExecutionCanvasFillRecord};

mod collection;

pub(super) type RowLocalFillBatch = Option<(
    Vec<ExecutionCanvasCommand>,
    Vec<ExecutionCanvasFillRecord>,
    usize,
)>;

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
    match command {
        "rect" if args.len() == 4 => Some(ExecutionCanvasFillRecord::rect(
            args[0], args[1], args[2], args[3], fill,
        )),
        "circle" if args.len() == 3 => Some(ExecutionCanvasFillRecord::ellipse_centered(
            args[0], args[1], args[2], args[2], fill,
        )),
        "ellipse" if args.len() == 3 || args.len() == 4 => {
            Some(ExecutionCanvasFillRecord::ellipse_centered(
                args[0],
                args[1],
                args[2],
                if args.len() == 4 { args[3] } else { args[2] },
                fill,
            ))
        }
        "triangle" if args.len() == 6 => Some(ExecutionCanvasFillRecord::triangle(
            (args[0], args[1]),
            (args[2], args[3]),
            (args[4], args[5]),
            fill,
        )),
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
