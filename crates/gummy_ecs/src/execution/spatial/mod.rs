//! Spatial relation execution, indexing, caching, and direct-precompute paths.
//!
//! This hub keeps generic runtime evaluation, shared support types, persistent
//! index caches, numeric aggregation, direct variants, and the specialized
//! point hash grid distinct while retaining their shared `PlanExecutor` state.

pub(in crate::execution) mod cache;
pub(in crate::execution) mod direct;
pub(in crate::execution) mod helpers;
pub(in crate::execution) mod numeric;
pub(in crate::execution) mod point_hash_grid;
pub(in crate::execution) mod relation_cache;
pub(in crate::execution) mod runtime;
pub(in crate::execution) mod support;
