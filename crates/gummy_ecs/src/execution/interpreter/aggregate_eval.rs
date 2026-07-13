use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::AggregateKind;

use super::super::{EvalContext, PlanExecutor};
use super::value_ops::numeric_f64;

pub(in crate::execution) fn aggregate_empty(
    kind: AggregateKind,
    source_name: &str,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if let Some(default_expr) = default {
        return executor.eval_expr(default_expr, ctx);
    }
    match kind {
        AggregateKind::Any => Ok(EcsValue::Bool(false)),
        AggregateKind::Count => Ok(EcsValue::I64(0)),
        AggregateKind::Sum => Ok(EcsValue::I64(0)),
        AggregateKind::Min | AggregateKind::Max | AggregateKind::Mean => {
            Err(EcsError::InvalidPlan(format!(
                "{source_name} aggregate is empty and no default was provided"
            )))
        }
        AggregateKind::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{source_name}'"
        ))),
    }
}

pub(in crate::execution) fn aggregate_finish(
    kind: AggregateKind,
    source_name: &str,
    count: usize,
    values: Vec<EcsValue>,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if count == 0
        && matches!(
            kind,
            AggregateKind::Min | AggregateKind::Max | AggregateKind::Mean
        )
    {
        return aggregate_empty(kind, source_name, default, executor, ctx);
    }
    match kind {
        AggregateKind::Any => Ok(EcsValue::Bool(count > 0)),
        AggregateKind::Count => i64::try_from(count)
            .map(EcsValue::I64)
            .map_err(|_| EcsError::InvalidPlan("ECS count aggregate overflowed Int64".to_string())),
        AggregateKind::Sum => numeric_sum(&values),
        AggregateKind::Min => numeric_extreme(&values, "min", std::cmp::Ordering::Less),
        AggregateKind::Max => numeric_extreme(&values, "max", std::cmp::Ordering::Greater),
        AggregateKind::Mean => {
            if values.is_empty() {
                return aggregate_empty(kind, source_name, default, executor, ctx);
            }
            let sum = values
                .iter()
                .try_fold(0.0, |sum, value| Ok(sum + numeric_f64(value)?))?;
            Ok(EcsValue::F64(sum / values.len() as f64))
        }
        AggregateKind::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{source_name}'"
        ))),
    }
}

fn integer_part(value: &EcsValue) -> Option<(i128, bool)> {
    match value {
        EcsValue::I64(value) => Some((i128::from(*value), false)),
        EcsValue::U64(value) => Some((i128::from(*value), true)),
        _ => None,
    }
}

fn integer_result(value: i128, unsigned: bool, aggregate: &str) -> Result<EcsValue> {
    if unsigned && value >= 0 {
        return u64::try_from(value).map(EcsValue::U64).map_err(|_| {
            EcsError::InvalidPlan(format!("ECS {aggregate} aggregate overflowed UInt64"))
        });
    }
    i64::try_from(value)
        .map(EcsValue::I64)
        .map_err(|_| EcsError::InvalidPlan(format!("ECS {aggregate} aggregate overflowed Int64")))
}

fn numeric_sum(values: &[EcsValue]) -> Result<EcsValue> {
    if values.iter().all(|value| integer_part(value).is_some()) {
        let mut sum = 0_i128;
        let mut unsigned = false;
        for value in values {
            let (part, part_unsigned) = integer_part(value).expect("checked integer aggregate");
            sum = sum
                .checked_add(part)
                .ok_or_else(|| EcsError::InvalidPlan("ECS sum aggregate overflowed".to_string()))?;
            unsigned |= part_unsigned;
        }
        return integer_result(sum, unsigned, "sum");
    }
    values
        .iter()
        .try_fold(0.0, |sum, value| Ok(sum + numeric_f64(value)?))
        .map(EcsValue::F64)
}

fn numeric_extreme(
    values: &[EcsValue],
    kind: &str,
    wanted: std::cmp::Ordering,
) -> Result<EcsValue> {
    let mut iter = values.iter();
    let mut best = iter
        .next()
        .cloned()
        .ok_or_else(|| EcsError::InvalidPlan(format!("{kind} aggregate has no values")))?;
    for value in iter {
        let ordering = match (integer_part(&best), integer_part(value)) {
            (Some((left, _)), Some((right, _))) => left.cmp(&right),
            _ => numeric_f64(&best)?
                .partial_cmp(&numeric_f64(value)?)
                .ok_or_else(|| {
                    EcsError::InvalidPlan("cannot aggregate NaN ECS values".to_string())
                })?,
        };
        if ordering == wanted {
            continue;
        }
        if ordering != std::cmp::Ordering::Equal {
            best = value.clone();
        }
    }
    Ok(best)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integer_sum_does_not_round_through_f64() {
        let values = [EcsValue::I64(9_007_199_254_740_993), EcsValue::I64(2)];
        assert_eq!(
            numeric_sum(&values).unwrap(),
            EcsValue::I64(9_007_199_254_740_995)
        );
    }
}
