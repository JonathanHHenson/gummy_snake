use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::world::World;

use super::super::{bool_f64, default_input_state_value, numeric_f64, truthy_f64};
use super::compiler::{compiled_field_f64_value, compiled_spatial_f64_value};
use super::ops::{eval_f64_binary_op, eval_f64_unary_op};
use super::{CompiledF64Expr, CompiledF64ReadOnlyProgram, F64BinaryOp};

pub(in crate::execution) fn eval_compiled_f64_readonly(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    cache: &mut [Option<f64>],
) -> Result<f64> {
    let expr_index = program.aliases[expr_index];
    if let Some(value) = cache[expr_index] {
        return Ok(value);
    }
    let value = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => *value,
        CompiledF64Expr::Field(slot) => {
            compiled_field_f64_value(program.field_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)?
        }
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        CompiledF64Expr::Unary { op, input } => {
            let input =
                eval_compiled_f64_readonly(*input, row_index, entity, program, world, cache)?;
            eval_f64_unary_op(*op, input)
        }
        CompiledF64Expr::Binary { op, left, right } => match op {
            F64BinaryOp::And => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                if truthy_f64(left) {
                    bool_f64(truthy_f64(eval_compiled_f64_readonly(
                        *right, row_index, entity, program, world, cache,
                    )?))
                } else {
                    0.0
                }
            }
            F64BinaryOp::Or => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_compiled_f64_readonly(
                        *right, row_index, entity, program, world, cache,
                    )?))
                }
            }
            op => {
                let left =
                    eval_compiled_f64_readonly(*left, row_index, entity, program, world, cache)?;
                let right =
                    eval_compiled_f64_readonly(*right, row_index, entity, program, world, cache)?;
                eval_f64_binary_op(*op, left, right)
            }
        },
        CompiledF64Expr::Passthrough(input) => {
            eval_compiled_f64_readonly(*input, row_index, entity, program, world, cache)?
        }
        CompiledF64Expr::Unsupported(message) => {
            return Err(EcsError::InvalidPlan(message.clone()));
        }
    };
    cache[expr_index] = Some(value);
    Ok(value)
}
