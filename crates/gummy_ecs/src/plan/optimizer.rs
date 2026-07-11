use crate::column::EcsValue;
use crate::error::{EcsError, Result};

use super::typed_ir::{BinaryOp, UnaryOp};
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
    // Preserve the historical folder boundary: `!` is executable but was not
    // a constant-folding spelling in version-2 plans.
    if op == "!" {
        return Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported unary op {op}"
        )));
    }
    match UnaryOp::parse(op) {
        UnaryOp::Not => Ok(EcsValue::Bool(!truthy_literal(&value)?)),
        UnaryOp::Neg => Ok(EcsValue::F64(-numeric_literal_f64(&value)?)),
        UnaryOp::Abs => Ok(EcsValue::F64(numeric_literal_f64(&value)?.abs())),
        UnaryOp::Sqrt => Ok(EcsValue::F64(numeric_literal_f64(&value)?.sqrt())),
        UnaryOp::Sin => Ok(EcsValue::F64(numeric_literal_f64(&value)?.sin())),
        UnaryOp::Cos => Ok(EcsValue::F64(numeric_literal_f64(&value)?.cos())),
        UnaryOp::Floor => Ok(EcsValue::F64(numeric_literal_f64(&value)?.floor())),
        UnaryOp::Ceil => Ok(EcsValue::F64(numeric_literal_f64(&value)?.ceil())),
        // `pos` was historically accepted only by constant folding. Retain
        // that wire behaviour without treating it as an executable unary op.
        _ if matches!(op, "pos" | "+") => Ok(EcsValue::F64(numeric_literal_f64(&value)?)),
        UnaryOp::Unknown => Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported unary op {op}"
        ))),
    }
}

fn fold_binary_literal(op: &str, left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    // Preserve the historical folder boundary: symbolic boolean aliases are
    // executable but were not folded by the version-2 optimizer.
    if matches!(op, "&&" | "||") {
        return Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported binary op {op}"
        )));
    }
    match BinaryOp::parse(op) {
        BinaryOp::And => Ok(EcsValue::Bool(
            truthy_literal(&left)? && truthy_literal(&right)?,
        )),
        BinaryOp::Or => Ok(EcsValue::Bool(
            truthy_literal(&left)? || truthy_literal(&right)?,
        )),
        BinaryOp::Add => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? + numeric_literal_f64(&right)?,
        )),
        BinaryOp::Sub => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? - numeric_literal_f64(&right)?,
        )),
        BinaryOp::Mul => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? * numeric_literal_f64(&right)?,
        )),
        BinaryOp::TrueDiv => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? / numeric_literal_f64(&right)?,
        )),
        BinaryOp::FloorDiv => Ok(EcsValue::F64(
            (numeric_literal_f64(&left)? / numeric_literal_f64(&right)?).floor(),
        )),
        BinaryOp::Mod => Ok(EcsValue::F64(
            numeric_literal_f64(&left)? % numeric_literal_f64(&right)?,
        )),
        BinaryOp::Pow => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.powf(numeric_literal_f64(&right)?),
        )),
        BinaryOp::Lt => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? < numeric_literal_f64(&right)?,
        )),
        BinaryOp::Le => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? <= numeric_literal_f64(&right)?,
        )),
        BinaryOp::Gt => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? > numeric_literal_f64(&right)?,
        )),
        BinaryOp::Ge => Ok(EcsValue::Bool(
            numeric_literal_f64(&left)? >= numeric_literal_f64(&right)?,
        )),
        BinaryOp::Eq => Ok(EcsValue::Bool(left == right)),
        BinaryOp::Ne => Ok(EcsValue::Bool(left != right)),
        BinaryOp::Min => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.min(numeric_literal_f64(&right)?),
        )),
        BinaryOp::Max => Ok(EcsValue::F64(
            numeric_literal_f64(&left)?.max(numeric_literal_f64(&right)?),
        )),
        BinaryOp::Unknown => Err(EcsError::InvalidPlan(format!(
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
