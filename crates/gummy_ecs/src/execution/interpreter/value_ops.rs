use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::{BinaryOp, UnaryOp};
use crate::plan::ExprNode;
use crate::schema::StorageType;

pub(in crate::execution) use crate::column::coerce_value_for_storage;

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
            EcsValue::I64(value) => value
                .checked_neg()
                .map(EcsValue::I64)
                .ok_or_else(|| integer_overflow("neg")),
            EcsValue::U64(value) => {
                let value = i128::from(value)
                    .checked_neg()
                    .ok_or_else(|| integer_overflow("neg"))?;
                integer_result(value, false)
            }
            EcsValue::F64(value) => Ok(EcsValue::F64(-value)),
            other => Err(EcsError::InvalidPlan(format!(
                "unary neg expects a numeric value, got {}",
                other.kind_name()
            ))),
        },
        UnaryOp::Not => Ok(EcsValue::Bool(!truthy(&input)?)),
        UnaryOp::Abs => match input {
            EcsValue::I64(value) => value
                .checked_abs()
                .map(EcsValue::I64)
                .ok_or_else(|| integer_overflow("abs")),
            EcsValue::U64(value) => Ok(EcsValue::U64(value)),
            EcsValue::F64(value) => Ok(EcsValue::F64(value.abs())),
            other => Err(EcsError::InvalidPlan(format!(
                "abs expects a numeric value, got {}",
                other.kind_name()
            ))),
        },
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
        BinaryOp::Add => numeric_arithmetic(left, right, "add", i128::checked_add, |a, b| a + b),
        BinaryOp::Sub => numeric_arithmetic(left, right, "sub", i128::checked_sub, |a, b| a - b),
        BinaryOp::Mul => numeric_arithmetic(left, right, "mul", i128::checked_mul, |a, b| a * b),
        BinaryOp::TrueDiv => Ok(EcsValue::F64(numeric_f64(&left)? / numeric_f64(&right)?)),
        BinaryOp::FloorDiv => integer_or_float_division(left, right, true),
        BinaryOp::Mod => integer_or_float_modulo(left, right),
        BinaryOp::Pow => Ok(EcsValue::F64(
            numeric_f64(&left)?.powf(numeric_f64(&right)?),
        )),
        BinaryOp::Lt => Ok(EcsValue::Bool(compare_values(&left, &right)?.is_lt())),
        BinaryOp::Le => Ok(EcsValue::Bool(!compare_values(&left, &right)?.is_gt())),
        BinaryOp::Gt => Ok(EcsValue::Bool(compare_values(&left, &right)?.is_gt())),
        BinaryOp::Ge => Ok(EcsValue::Bool(!compare_values(&left, &right)?.is_lt())),
        BinaryOp::Eq => Ok(EcsValue::Bool(values_equal(&left, &right)?)),
        BinaryOp::Ne => Ok(EcsValue::Bool(!values_equal(&left, &right)?)),
        BinaryOp::Min => Ok(if compare_values(&left, &right)?.is_le() {
            left
        } else {
            right
        }),
        BinaryOp::Max => Ok(if compare_values(&left, &right)?.is_ge() {
            left
        } else {
            right
        }),
        BinaryOp::And | BinaryOp::Or | BinaryOp::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported physical binary op '{source_name}'"
        ))),
    }
}

fn integer_overflow(operation: &str) -> EcsError {
    EcsError::InvalidPlan(format!(
        "checked ECS integer {operation} overflowed its 64-bit transport domain"
    ))
}

fn integer_parts(value: &EcsValue) -> Option<(i128, bool)> {
    match value {
        EcsValue::I64(value) => Some((i128::from(*value), false)),
        EcsValue::U64(value) => Some((i128::from(*value), true)),
        _ => None,
    }
}

fn integer_result(value: i128, prefer_unsigned: bool) -> Result<EcsValue> {
    if value < 0 || !prefer_unsigned {
        return i64::try_from(value)
            .map(EcsValue::I64)
            .map_err(|_| integer_overflow("operation"));
    }
    u64::try_from(value)
        .map(EcsValue::U64)
        .map_err(|_| integer_overflow("operation"))
}

