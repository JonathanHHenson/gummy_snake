use crate::column::EcsValue;
use crate::error::{EcsError, Result};

use super::{ActionNode, BridgePlanPayload, ExprNode, PhysicalPlan};

pub(super) fn optimize_bridge_payload(mut payload: BridgePlanPayload) -> BridgePlanPayload {
    for query in &mut payload.queries {
        query.terms.sort();
        query.terms.dedup();
        if let Some(allowed) = &mut query.allowed_entities {
            allowed.sort_by_key(|entity| entity.raw());
            allowed.dedup_by_key(|entity| entity.raw());
        }
    }
    payload
}

pub(super) fn optimize_physical_plan(mut plan: PhysicalPlan) -> Result<PhysicalPlan> {
    fold_constant_expressions(&mut plan.expressions)?;
    simplify_actions(&mut plan.actions, plan.root_action)?;
    Ok(plan)
}

fn fold_constant_expressions(expressions: &mut [ExprNode]) -> Result<()> {
    for index in 0..expressions.len() {
        let folded = match expressions[index].clone() {
            ExprNode::Unary { op, input } => literal_expr_value(expressions.get(input))
                .map(|value| fold_unary_literal(&op, value))
                .transpose()?,
            ExprNode::Binary { op, left, right } => {
                match (
                    literal_expr_value(expressions.get(left)),
                    literal_expr_value(expressions.get(right)),
                ) {
                    (Some(left), Some(right)) => Some(fold_binary_literal(&op, left, right)?),
                    _ => None,
                }
            }
            ExprNode::Attribute { input, attribute } => literal_expr_value(expressions.get(input))
                .and_then(|value| fold_attribute_literal(value, &attribute)),
            _ => None,
        };
        if let Some(value) = folded {
            expressions[index] = expr_from_value(value);
        }
    }
    Ok(())
}

fn literal_expr_value(expr: Option<&ExprNode>) -> Option<EcsValue> {
    match expr? {
        ExprNode::LiteralF64(value) => Some(EcsValue::F64(*value)),
        ExprNode::LiteralI64(value) => Some(EcsValue::I64(*value)),
        ExprNode::LiteralBool(value) => Some(EcsValue::Bool(*value)),
        ExprNode::LiteralString(value) => Some(EcsValue::String(value.clone())),
        ExprNode::LiteralValue(value) => Some(value.clone()),
        _ => None,
    }
}

fn expr_from_value(value: EcsValue) -> ExprNode {
    match value {
        EcsValue::F64(value) => ExprNode::LiteralF64(value),
        EcsValue::I64(value) => ExprNode::LiteralI64(value),
        EcsValue::Bool(value) => ExprNode::LiteralBool(value),
        EcsValue::String(value) => ExprNode::LiteralString(value),
        value => ExprNode::LiteralValue(value),
    }
}

fn fold_unary_literal(op: &str, value: EcsValue) -> Result<EcsValue> {
    match op {
        "not" => Ok(EcsValue::Bool(!truthy_literal(&value)?)),
        "neg" | "-" => Ok(EcsValue::F64(-numeric_literal_f64(&value)?)),
        "pos" | "+" => Ok(EcsValue::F64(numeric_literal_f64(&value)?)),
        "abs" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.abs())),
        "sqrt" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.sqrt())),
        "sin" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.sin())),
        "cos" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.cos())),
        "floor" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.floor())),
        "ceil" => Ok(EcsValue::F64(numeric_literal_f64(&value)?.ceil())),
        _ => Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported unary op {op}"
        ))),
    }
}

