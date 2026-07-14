//! Physical-plan execution hub.
//!
//! Generic interpretation lives in [`interpreter`], specialized numeric and
//! parallel paths live in [`optimized`], and row-local/spatial fast paths keep
//! their independent packages. `PlanExecutor` deliberately retains a flat
//! field layout: its query, evaluation-cache, spatial-cache, and profiling
//! fields share one allocation-free lifetime-bound executor state.

#[cfg(test)]
use std::collections::HashMap;

#[cfg(test)]
use crate::column::EcsValue;
#[cfg(test)]
use crate::entity::Entity;
#[cfg(test)]
use crate::plan::{ActionNode, BridgePlanPayload, ExprNode, SpatialRelationNode};
#[cfg(test)]
use crate::schema::StorageType;

#[cfg(test)]
use crate::world::World;

mod access_analysis;
mod executor;
pub(crate) mod interpreter;
mod optimized;
mod report;
mod row_local;
mod spatial;
mod typed_ir;

pub(in crate::execution) use self::executor::{
    DirectF64SetSpec, EvalContext, ExprCacheKey, PlanExecutor, QueryIndices, QueryLocationCache,
    QueryRows, WriteKey,
};
pub(in crate::execution) use self::interpreter::value_ops::{
    bool_f64, default_input_state_value, numeric_f64, storage_type_is_numeric, truthy, truthy_f64,
};
pub use self::report::{
    ExecutionCanvasCommand, ExecutionCanvasFillBatch, ExecutionCanvasFillKind,
    ExecutionCanvasFillRecord, ExecutionEvent, ExecutionReport, ExecutionWrite,
};
#[allow(unused_imports)]
pub(in crate::execution) use self::spatial::support as spatial_support;
#[allow(unused_imports)]
pub(crate) use self::spatial::support::{BuiltSpatialIndex, CachedSpatialIndex};
#[allow(unused_imports)]
use self::spatial::support::{SpatialBatchSpec, SpatialF64RowArray, SpatialPrecomputeLayout};
pub(crate) use self::typed_ir::TypedExecutorPlan;
pub(in crate::execution) use self::typed_ir::{TypedAction, TypedExpr, TypedSpatialRelation};

#[cfg(test)]
mod tests;