fn numeric_arithmetic(
    left: EcsValue,
    right: EcsValue,
    operation: &str,
    integer_op: fn(i128, i128) -> Option<i128>,
    float_op: fn(f64, f64) -> f64,
) -> Result<EcsValue> {
    if let (Some((left_value, left_unsigned)), Some((right_value, right_unsigned))) =
        (integer_parts(&left), integer_parts(&right))
    {
        let value =
            integer_op(left_value, right_value).ok_or_else(|| integer_overflow(operation))?;
        return integer_result(value, left_unsigned || right_unsigned);
    }
    Ok(EcsValue::F64(float_op(
        numeric_f64(&left)?,
        numeric_f64(&right)?,
    )))
}

fn integer_or_float_division(left: EcsValue, right: EcsValue, floor: bool) -> Result<EcsValue> {
    if let (Some((left_value, left_unsigned)), Some((right_value, right_unsigned))) =
        (integer_parts(&left), integer_parts(&right))
    {
        if right_value == 0 {
            return Err(EcsError::InvalidPlan(
                "ECS integer floor division by zero".to_string(),
            ));
        }
        let quotient = left_value / right_value;
        let remainder = left_value % right_value;
        let quotient = if floor && remainder != 0 && (remainder < 0) != (right_value < 0) {
            quotient - 1
        } else {
            quotient
        };
        return integer_result(quotient, left_unsigned && right_unsigned);
    }
    Ok(EcsValue::F64(
        (numeric_f64(&left)? / numeric_f64(&right)?).floor(),
    ))
}

fn integer_or_float_modulo(left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    if let (Some((left_value, left_unsigned)), Some((right_value, right_unsigned))) =
        (integer_parts(&left), integer_parts(&right))
    {
        if right_value == 0 {
            return Err(EcsError::InvalidPlan(
                "ECS integer modulo by zero".to_string(),
            ));
        }
        let remainder = left_value % right_value;
        let remainder = if remainder != 0 && (remainder < 0) != (right_value < 0) {
            remainder + right_value
        } else {
            remainder
        };
        return integer_result(remainder, left_unsigned && right_unsigned);
    }
    Ok(EcsValue::F64(numeric_f64(&left)? % numeric_f64(&right)?))
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

fn compare_values(left: &EcsValue, right: &EcsValue) -> Result<std::cmp::Ordering> {
    if let (Some((left, _)), Some((right, _))) = (integer_parts(left), integer_parts(right)) {
        return Ok(left.cmp(&right));
    }
    numeric_f64(left)?
        .partial_cmp(&numeric_f64(right)?)
        .ok_or_else(|| EcsError::InvalidPlan("cannot compare NaN ECS values".to_string()))
}

fn values_equal(left: &EcsValue, right: &EcsValue) -> Result<bool> {
    match (left, right) {
        (EcsValue::Bool(left), EcsValue::Bool(right)) => Ok(left == right),
        (EcsValue::String(left), EcsValue::String(right)) => Ok(left == right),
        (EcsValue::I64(_) | EcsValue::U64(_), EcsValue::I64(_) | EcsValue::U64(_)) => {
            Ok(integer_parts(left).map(|value| value.0)
                == integer_parts(right).map(|value| value.0))
        }
        (
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
        ) => Ok(numeric_f64(left)? == numeric_f64(right)?),
        _ => Ok(left == right),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integer_arithmetic_remains_exact_above_f64_integer_precision() {
        let value = 9_007_199_254_740_993_i64;
        assert_eq!(
            eval_binary(BinaryOp::Add, "add", EcsValue::I64(value), EcsValue::I64(2),).unwrap(),
            EcsValue::I64(value + 2)
        );
        assert_eq!(
            eval_binary(BinaryOp::Mod, "mod", EcsValue::I64(-5), EcsValue::I64(3),).unwrap(),
            EcsValue::I64(1)
        );
    }

    #[test]
    fn checked_integer_transport_overflow_is_an_execution_error() {
        assert!(eval_binary(
            BinaryOp::Add,
            "add",
            EcsValue::I64(i64::MAX),
            EcsValue::I64(1),
        )
        .is_err());
    }
}