fn fold_binary_literal(op: &str, left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    match op {
        "and" => Ok(EcsValue::Bool(
            truthy_literal(&left)? && truthy_literal(&right)?,
        )),
        "or" => Ok(EcsValue::Bool(
            truthy_literal(&left)? || truthy_literal(&right)?,
        )),
        "add" | "+" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? + numeric_literal_f64(&right)?,
        )),
        "sub" | "-" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? - numeric_literal_f64(&right)?,
        )),
        "mul" | "*" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? * numeric_literal_f64(&right)?,
        )),
        "truediv" | "/" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? / numeric_literal_f64(&right)?,
        )),
        "floordiv" | "//" => Ok(EcsValue::F64(
            (numeric_literal_f64(&left)? / numeric_literal_f64(&right)?).floor(),
        )),
        "mod" | "%" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? % numeric_literal_f64(&right)?,
        )),
        "pow" | "**" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.powf(numeric_literal_f64(&right)?),
        )),
        "lt" | "<" => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? < numeric_literal_f64(&right)?,
        )),
        "le" | "<=" => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? <= numeric_literal_f64(&right)?,
        )),
        "gt" | ">" => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? > numeric_literal_f64(&right)?,
        )),
        "ge" | ">=" => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? >= numeric_literal_f64(&right)?,
        )),
        "eq" | "==" => Ok(EcsValue::Bool(left == right)),
        "ne" | "!=" => Ok(EcsValue::Bool(left != right)),
        "min" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.min(numeric_literal_f64(&right)?),
        )),
        "max" => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.max(numeric_literal_f64(&right)?),
        )),
        _ => Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported binary op {op}"
        ))),
    }
}

fn fold_attribute_literal(value: EcsValue, attribute: &str) -> Option<EcsValue> {
    match (value, attribute) {
        (EcsValue::Struct(fields), name) => fields.get(name).cloned(),
        (EcsValue::Vec2F64(value), "x") => Some(EcsValue::F64(value[0])),
        (EcsValue::Vec2F64(value), "y") => Some(EcsValue::F64(value[1])),
        (EcsValue::Vec3F64(value), "x") => Some(EcsValue::F64(value[0])),
        (EcsValue::Vec3F64(value), "y") => Some(EcsValue::F64(value[1])),
        (EcsValue::Vec3F64(value), "z") => Some(EcsValue::F64(value[2])),
        _ => None,
    }
}

fn numeric_literal_f64(value: &EcsValue) -> Result<f64> {
    match value {
        EcsValue::F64(value) => Ok(*value),
        EcsValue::I64(value) => Ok(*value as f64),
        EcsValue::U64(value) => Ok(*value as f64),
        EcsValue::Bool(value) => Ok(if *value { 1.0 } else { 0.0 }),
        other => Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold non-numeric literal {}",
            other.kind_name()
        ))),
    }
}

fn truthy_literal(value: &EcsValue) -> Result<bool> {
    match value {
        EcsValue::Bool(value) => Ok(*value),
        EcsValue::I64(value) => Ok(*value != 0),
        EcsValue::U64(value) => Ok(*value != 0),
        EcsValue::F64(value) => Ok(*value != 0.0),
        other => Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold boolean op for literal {}",
            other.kind_name()
        ))),
    }
}

fn simplify_actions(actions: &mut [ActionNode], root_action: usize) -> Result<()> {
    for index in 0..actions.len() {
        let simplified = match actions[index].clone() {
            ActionNode::Sequence(children) => {
                let children = children
                    .into_iter()
                    .filter(|child| !matches!(actions.get(*child), Some(ActionNode::Noop)))
                    .collect::<Vec<_>>();
                match children.as_slice() {
                    [] => Some(ActionNode::Noop),
                    [child] if index != root_action => actions.get(*child).cloned(),
                    _ => Some(ActionNode::Sequence(children)),
                }
            }
            ActionNode::Parallel(children) => {
                let children = children
                    .into_iter()
                    .filter(|child| !matches!(actions.get(*child), Some(ActionNode::Noop)))
                    .collect::<Vec<_>>();
                match children.as_slice() {
                    [] => Some(ActionNode::Noop),
                    [child] if index != root_action => actions.get(*child).cloned(),
                    _ => Some(ActionNode::Parallel(children)),
                }
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => Some(ActionNode::When {
                condition,
                then_action,
                otherwise_action: otherwise_action
                    .filter(|child| !matches!(actions.get(*child), Some(ActionNode::Noop))),
            }),
            _ => None,
        };
        if let Some(action) = simplified {
            actions[index] = action;
        }
    }
    Ok(())
}
