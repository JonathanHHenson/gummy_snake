use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::execution::interpreter::value_ops::{eval_binary, eval_unary};

use super::typed_ir::{BinaryOp, UnaryOp};
use super::{ActionNode, BridgePlanPayload, ExprNode, PhysicalPlan};

pub(super) fn optimize_bridge_payload(mut payload: BridgePlanPayload) -> BridgePlanPayload {
    for query in &mut payload.queries {
        query.terms.sort();
        query.terms.dedup();
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
    if matches!(op, "pos" | "+") {
        return match value {
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_) => Ok(value),
            other => Err(EcsError::InvalidPlan(format!(
                "cannot constant-fold unary pos for literal {}",
                other.kind_name()
            ))),
        };
    }
    eval_unary(UnaryOp::parse(op), op, value)
}

fn fold_binary_literal(op: &str, left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    // Preserve the historical folder boundary: symbolic boolean aliases are
    // executable but were not folded by the version-2 optimizer.
    if matches!(op, "&&" | "||") {
        return Err(EcsError::InvalidPlan(format!(
            "cannot constant-fold unsupported binary op {op}"
        )));
    }
    eval_binary(BinaryOp::parse(op), op, left, right)
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn constant_folding_preserves_exact_integer_values_and_overflow_errors() {
        let value = 9_007_199_254_740_993_i64;
        let mut expressions = vec![
            ExprNode::LiteralI64(value),
            ExprNode::LiteralI64(2),
            ExprNode::Binary {
                op: "add".to_string(),
                left: 0,
                right: 1,
            },
        ];
        fold_constant_expressions(&mut expressions).unwrap();
        assert_eq!(expressions[2], ExprNode::LiteralI64(value + 2));

        let mut overflowing = vec![
            ExprNode::LiteralI64(i64::MAX),
            ExprNode::LiteralI64(1),
            ExprNode::Binary {
                op: "add".to_string(),
                left: 0,
                right: 1,
            },
        ];
        assert!(fold_constant_expressions(&mut overflowing).is_err());
    }
}
