use crate::error::{EcsError, Result};

use super::super::{bool_f64, truthy_f64};
use super::{F64BinaryOp, F64UnaryOp};

pub(in crate::execution) fn f64_unary_op(op: &str) -> Option<F64UnaryOp> {
    match op {
        "neg" | "-" => Some(F64UnaryOp::Neg),
        "not" | "!" => Some(F64UnaryOp::Not),
        "abs" => Some(F64UnaryOp::Abs),
        "sqrt" => Some(F64UnaryOp::Sqrt),
        "sin" => Some(F64UnaryOp::Sin),
        "cos" => Some(F64UnaryOp::Cos),
        "floor" => Some(F64UnaryOp::Floor),
        "ceil" => Some(F64UnaryOp::Ceil),
        _ => None,
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

pub(in crate::execution) fn eval_unary_f64(op: &str, input: f64) -> Result<f64> {
    f64_unary_op(op)
        .map(|op| eval_f64_unary_op(op, input))
        .ok_or_else(|| EcsError::InvalidPlan(format!("unsupported physical unary op '{op}'")))
}

pub(in crate::execution) fn f64_binary_op(op: &str) -> Option<F64BinaryOp> {
    match op {
        "add" | "+" => Some(F64BinaryOp::Add),
        "sub" | "-" => Some(F64BinaryOp::Sub),
        "mul" | "*" => Some(F64BinaryOp::Mul),
        "truediv" | "/" => Some(F64BinaryOp::TrueDiv),
        "floordiv" | "//" => Some(F64BinaryOp::FloorDiv),
        "mod" | "%" => Some(F64BinaryOp::Mod),
        "pow" | "**" => Some(F64BinaryOp::Pow),
        "lt" | "<" => Some(F64BinaryOp::Lt),
        "le" | "<=" => Some(F64BinaryOp::Le),
        "gt" | ">" => Some(F64BinaryOp::Gt),
        "ge" | ">=" => Some(F64BinaryOp::Ge),
        "eq" | "==" => Some(F64BinaryOp::Eq),
        "ne" | "!=" => Some(F64BinaryOp::Ne),
        "min" => Some(F64BinaryOp::Min),
        "max" => Some(F64BinaryOp::Max),
        "and" | "&&" => Some(F64BinaryOp::And),
        "or" | "||" => Some(F64BinaryOp::Or),
        _ => None,
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

pub(in crate::execution) fn eval_binary_f64(op: &str, left: f64, right: f64) -> Result<f64> {
    f64_binary_op(op)
        .map(|op| eval_f64_binary_op(op, left, right))
        .ok_or_else(|| EcsError::InvalidPlan(format!("unsupported physical binary op '{op}'")))
}
