use std::collections::HashMap;

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::execution::{TypedExecutorPlan, TypedExpr};
use crate::plan::{ExprNode, PhysicalPlan};
use crate::world::World;

use super::super::{bool_f64, default_input_state_value, numeric_f64, SpatialF64RowArray};
use super::ops::{eval_f64_binary_op, eval_f64_unary_op, f64_binary_op, f64_unary_op};
use super::{
    CompiledF64Array, CompiledF64Expr, CompiledF64ExprKey, CompiledF64ReadOnlyProgram,
    CompiledSpatialF64Array, F64BinaryOp,
};

type EntityF64Cache = HashMap<String, HashMap<String, HashMap<Entity, f64>>>;
type QueryRowF64Cache = HashMap<String, HashMap<String, Vec<f64>>>;

#[allow(clippy::too_many_arguments)]
pub(in crate::execution) fn compile_f64_readonly_program<'a>(
    plan: &PhysicalPlan,
    typed_plan: &TypedExecutorPlan,
    _world: &World,
    query_name: &str,
    numeric_field_cache: &'a EntityF64Cache,
    numeric_field_cache_rows: &'a QueryRowF64Cache,
    spatial_precomputed_f64: &'a HashMap<usize, HashMap<Entity, f64>>,
    spatial_precomputed_f64_rows: &'a HashMap<usize, SpatialF64RowArray>,
) -> CompiledF64ReadOnlyProgram<'a> {
    let mut expressions = Vec::with_capacity(plan.expressions.len());
    let mut field_arrays = Vec::new();
    let mut field_array_slots: HashMap<(String, String), usize> = HashMap::new();
    let mut spatial_arrays = Vec::new();
    for (expr_index, expr) in plan.expressions.iter().enumerate() {
        let compiled = match expr {
            ExprNode::LiteralF64(value) => CompiledF64Expr::Literal(*value),
            ExprNode::LiteralI64(value) => CompiledF64Expr::Literal(*value as f64),
            ExprNode::LiteralBool(value) => CompiledF64Expr::Literal(bool_f64(*value)),
            ExprNode::LiteralValue(value) => match numeric_f64(value) {
                Ok(value) => CompiledF64Expr::Literal(value),
                Err(error) => CompiledF64Expr::Unsupported(error.to_string()),
            },
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                if query != query_name {
                    CompiledF64Expr::Unsupported(format!(
                        "readonly f64 evaluator cannot read unbound query '{query}'"
                    ))
                } else if let Some(values) = numeric_field_cache_rows
                    .get(component)
                    .and_then(|fields| fields.get(field))
                {
                    let key = (component.clone(), field.clone());
                    let slot = if let Some(slot) = field_array_slots.get(&key) {
                        *slot
                    } else {
                        let slot = field_arrays.len();
                        field_arrays.push(CompiledF64Array::QueryRows(values.as_slice()));
                        field_array_slots.insert(key, slot);
                        slot
                    };
                    CompiledF64Expr::Field(slot)
                } else if let Some(values) = numeric_field_cache
                    .get(component)
                    .and_then(|fields| fields.get(field))
                {
                    let key = (component.clone(), field.clone());
                    let slot = if let Some(slot) = field_array_slots.get(&key) {
                        *slot
                    } else {
                        let slot = field_arrays.len();
                        field_arrays.push(CompiledF64Array::SparseEntity(values));
                        field_array_slots.insert(key, slot);
                        slot
                    };
                    CompiledF64Expr::Field(slot)
                } else {
                    CompiledF64Expr::Unsupported(format!(
                        "numeric field cache missing field '{component}.{field}'"
                    ))
                }
            }
            ExprNode::ResourceField { resource, field } => CompiledF64Expr::ResourceField {
                resource: resource.clone(),
                field: field.clone(),
            },
            ExprNode::ForEachItem { slot } => CompiledF64Expr::ForEachItem(*slot),
            ExprNode::InputState { name, code } => CompiledF64Expr::InputState {
                name: name.clone(),
                code: *code,
            },
            ExprNode::Unary { op, input } => {
                let TypedExpr::Unary(typed_op) = typed_plan.expression(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                match f64_unary_op(typed_op) {
                    Some(op) => CompiledF64Expr::Unary { op, input: *input },
                    None => CompiledF64Expr::Unsupported(format!(
                        "unsupported physical unary op '{op}'"
                    )),
                }
            }
            ExprNode::Binary { op, left, right } => {
                let TypedExpr::Binary(typed_op) = typed_plan.expression(expr_index) else {
                    unreachable!("typed executor expression must match bridge expression")
                };
                match f64_binary_op(typed_op) {
                    Some(op) => CompiledF64Expr::Binary {
                        op,
                        left: *left,
                        right: *right,
                    },
                    None => CompiledF64Expr::Unsupported(format!(
                        "unsupported physical binary op '{op}'"
                    )),
                }
            }
            ExprNode::ContextJoin { predicate, .. } => CompiledF64Expr::Passthrough(*predicate),
            ExprNode::SpatialAggregate { .. } => {
                if let Some(values) = spatial_precomputed_f64_rows.get(&expr_index) {
                    let slot = spatial_arrays.len();
                    match values {
                        SpatialF64RowArray::Dense(values) => {
                            spatial_arrays
                                .push(CompiledSpatialF64Array::QueryRows(values.as_slice()));
                        }
                        SpatialF64RowArray::Optional(values) => {
                            spatial_arrays.push(CompiledSpatialF64Array::QueryRowsOptional(
                                values.as_slice(),
                            ));
                        }
                    }
                    CompiledF64Expr::SpatialAggregate(slot)
                } else if let Some(values) = spatial_precomputed_f64.get(&expr_index) {
                    let slot = spatial_arrays.len();
                    spatial_arrays.push(CompiledSpatialF64Array::SparseEntity(values));
                    CompiledF64Expr::SpatialAggregate(slot)
                } else {
                    CompiledF64Expr::Unsupported(format!(
                        "spatial aggregate expression {expr_index} was not precomputed"
                    ))
                }
            }
            ExprNode::Attribute { input, .. } => CompiledF64Expr::Passthrough(*input),
            other => CompiledF64Expr::Unsupported(format!(
                "readonly f64 evaluator does not support expression {expr_index}: {other:?}"
            )),
        };
        expressions.push(compiled);
    }
    let aliases = build_compiled_f64_aliases(&expressions);
    let initial_values = expressions
        .iter()
        .enumerate()
        .filter_map(|(index, expression)| {
            if aliases[index] == index {
                if let CompiledF64Expr::Literal(value) = expression {
                    return Some((index, *value));
                }
            }
            None
        })
        .collect();
    CompiledF64ReadOnlyProgram {
        expressions,
        aliases,
        initial_values,
        field_arrays,
        field_slot_by_key: field_array_slots,
        spatial_arrays,
    }
}

