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
        AggregateKind::Sum => Ok(EcsValue::F64(0.0)),
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
        AggregateKind::Count => Ok(EcsValue::I64(count as i64)),
        AggregateKind::Sum => Ok(EcsValue::F64(numeric_sum(&values)?)),
        AggregateKind::Min => Ok(EcsValue::F64(numeric_extreme(&values, "min", f64::min)?)),
        AggregateKind::Max => Ok(EcsValue::F64(numeric_extreme(&values, "max", f64::max)?)),
        AggregateKind::Mean => {
            if values.is_empty() {
                return aggregate_empty(kind, source_name, default, executor, ctx);
            }
            let sum = numeric_sum(&values)?;
            Ok(EcsValue::F64(sum / values.len() as f64))
        }
        AggregateKind::Unknown => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{source_name}'"
        ))),
    }
}

fn numeric_sum(values: &[EcsValue]) -> Result<f64> {
    values
        .iter()
        .try_fold(0.0, |sum, value| Ok(sum + numeric_f64(value)?))
}

fn numeric_extreme(values: &[EcsValue], kind: &str, choose: fn(f64, f64) -> f64) -> Result<f64> {
    let mut iter = values.iter().map(numeric_f64);
    let mut best = iter
        .next()
        .transpose()?
        .ok_or_else(|| EcsError::InvalidPlan(format!("{kind} aggregate has no values")))?;
    for value in iter {
        best = choose(best, value?);
    }
    Ok(best)
}
