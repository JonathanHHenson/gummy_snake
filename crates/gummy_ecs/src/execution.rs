use std::collections::HashMap;
use std::sync::Arc;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::plan::PhysicalPlan;
use crate::spatial::SpatialRecord;
use crate::world::World;

#[cfg(test)]
use crate::plan::{ActionNode, BridgePlanPayload, ExprNode, SpatialRelationNode};
#[cfg(test)]
use crate::schema::StorageType;

mod access_analysis;
mod actions;
mod aggregate_eval;
mod direct_f64_actions;
mod direct_point_hash_grid;
mod expression_eval;
mod f64_program;
mod parallel_actions;
mod query_context;
mod row_local_actions;
mod spatial_direct;
mod spatial_helpers;
mod spatial_index_cache;
mod spatial_numeric;
mod spatial_runtime;
mod spatial_support;
mod value_ops;
mod world_execution;

use self::spatial_helpers::dimensions_len;
pub(crate) use self::spatial_support::{BuiltSpatialIndex, CachedSpatialIndex};
use self::spatial_support::{
    SpatialBatchAccum, SpatialBatchSpec, SpatialBatchValue, SpatialF64RowArray,
    SpatialPrecomputeLayout,
};
use self::value_ops::{
    bool_f64, default_input_state_value, numeric_f64, storage_type_is_numeric, truthy, truthy_f64,
};

#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionWrite {
    ComponentField {
        entity: Entity,
        component: String,
        field: String,
        value: EcsValue,
    },
    ResourceField {
        resource: String,
        field: String,
        value: EcsValue,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionEvent {
    pub event_type: String,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionReport {
    pub rows_scanned: usize,
    pub fields_written: usize,
    pub resource_fields_written: usize,
    pub events_emitted: usize,
    pub structural_commands: usize,
    pub duplicate_writes: usize,
    pub spatial_indexes_built: usize,
    pub spatial_candidate_rows: usize,
    pub spatial_exact_rows: usize,
    pub spatial_false_positive_rows: usize,
    pub spatial_deduplicated_pairs: usize,
    pub spatial_algorithm_hash_grid: usize,
    pub spatial_algorithm_quadtree: usize,
    pub spatial_algorithm_octree: usize,
    pub spatial_algorithm_hilbert_curve: usize,
    pub spatial_index_reuses: usize,
    pub spatial_index_full_rebuilds: usize,
    pub spatial_index_incremental_updates: usize,
    pub spatial_parallel_chunks: usize,
    pub spatial_parallel_workers: usize,
    pub spatial_thread_scratch_reuses: usize,
    pub spatial_candidate_buffer_growths: usize,
    pub writes: Vec<ExecutionWrite>,
    pub events: Vec<ExecutionEvent>,
}

#[derive(Debug, Clone, Default)]
struct EvalContext {
    bindings: HashMap<String, Entity>,
    loop_items: HashMap<usize, EcsValue>,
}

impl EvalContext {
    fn with_binding(&self, query: String, entity: Entity) -> Self {
        let mut next = self.clone();
        next.bindings.insert(query, entity);
        next
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum WriteKey {
    Component {
        entity: Entity,
        component: String,
        field: String,
    },
    Resource {
        resource: String,
        field: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum ExprCacheKey {
    Empty(usize),
    One(usize, usize, u64),
    Many(usize, Vec<(usize, u64)>),
}

#[derive(Debug, Clone)]
struct DirectF64SetSpec {
    query: String,
    component: String,
    field: String,
    value_expr: usize,
}

type QueryRows = HashMap<String, Vec<Entity>>;
type QueryIndices = HashMap<String, usize>;
type QueryLocationCache = HashMap<String, Vec<(usize, usize)>>;
type SpatialIndexMetadata = HashMap<String, (String, u64, u64)>;
type SpatialRelationCacheKey = (String, Option<usize>, Option<usize>, bool, String, u64);
type SpatialRelationCache = HashMap<SpatialRelationCacheKey, Arc<Vec<SpatialRecord>>>;
type NumericFieldCache = HashMap<String, HashMap<String, Vec<Option<(u32, f64)>>>>;
type NumericFieldRowCache = HashMap<String, HashMap<String, Vec<f64>>>;
type SpatialBatchSpecCache = HashMap<(String, Option<usize>, Option<usize>), Vec<SpatialBatchSpec>>;
type SparseSpatialF64Cache = HashMap<usize, Vec<Option<(u32, f64)>>>;
type RowSpatialF64Cache = HashMap<usize, SpatialF64RowArray>;

struct PlanExecutor<'a> {
    world: &'a mut World,
    plan: &'a PhysicalPlan,
    query_rows: QueryRows,
    query_indices: QueryIndices,
    query_location_cache: QueryLocationCache,
    report: ExecutionReport,
    report_writes: bool,
    spatial_indexes: HashMap<String, BuiltSpatialIndex>,
    spatial_index_metadata: SpatialIndexMetadata,
    spatial_relation_cache: SpatialRelationCache,
    expr_cache: HashMap<ExprCacheKey, EcsValue>,
    local_expr_cache: Option<Vec<Option<EcsValue>>>,
    local_expr_bindings: Option<HashMap<String, Entity>>,
    numeric_field_cache_enabled: bool,
    numeric_field_cache: NumericFieldCache,
    numeric_field_cache_rows: NumericFieldRowCache,
    spatial_batch_spec_cache: SpatialBatchSpecCache,
    spatial_precomputed_f64: SparseSpatialF64Cache,
    spatial_precomputed_f64_rows: RowSpatialF64Cache,
    profile: bool,
    profile_eval_calls: usize,
    profile_expr_cache_hits: usize,
    profile_expr_cache_misses: usize,
    profile_spatial_relation_hits: usize,
    profile_spatial_relation_misses: usize,
    profile_spatial_index_nanos: u128,
    profile_spatial_query_nanos: u128,
    profile_spatial_filter_nanos: u128,
    profile_direct_aggregate_nanos: u128,
    profile_direct_aggregate_hits: usize,
}

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn new(
        world: &'a mut World,
        plan: &'a PhysicalPlan,
        query_rows: QueryRows,
        query_indices: QueryIndices,
        report_writes: bool,
        profile: bool,
    ) -> Self {
        Self {
            world,
            plan,
            query_rows,
            query_indices,
            query_location_cache: QueryLocationCache::new(),
            report: ExecutionReport::default(),
            report_writes,
            spatial_indexes: HashMap::new(),
            spatial_index_metadata: SpatialIndexMetadata::new(),
            spatial_relation_cache: SpatialRelationCache::new(),
            expr_cache: HashMap::new(),
            local_expr_cache: None,
            local_expr_bindings: None,
            numeric_field_cache_enabled: false,
            numeric_field_cache: NumericFieldCache::new(),
            numeric_field_cache_rows: NumericFieldRowCache::new(),
            spatial_batch_spec_cache: SpatialBatchSpecCache::new(),
            spatial_precomputed_f64: SparseSpatialF64Cache::new(),
            spatial_precomputed_f64_rows: RowSpatialF64Cache::new(),
            profile,
            profile_eval_calls: 0,
            profile_expr_cache_hits: 0,
            profile_expr_cache_misses: 0,
            profile_spatial_relation_hits: 0,
            profile_spatial_relation_misses: 0,
            profile_spatial_index_nanos: 0,
            profile_spatial_query_nanos: 0,
            profile_spatial_filter_nanos: 0,
            profile_direct_aggregate_nanos: 0,
            profile_direct_aggregate_hits: 0,
        }
    }
}

#[cfg(test)]
mod tests;