fn build_compiled_f64_aliases(expressions: &[CompiledF64Expr]) -> Vec<usize> {
    let mut aliases = vec![0; expressions.len()];
    let mut seen: HashMap<CompiledF64ExprKey, usize> = HashMap::new();
    for (index, expression) in expressions.iter().enumerate() {
        let key = compiled_f64_expr_key(expression, &aliases, index);
        if let Some(key) = key {
            if let Some(existing) = seen.get(&key) {
                aliases[index] = *existing;
            } else {
                aliases[index] = index;
                seen.insert(key, index);
            }
        } else {
            aliases[index] = index;
        }
    }
    aliases
}

fn compiled_f64_expr_key(
    expression: &CompiledF64Expr,
    aliases: &[usize],
    current_index: usize,
) -> Option<CompiledF64ExprKey> {
    let alias = |index: usize| -> usize {
        if index < current_index {
            aliases[index]
        } else {
            index
        }
    };
    match expression {
        CompiledF64Expr::Literal(value) => Some(CompiledF64ExprKey::Literal(value.to_bits())),
        CompiledF64Expr::Field(slot) => Some(CompiledF64ExprKey::Field(*slot)),
        CompiledF64Expr::SpatialAggregate(slot) => {
            Some(CompiledF64ExprKey::SpatialAggregate(*slot))
        }
        CompiledF64Expr::ForEachItem(slot) => Some(CompiledF64ExprKey::ForEachItem(*slot)),
        CompiledF64Expr::ResourceField { resource, field } => Some(
            CompiledF64ExprKey::ResourceField(resource.clone(), field.clone()),
        ),
        CompiledF64Expr::InputState { name, code } => {
            Some(CompiledF64ExprKey::InputState(name.clone(), *code))
        }
        CompiledF64Expr::Unary { op, input } => Some(CompiledF64ExprKey::Unary(*op, alias(*input))),
        CompiledF64Expr::Binary { op, left, right } => {
            Some(CompiledF64ExprKey::Binary(*op, alias(*left), alias(*right)))
        }
        CompiledF64Expr::Passthrough(input) => Some(CompiledF64ExprKey::Passthrough(alias(*input))),
        CompiledF64Expr::Unsupported(_) => None,
    }
}

pub(in crate::execution) fn compiled_f64_eval_order(
    program: &CompiledF64ReadOnlyProgram<'_>,
    outputs: impl IntoIterator<Item = usize>,
) -> Option<Vec<usize>> {
    let mut order = Vec::new();
    let mut visited = vec![false; program.expressions.len()];
    let mut visiting = vec![false; program.expressions.len()];
    for output in outputs {
        if !collect_compiled_f64_eval_order(
            program.aliases[output],
            program,
            &mut visited,
            &mut visiting,
            &mut order,
        ) {
            return None;
        }
    }
    Some(order)
}

