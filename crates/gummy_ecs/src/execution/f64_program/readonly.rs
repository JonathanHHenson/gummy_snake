use std::collections::HashMap;

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, PhysicalPlan};
use crate::world::World;

use super::super::{bool_f64, default_input_state_value, numeric_f64, truthy_f64};
use super::compiler::{compiled_field_f64_value, compiled_spatial_f64_value};
use super::ops::{eval_binary_f64, eval_f64_binary_op, eval_f64_unary_op, eval_unary_f64};
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
            return Err(EcsError::InvalidPlan(message.clone()))
        }
    };
    cache[expr_index] = Some(value);
    Ok(value)
}

#[allow(dead_code)]
fn eval_expr_f64_readonly(
    expr_index: usize,
    entity: Entity,
    query_name: &str,
    plan: &PhysicalPlan,
    world: &World,
    numeric_field_cache: &HashMap<String, HashMap<String, Vec<Option<(u32, f64)>>>>,
    spatial_precomputed_f64: &HashMap<usize, Vec<Option<(u32, f64)>>>,
    cache: &mut [Option<f64>],
) -> Result<f64> {
    if let Some(value) = cache[expr_index] {
        return Ok(value);
    }
    let value = match &plan.expressions[expr_index] {
        ExprNode::LiteralF64(value) => *value,
        ExprNode::LiteralI64(value) => *value as f64,
        ExprNode::LiteralBool(value) => bool_f64(*value),
        ExprNode::LiteralValue(value) => numeric_f64(value)?,
        ExprNode::Field {
            query,
            component,
            field,
        } => {
            if query != query_name {
                return Err(EcsError::InvalidPlan(format!(
                    "readonly f64 evaluator cannot read unbound query '{query}'"
                )));
            }
            let Some(fields) = numeric_field_cache.get(component) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing component '{component}'"
                )));
            };
            let Some(values) = fields.get(field) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing field '{component}.{field}'"
                )));
            };
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache missing entity {}:{} for '{component}.{field}'",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(format!(
                    "numeric field cache has stale entity generation for {}:{}",
                    entity.index, entity.generation
                )));
            }
            *value
        }
        ExprNode::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)?
        }
        ExprNode::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        )?,
        ExprNode::Unary { op, input } => {
            let input = eval_expr_f64_readonly(
                *input,
                entity,
                query_name,
                plan,
                world,
                numeric_field_cache,
                spatial_precomputed_f64,
                cache,
            )?;
            eval_unary_f64(op, input)?
        }
        ExprNode::Binary { op, left, right } => {
            if matches!(op.as_str(), "and" | "&&") {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                if !truthy_f64(left) {
                    0.0
                } else {
                    bool_f64(truthy_f64(eval_expr_f64_readonly(
                        *right,
                        entity,
                        query_name,
                        plan,
                        world,
                        numeric_field_cache,
                        spatial_precomputed_f64,
                        cache,
                    )?))
                }
            } else if matches!(op.as_str(), "or" | "||") {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                if truthy_f64(left) {
                    1.0
                } else {
                    bool_f64(truthy_f64(eval_expr_f64_readonly(
                        *right,
                        entity,
                        query_name,
                        plan,
                        world,
                        numeric_field_cache,
                        spatial_precomputed_f64,
                        cache,
                    )?))
                }
            } else {
                let left = eval_expr_f64_readonly(
                    *left,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                let right = eval_expr_f64_readonly(
                    *right,
                    entity,
                    query_name,
                    plan,
                    world,
                    numeric_field_cache,
                    spatial_precomputed_f64,
                    cache,
                )?;
                eval_binary_f64(op, left, right)?
            }
        }
        ExprNode::ContextJoin { predicate, .. } => eval_expr_f64_readonly(
            *predicate,
            entity,
            query_name,
            plan,
            world,
            numeric_field_cache,
            spatial_precomputed_f64,
            cache,
        )?,
        ExprNode::SpatialAggregate { .. } => {
            let Some(values) = spatial_precomputed_f64.get(&expr_index) else {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} was not precomputed"
                )));
            };
            let Some(Some((generation, value))) = values.get(entity.index as usize) else {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} missing entity {}:{}",
                    entity.index, entity.generation
                )));
            };
            if *generation != entity.generation {
                return Err(EcsError::InvalidPlan(format!(
                    "spatial aggregate expression {expr_index} has stale entity generation"
                )));
            }
            *value
        }
        ExprNode::Attribute { input, .. } => eval_expr_f64_readonly(
            *input,
            entity,
            query_name,
            plan,
            world,
            numeric_field_cache,
            spatial_precomputed_f64,
            cache,
        )?,
        other => {
            return Err(EcsError::InvalidPlan(format!(
                "readonly f64 evaluator does not support expression {expr_index}: {other:?}"
            )))
        }
    };
    cache[expr_index] = Some(value);
    Ok(value)
}
