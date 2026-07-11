use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::{BinaryOp, UnaryOp};
use crate::plan::ExprNode;
use crate::schema::StorageType;

pub(in crate::execution) fn bool_f64(value: bool) -> f64 {
    if value {
        1.0
    } else {
        0.0
    }
}

pub(in crate::execution) fn truthy_f64(value: f64) -> bool {
    value != 0.0
}

pub(in crate::execution) fn storage_type_is_numeric(storage_type: StorageType) -> bool {
    matches!(
        storage_type,
        StorageType::Bool
            | StorageType::Int8
            | StorageType::Int16
            | StorageType::Int32
            | StorageType::Int64
            | StorageType::UInt8
            | StorageType::UInt16
            | StorageType::UInt32
            | StorageType::UInt64
            | StorageType::Float32
            | StorageType::Float64
    )
}

pub(in crate::execution) fn eval_unary(
    op: UnaryOp,
    source_name: &str,
    input: EcsValue,
) -> Result<EcsValue> {
    match op {
        UnaryOp::Neg => match input {
            EcsValue::I64(value) => Ok(EcsValue::I64(-value)),
            EcsValue::U64(value) => Ok(EcsValue::I64(-(value as i64))),
            EcsValue::F64(value) => Ok(EcsValue::F64(-value)),
            other => Err(EcsError::InvalidPlan(format!(
                "unary neg expects a numeric value, got {}",
                other.kind_name()
            ))),
        },
        UnaryOp::Not => Ok(EcsValue::Bool(!truthy(&input)?)),
        UnaryOp::Abs => Ok(EcsValue::F64(numeric_f64(&input)?.abs())),
        UnaryOp::Sqrt => Ok(EcsValue::F64(numeric_f64(&input)?.sqrt())),
        UnaryOp::Sin => Ok(EcsValue::F64(numeric_f64(&input)?.sin())),
        UnaryOp::Cos => Ok(EcsValue::F64(numeric_f64(&input)?.cos())),
        UnaryOp::Floor => Ok(EcsValue::F64(numeric_f64(&input)?.floor())),
        UnaryOp::Ceil => Ok(EcsValue::F64(numeric_f64(&input)?.ceil())),
        UnaryOp::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported physical unary op '{source_name}'"
        ))),
    }
}

pub(in crate::execution) fn default_input_state_value(name: &str) -> EcsValue {
    match name {
        "dt" | "delta_time" => EcsValue::F64(0.0),
        "key_down" => EcsValue::Bool(false),
        _ => EcsValue::Bool(false),
    }
}

pub(in crate::execution) fn eval_binary(
    op: BinaryOp,
    source_name: &str,
    left: EcsValue,
    right: EcsValue,
) -> Result<EcsValue> {
    match op {
        BinaryOp::Add => numeric_arithmetic(left, right, |a, b| a + b),
        BinaryOp::Sub => numeric_arithmetic(left, right, |a, b| a - b),
        BinaryOp::Mul => numeric_arithmetic(left, right, |a, b| a * b),
        BinaryOp::TrueDiv => Ok(EcsValue::F64(numeric_f64(&left)? / numeric_f64(&right)?)),
        BinaryOp::FloorDiv => Ok(EcsValue::F64(
            (numeric_f64(&left)? / numeric_f64(&right)?).floor(),
        )),
        BinaryOp::Mod => Ok(EcsValue::F64(numeric_f64(&left)? % numeric_f64(&right)?)),
        BinaryOp::Pow => Ok(EcsValue::F64(
            numeric_f64(&left)?.powf(numeric_f64(&right)?),
        )),
        BinaryOp::Lt => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a < b)?)),
        BinaryOp::Le => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a <= b
        })?)),
        BinaryOp::Gt => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a > b)?)),
        BinaryOp::Ge => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a >= b
        })?)),
        BinaryOp::Eq => Ok(EcsValue::Bool(values_equal(&left, &right)?)),
        BinaryOp::Ne => Ok(EcsValue::Bool(!values_equal(&left, &right)?)),
        BinaryOp::Min => Ok(if numeric_f64(&left)? <= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        BinaryOp::Max => Ok(if numeric_f64(&left)? >= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        BinaryOp::And | BinaryOp::Or | BinaryOp::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported physical binary op '{source_name}'"
        ))),
    }
}

fn numeric_arithmetic(
    left: EcsValue,
    right: EcsValue,
    op: impl FnOnce(f64, f64) -> f64,
) -> Result<EcsValue> {
    Ok(EcsValue::F64(op(numeric_f64(&left)?, numeric_f64(&right)?)))
}

pub(in crate::execution) fn literal_expr_numeric(expr: &ExprNode) -> Option<f64> {
    match expr {
        ExprNode::LiteralF64(value) => Some(*value),
        ExprNode::LiteralI64(value) => Some(*value as f64),
        ExprNode::LiteralBool(value) => Some(if *value { 1.0 } else { 0.0 }),
        ExprNode::LiteralValue(value) => numeric_f64(value).ok(),
        _ => None,
    }
}