fn collect_compiled_f64_eval_order(
    expr_index: usize,
    program: &CompiledF64ReadOnlyProgram<'_>,
    visited: &mut [bool],
    visiting: &mut [bool],
    order: &mut Vec<usize>,
) -> bool {
    let expr_index = program.aliases[expr_index];
    if visited[expr_index] {
        return true;
    }
    if visiting[expr_index] {
        return false;
    }
    visiting[expr_index] = true;
    let emit = !matches!(program.expressions[expr_index], CompiledF64Expr::Literal(_));
    let supported = match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(_)
        | CompiledF64Expr::Field(_)
        | CompiledF64Expr::SpatialAggregate(_)
        | CompiledF64Expr::ResourceField { .. }
        | CompiledF64Expr::InputState { .. } => true,
        CompiledF64Expr::ForEachItem(_) => false,
        CompiledF64Expr::Unary { input, .. } | CompiledF64Expr::Passthrough(input) => {
            collect_compiled_f64_eval_order(
                program.aliases[*input],
                program,
                visited,
                visiting,
                order,
            )
        }
        CompiledF64Expr::Binary { op, left, right } => {
            !matches!(op, F64BinaryOp::And | F64BinaryOp::Or)
                && collect_compiled_f64_eval_order(
                    program.aliases[*left],
                    program,
                    visited,
                    visiting,
                    order,
                )
                && collect_compiled_f64_eval_order(
                    program.aliases[*right],
                    program,
                    visited,
                    visiting,
                    order,
                )
        }
        CompiledF64Expr::Unsupported(_) => false,
    };
    visiting[expr_index] = false;
    if supported {
        visited[expr_index] = true;
        if emit {
            order.push(expr_index);
        }
    }
    supported
}

pub(in crate::execution) fn eval_compiled_f64_linear_order(
    order: &[usize],
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    values: &mut [f64],
) -> Result<()> {
    for expr_index in order {
        values[*expr_index] =
            eval_compiled_f64_linear_node(*expr_index, row_index, entity, program, world, values)?;
    }
    Ok(())
}

fn eval_compiled_f64_linear_node(
    expr_index: usize,
    row_index: usize,
    entity: Entity,
    program: &CompiledF64ReadOnlyProgram<'_>,
    world: &World,
    values: &[f64],
) -> Result<f64> {
    match &program.expressions[expr_index] {
        CompiledF64Expr::Literal(value) => Ok(*value),
        CompiledF64Expr::Field(slot) => {
            compiled_field_f64_value(program.field_arrays[*slot], row_index, entity)
        }
        CompiledF64Expr::SpatialAggregate(slot) => {
            compiled_spatial_f64_value(program.spatial_arrays[*slot], row_index, entity)
        }
        CompiledF64Expr::ForEachItem(slot) => Err(EcsError::InvalidPlan(format!(
            "for_each item slot {slot} is only available in row-local loop evaluation"
        ))),
        CompiledF64Expr::ResourceField { resource, field } => {
            numeric_f64(&world.resource_field(resource, field)?)
        }
        CompiledF64Expr::InputState { name, code } => numeric_f64(
            &world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name)),
        ),
        CompiledF64Expr::Unary { op, input } => {
            Ok(eval_f64_unary_op(*op, values[program.aliases[*input]]))
        }
        CompiledF64Expr::Binary { op, left, right } => Ok(eval_f64_binary_op(
            *op,
            values[program.aliases[*left]],
            values[program.aliases[*right]],
        )),
        CompiledF64Expr::Passthrough(input) => Ok(values[program.aliases[*input]]),
        CompiledF64Expr::Unsupported(message) => Err(EcsError::InvalidPlan(message.clone())),
    }
}

pub(in crate::execution) fn compiled_field_f64_value(
    array: CompiledF64Array<'_>,
    row_index: usize,
    entity: Entity,
) -> Result<f64> {
    match array {
        CompiledF64Array::QueryRows(values) => values.get(row_index).copied().ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "numeric field cache missing query row {row_index} for entity {}:{}",
                entity.index, entity.generation
            ))
        }),
        CompiledF64Array::SparseEntity(values) => values.get(&entity).copied().ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "numeric field cache missing entity {}:{}",
                entity.index, entity.generation
            ))
        }),
    }
}

pub(in crate::execution) fn compiled_spatial_f64_value(
    array: CompiledSpatialF64Array<'_>,
    row_index: usize,
    entity: Entity,
) -> Result<f64> {
    match array {
        CompiledSpatialF64Array::QueryRows(values) => {
            values.get(row_index).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial aggregate missing query row {row_index} for entity {}:{}",
                    entity.index, entity.generation
                ))
            })
        }
        CompiledSpatialF64Array::QueryRowsOptional(values) => values
            .get(row_index)
            .and_then(|value| *value)
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial aggregate missing query row {row_index} for entity {}:{}",
                    entity.index, entity.generation
                ))
            }),
        CompiledSpatialF64Array::SparseEntity(values) => {
            values.get(&entity).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial aggregate missing entity {}:{}",
                    entity.index, entity.generation
                ))
            })
        }
    }
}
