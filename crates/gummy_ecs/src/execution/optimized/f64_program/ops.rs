use crate::error::{EcsError, Result};
use crate::plan::typed_ir::{BinaryOp, UnaryOp};

use super::super::{bool_f64, truthy_f64};
use super::{F64BinaryOp, F64UnaryOp};

pub(in crate::execution) fn f64_unary_op(op: UnaryOp) -> Option<F64UnaryOp> {
    match op {
        UnaryOp::Neg => Some(F64UnaryOp::Neg),
        UnaryOp::Not => Some(F64UnaryOp::Not),
        UnaryOp::Abs => Some(F64UnaryOp::Abs),
        UnaryOp::Sqrt => Some(F64UnaryOp::Sqrt),
        UnaryOp::Sin => Some(F64UnaryOp::Sin),
        UnaryOp::Cos => Some(F64UnaryOp::Cos),
        UnaryOp::Floor => Some(F64UnaryOp::Floor),
        UnaryOp::Ceil => Some(F64UnaryOp::Ceil),
        UnaryOp::Unknown => None,
    }
}

pub(in crate::execution) fn eval_f64_unary_op(op: F64UnaryOp, input: f64) -> f64 {
    match op {
        F64UnaryOp::Neg => -input,
        F64UnaryOp::Not => bool_f64(!truthy_f64(input)),
        F64UnaryOp::Abs => input.abs(),
        F64UnaryOp::Sqrt => input.sqrt(),
        F64UnaryOp::Sin => input.sin(),
        F64UnaryOp::Cos => input.cos(),
        F64UnaryOp::Floor => input.floor(),
        F64UnaryOp::Ceil => input.ceil(),
    }
}

pub(in crate::execution) fn eval_unary_f64(
    op: UnaryOp,
    source_name: &str,
    input: f64,
) -> Result<f64> {
    f64_unary_op(op)
        .map(|op| eval_f64_unary_op(op, input))
        .ok_or_else(|| {
            EcsError::InvalidPlan(format!("unsupported physical unary op '{source_name}'"))
        })
}

pub(in crate::execution) fn f64_binary_op(op: BinaryOp) -> Option<F64BinaryOp> {
    match op {
        BinaryOp::Add => Some(F64BinaryOp::Add),
        BinaryOp::Sub => Some(F64BinaryOp::Sub),
        BinaryOp::Mul => Some(F64BinaryOp::Mul),
        BinaryOp::TrueDiv => Some(F64BinaryOp::TrueDiv),
        BinaryOp::FloorDiv => Some(F64BinaryOp::FloorDiv),
        BinaryOp::Mod => Some(F64BinaryOp::Mod),
        BinaryOp::Pow => Some(F64BinaryOp::Pow),
        BinaryOp::Lt => Some(F64BinaryOp::Lt),
        BinaryOp::Le => Some(F64BinaryOp::Le),
        BinaryOp::Gt => Some(F64BinaryOp::Gt),
        BinaryOp::Ge => Some(F64BinaryOp::Ge),
        BinaryOp::Eq => Some(F64BinaryOp::Eq),
        BinaryOp::Ne => Some(F64BinaryOp::Ne),
        BinaryOp::Min => Some(F64BinaryOp::Min),
        BinaryOp::Max => Some(F64BinaryOp::Max),
        BinaryOp::And => Some(F64BinaryOp::And),
        BinaryOp::Or => Some(F64BinaryOp::Or),
        BinaryOp::Unknown => None,
    }
}

pub(in crate::execution) fn eval_f64_binary_op(op: F64BinaryOp, left: f64, right: f64) -> f64 {
    match op {
        F64BinaryOp::Add => left + right,
        F64BinaryOp::Sub => left - right,
        F64BinaryOp::Mul => left * right,
        F64BinaryOp::TrueDiv => left / right,
        F64BinaryOp::FloorDiv => (left / right).floor(),
        F64BinaryOp::Mod => left % right,
        F64BinaryOp::Pow => left.powf(right),
        F64BinaryOp::Lt => bool_f64(left < right),
        F64BinaryOp::Le => bool_f64(left <= right),
        F64BinaryOp::Gt => bool_f64(left > right),
        F64BinaryOp::Ge => bool_f64(left >= right),
        F64BinaryOp::Eq => bool_f64(left == right),
        F64BinaryOp::Ne => bool_f64(left != right),
        F64BinaryOp::Min => left.min(right),
        F64BinaryOp::Max => left.max(right),
        F64BinaryOp::And => bool_f64(truthy_f64(left) && truthy_f64(right)),
        F64BinaryOp::Or => bool_f64(truthy_f64(left) || truthy_f64(right)),
    }
}

pub(in crate::execution) fn eval_binary_f64(
    op: BinaryOp,
    source_name: &str,
    left: f64,
    right: f64,
) -> Result<f64> {
    f64_binary_op(op)
        .map(|op| eval_f64_binary_op(op, left, right))
        .ok_or_else(|| {
            EcsError::InvalidPlan(format!("unsupported physical binary op '{source_name}'"))
        })
}