pub(in crate::execution) fn numeric_f64(value: &EcsValue) -> Result<f64> {
    match value {
        EcsValue::Bool(value) => Ok(if *value { 1.0 } else { 0.0 }),
        EcsValue::I64(value) => Ok(*value as f64),
        EcsValue::U64(value) => Ok(*value as f64),
        EcsValue::F64(value) => Ok(*value),
        other => Err(EcsError::InvalidPlan(format!(
            "expected numeric ECS value, got {}",
            other.kind_name()
        ))),
    }
}

pub(in crate::execution) fn truthy(value: &EcsValue) -> Result<bool> {
    match value {
        EcsValue::Bool(value) => Ok(*value),
        EcsValue::I64(value) => Ok(*value != 0),
        EcsValue::U64(value) => Ok(*value != 0),
        EcsValue::F64(value) => Ok(*value != 0.0),
        other => Err(EcsError::InvalidPlan(format!(
            "expected boolean-compatible ECS value, got {}",
            other.kind_name()
        ))),
    }
}

fn compare_values(
    left: &EcsValue,
    right: &EcsValue,
    op: impl FnOnce(f64, f64) -> bool,
) -> Result<bool> {
    Ok(op(numeric_f64(left)?, numeric_f64(right)?))
}

fn values_equal(left: &EcsValue, right: &EcsValue) -> Result<bool> {
    match (left, right) {
        (EcsValue::Bool(left), EcsValue::Bool(right)) => Ok(left == right),
        (EcsValue::String(left), EcsValue::String(right)) => Ok(left == right),
        (
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
        ) => Ok(numeric_f64(left)? == numeric_f64(right)?),
        _ => Ok(left == right),
    }
}

pub(in crate::execution) fn coerce_value_for_storage(
    storage_type: StorageType,
    value: EcsValue,
) -> Result<EcsValue> {
    match storage_type {
        StorageType::Bool => match value {
            EcsValue::Bool(value) => Ok(EcsValue::Bool(value)),
            other => Err(type_mismatch("Bool", other)),
        },
        StorageType::Int8 | StorageType::Int16 | StorageType::Int32 | StorageType::Int64 => {
            match value {
                EcsValue::I64(value) => Ok(EcsValue::I64(value)),
                EcsValue::U64(value) if value <= i64::MAX as u64 => Ok(EcsValue::I64(value as i64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= i64::MIN as f64
                        && value <= i64::MAX as f64 =>
                {
                    Ok(EcsValue::I64(value as i64))
                }
                other => Err(type_mismatch("I64", other)),
            }
        }
        StorageType::UInt8 | StorageType::UInt16 | StorageType::UInt32 | StorageType::UInt64 => {
            match value {
                EcsValue::U64(value) => Ok(EcsValue::U64(value)),
                EcsValue::I64(value) if value >= 0 => Ok(EcsValue::U64(value as u64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= 0.0
                        && value <= u64::MAX as f64 =>
                {
                    Ok(EcsValue::U64(value as u64))
                }
                other => Err(type_mismatch("U64", other)),
            }
        }
        StorageType::Float32 | StorageType::Float64 => match value {
            EcsValue::F64(value) => Ok(EcsValue::F64(value)),
            EcsValue::I64(value) => Ok(EcsValue::F64(value as f64)),
            EcsValue::U64(value) => Ok(EcsValue::F64(value as f64)),
            other => Err(type_mismatch("F64", other)),
        },
        StorageType::String | StorageType::CategoricalString => match value {
            EcsValue::String(value) => Ok(EcsValue::String(value)),
            other => Err(type_mismatch("String", other)),
        },
        StorageType::Vec2F32 => match value {
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F32(value)),
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F32([value[0] as f32, value[1] as f32])),
            other => Err(type_mismatch("Vec2F32", other)),
        },
        StorageType::Vec2F64 => match value {
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F64(value)),
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F64([value[0] as f64, value[1] as f64])),
            other => Err(type_mismatch("Vec2F64", other)),
        },
        StorageType::Vec3F32 => match value {
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F32(value)),
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F32([
                value[0] as f32,
                value[1] as f32,
                value[2] as f32,
            ])),
            other => Err(type_mismatch("Vec3F32", other)),
        },
        StorageType::Vec3F64 => match value {
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F64(value)),
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F64([
                value[0] as f64,
                value[1] as f64,
                value[2] as f64,
            ])),
            other => Err(type_mismatch("Vec3F64", other)),
        },
        StorageType::List => match value {
            EcsValue::List(value) => Ok(EcsValue::List(value)),
            other => Err(type_mismatch("List", other)),
        },
    }
}

fn type_mismatch(expected: &'static str, value: EcsValue) -> EcsError {
    EcsError::ColumnTypeMismatch {
        expected,
        got: value.kind_name(),
    }
}
