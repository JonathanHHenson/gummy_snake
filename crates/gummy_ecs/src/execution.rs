use std::collections::hash_map::DefaultHasher;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::sync::Arc;
use std::time::Instant;

use rayon::prelude::*;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::hilbert::HilbertIndex;
use crate::plan::{
    BridgePlanPayload, ExprNode, PhysicalPlan, PhysicalPlanHandle, SpatialBoundsExprNode,
    SpatialRelationNode,
};
use crate::scheduler::install_on_ecs_worker_pool;
use crate::schema::StorageType;
use crate::spatial::{Dimensions, HashGridIndex, SpatialAabb, SpatialPoint, SpatialRecord};
use crate::tree_spatial::{OctreeIndex, QuadtreeIndex};
use crate::world::World;

#[cfg(test)]
use crate::plan::ActionNode;

mod access_analysis;
mod actions;
mod direct_f64_actions;
mod direct_point_hash_grid;
mod f64_program;
mod parallel_actions;
mod row_local_actions;
mod spatial_support;
mod value_ops;

use self::access_analysis::{
    collect_action_query_access, query_access_conflicts, QueryAccessSummary,
};
use self::direct_point_hash_grid::{DirectPointHashGrid, DirectPointRecord};
use self::f64_program::{eval_binary_f64, eval_unary_f64};
use self::spatial_support::{
    comparison_from_op, reverse_comparison, DirectSpatialCoord, DirectSpatialRelationBatch,
    FastAggregateKind, FastDirectSpatialRelationBatch, FastFieldArray, FastSpatialBatchSpec,
    FastSpatialBatchValue, NumericComparison, SpatialBatchAccum, SpatialBatchSpec,
    SpatialBatchValue, SpatialChunkResult, SpatialDistanceFilter, SpatialF64RowArray,
    SpatialLocalCounters, SpatialPrecomputeLayout,
};
pub(crate) use self::spatial_support::{BuiltSpatialIndex, CachedSpatialIndex};
use self::value_ops::{
    bool_f64, coerce_value_for_storage, default_input_state_value, eval_binary, eval_unary,
    literal_expr_numeric, numeric_f64, storage_type_is_numeric, truthy, truthy_f64,
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

impl World {
    pub fn execute_bridge_plan(&mut self, payload: BridgePlanPayload) -> Result<ExecutionReport> {
        let plan = self.compile_bridge_plan(payload)?;
        self.execute_plan(&plan)
    }

    pub fn execute_compiled_plan(&mut self, handle: PhysicalPlanHandle) -> Result<ExecutionReport> {
        self.execute_compiled_plan_with_options(handle, true)
    }

    pub fn execute_compiled_plan_with_options(
        &mut self,
        handle: PhysicalPlanHandle,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let plan = self.validated_compiled_plan(handle)?;
        self.execute_plan_with_options(plan.as_ref(), include_writes)
    }

    pub fn execute_compiled_plans_with_options(
        &mut self,
        handles: &[PhysicalPlanHandle],
        include_writes: bool,
    ) -> Result<Vec<ExecutionReport>> {
        if handles.is_empty() {
            return Ok(Vec::new());
        }
        if include_writes || handles.len() == 1 {
            return handles
                .iter()
                .map(|handle| self.execute_compiled_plan_with_options(*handle, include_writes))
                .collect();
        }
        let plans = handles
            .iter()
            .map(|handle| self.validated_compiled_plan(*handle))
            .collect::<Result<Vec<_>>>()?;
        let access = plans
            .iter()
            .map(|plan| self.query_access_summary(plan.as_ref()))
            .collect::<Result<Vec<_>>>()?;
        let mut query_sets: HashMap<(usize, String), HashSet<u64>> = HashMap::new();
        for (plan_index, plan) in plans.iter().enumerate() {
            for query in &plan.queries {
                let rows = query_rows_for_world(self, plan.as_ref(), &query.name)?;
                query_sets.insert(
                    (plan_index, query.name.clone()),
                    rows.into_iter().map(|entity| entity.raw()).collect(),
                );
            }
        }

        let mut waves: Vec<Vec<usize>> = Vec::new();
        let mut current = Vec::new();
        for plan_index in 0..plans.len() {
            if !access[plan_index].copyback_eligible {
                if !current.is_empty() {
                    waves.push(std::mem::take(&mut current));
                }
                waves.push(vec![plan_index]);
                continue;
            }
            let conflicts = current.iter().any(|other| {
                query_access_conflicts(
                    &access[*other],
                    *other,
                    &access[plan_index],
                    plan_index,
                    &query_sets,
                )
            });
            if conflicts {
                if !current.is_empty() {
                    waves.push(std::mem::take(&mut current));
                }
            }
            current.push(plan_index);
        }
        if !current.is_empty() {
            waves.push(current);
        }

        let mut reports_by_index: Vec<Option<ExecutionReport>> = vec![None; plans.len()];
        for wave in waves {
            if wave.len() == 1 {
                let plan_index = wave[0];
                let report = self.execute_plan_with_options(plans[plan_index].as_ref(), false)?;
                reports_by_index[plan_index] = Some(report);
                continue;
            }
            let snapshot = self.clone();
            let wave_results = install_on_ecs_worker_pool(|| {
                wave.par_iter()
                    .map(|plan_index| {
                        let mut child = snapshot.clone();
                        let report = child
                            .execute_plan_with_options_inner(plans[*plan_index].as_ref(), false)?;
                        Ok((*plan_index, child, report))
                    })
                    .collect::<Result<Vec<_>>>()
            })?;
            let mut wave_results = wave_results;
            wave_results.sort_by_key(|(plan_index, _, _)| *plan_index);
            for (plan_index, child, report) in wave_results {
                self.copy_f64_write_targets_from(
                    &child,
                    plans[plan_index].as_ref(),
                    &access[plan_index],
                )?;
                reports_by_index[plan_index] = Some(report);
            }
        }
        reports_by_index
            .into_iter()
            .map(|report| {
                report.ok_or_else(|| {
                    EcsError::InvalidSchedule(
                        "compiled ECS batch did not produce one report per plan".to_string(),
                    )
                })
            })
            .collect()
    }

    fn validated_compiled_plan(
        &self,
        handle: PhysicalPlanHandle,
    ) -> Result<std::sync::Arc<PhysicalPlan>> {
        let plan = self.compiled_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if plan.schema_fingerprint != current_schema_fingerprint {
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {}, \
                 but the world schema fingerprint is {}; recompile the plan",
                plan.schema_fingerprint, current_schema_fingerprint
            )));
        }
        Ok(plan)
    }

    fn query_access_summary(&self, plan: &PhysicalPlan) -> Result<QueryAccessSummary> {
        let mut access = QueryAccessSummary {
            copyback_eligible: true,
            ..QueryAccessSummary::default()
        };
        collect_action_query_access(self, plan, plan.root_action, &mut access)?;
        if access.structural
            || !access.resource_writes.is_empty()
            || !access.event_writes.is_empty()
            || !access.hidden_writes.is_empty()
        {
            access.copyback_eligible = false;
        }
        if access.f64_write_targets.is_empty() {
            access.copyback_eligible = false;
        }
        Ok(access)
    }

    fn copy_f64_write_targets_from(
        &mut self,
        source: &World,
        plan: &PhysicalPlan,
        access: &QueryAccessSummary,
    ) -> Result<()> {
        let mut seen = HashSet::new();
        for target in &access.f64_write_targets {
            if !seen.insert(target.clone()) {
                continue;
            }
            let entities = query_rows_for_world(self, plan, &target.query)?;
            if entities.is_empty() {
                continue;
            }
            let locations = self.locations_for_entities(entities.iter().copied())?;
            let mut values = Vec::with_capacity(entities.len());
            for entity in &entities {
                values.push(source.get_field_f64(*entity, &target.component, &target.field)?);
            }
            self.set_field_f64_resolved_strided(
                &target.component,
                &target.field,
                &locations,
                &values,
                0,
                1,
            )?;
        }
        Ok(())
    }

    pub fn warm_compiled_plan_spatial_indexes(
        &mut self,
        handle: PhysicalPlanHandle,
    ) -> Result<ExecutionReport> {
        let plan = self.compiled_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if plan.schema_fingerprint != current_schema_fingerprint {
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {}, \
                 but the world schema fingerprint is {}; recompile the plan",
                plan.schema_fingerprint, current_schema_fingerprint
            )));
        }
        self.warm_plan_spatial_indexes(plan.as_ref())
    }

    pub fn execute_plan(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        self.execute_plan_with_options(plan, true)
    }

    pub fn execute_plan_with_options(
        &mut self,
        plan: &PhysicalPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| self.execute_plan_with_options_inner(plan, include_writes))
    }

    pub fn warm_plan_spatial_indexes(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| self.warm_plan_spatial_indexes_inner(plan))
    }

    fn warm_plan_spatial_indexes_inner(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        let (query_rows, query_indices) = query_rows_for_plan(self, plan)?;
        let mut executor = PlanExecutor::new(self, plan, query_rows, query_indices, false, false);
        let query_names = executor.query_rows.keys().cloned().collect::<Vec<_>>();
        for query_name in query_names {
            executor.precompute_direct_spatial_aggregates_for_query(
                &query_name,
                SpatialPrecomputeLayout::SparseEntity,
            )?;
        }
        executor.persist_spatial_index_cache();
        Ok(std::mem::take(&mut executor.report))
    }

    fn execute_plan_with_options_inner(
        &mut self,
        plan: &PhysicalPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let profile = std::env::var_os("GUMMY_ECS_PROFILE").is_some();
        let total_start = profile.then(Instant::now);
        let query_start = profile.then(Instant::now);
        let (query_rows, query_indices) = query_rows_for_plan(self, plan)?;
        if let Some(start) = query_start {
            eprintln!(
                "ecs_profile execute_query_prep elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let mut executor = PlanExecutor::new(
            self,
            plan,
            query_rows,
            query_indices,
            include_writes,
            profile,
        );
        let execute_result = executor.execute_action(plan.root_action, &[EvalContext::default()]);
        executor.persist_spatial_index_cache();
        execute_result?;
        if let Some(start) = total_start {
            eprintln!(
                "ecs_profile execute_total elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(executor.report)
    }

    pub fn storage_type_for_field(&self, component: &str, field: &str) -> Result<StorageType> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        schema
            .fields
            .iter()
            .find(|candidate| candidate.name == field)
            .map(|candidate| candidate.storage_type)
            .ok_or_else(|| EcsError::UnknownField {
                component: component.to_string(),
                field: field.to_string(),
            })
    }

    pub fn coerce_value_for_component_field(
        &self,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<EcsValue> {
        let storage_type = self.storage_type_for_field(component, field)?;
        coerce_value_for_storage(storage_type, value)
    }

    pub fn coerce_component_row(
        &self,
        component: &str,
        row: HashMap<String, EcsValue>,
    ) -> Result<HashMap<String, EcsValue>> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        let mut coerced = HashMap::with_capacity(row.len());
        for field in &schema.fields {
            let value = row
                .get(&field.name)
                .cloned()
                .ok_or_else(|| EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.name.clone(),
                })?;
            coerced.insert(
                field.name.clone(),
                coerce_value_for_storage(field.storage_type, value)?,
            );
        }
        for field in row.keys() {
            if !schema
                .fields
                .iter()
                .any(|candidate| &candidate.name == field)
            {
                return Err(EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.clone(),
                });
            }
        }
        Ok(coerced)
    }
}

impl<'a> PlanExecutor<'a> {
    fn query_locations(&mut self, query_name: &str) -> Result<Vec<(usize, usize)>> {
        if let Some(locations) = self.query_location_cache.get(query_name) {
            return Ok(locations.clone());
        }
        let rows = self.query_rows.get(query_name).ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        let locations = self.world.locations_for_entities(rows.iter().copied())?;
        self.query_location_cache
            .insert(query_name.to_string(), locations.clone());
        Ok(locations)
    }

    fn preload_numeric_fields_for_query(
        &mut self,
        query_name: &str,
        layout: SpatialPrecomputeLayout,
    ) -> Result<()> {
        let rows = self.query_rows.get(query_name).cloned().ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        let mut seen = HashSet::new();
        let mut fields = Vec::new();
        for expr in &self.plan.expressions {
            let ExprNode::Field {
                query,
                component,
                field,
            } = expr
            else {
                continue;
            };
            if query != query_name {
                continue;
            }
            if seen.insert((component.clone(), field.clone())) {
                fields.push((component.clone(), field.clone()));
            }
        }
        let locations = self.query_locations(query_name)?;
        for (component, field) in fields {
            match layout {
                SpatialPrecomputeLayout::SparseEntity => {
                    let values = self.world.field_f64_cache_for_resolved_entities(
                        &component, &field, &rows, &locations,
                    )?;
                    self.numeric_field_cache
                        .entry(component)
                        .or_default()
                        .insert(field, values);
                }
                SpatialPrecomputeLayout::QueryRows => {
                    let values = self
                        .world
                        .field_f64_rows_for_resolved_entities(&component, &field, &locations)?;
                    self.numeric_field_cache_rows
                        .entry(component)
                        .or_default()
                        .insert(field, values);
                }
            }
        }
        Ok(())
    }

    fn expand_context_for_queries(
        &self,
        base_ctx: &EvalContext,
        query_names: &BTreeSet<String>,
    ) -> Result<Vec<EvalContext>> {
        let missing = query_names
            .iter()
            .filter(|name| !base_ctx.bindings.contains_key(*name))
            .cloned()
            .collect::<Vec<_>>();
        if missing.is_empty() {
            return Ok(vec![base_ctx.clone()]);
        }
        let mut out = Vec::new();
        self.expand_query_recursive(base_ctx, &missing, 0, &mut out)?;
        Ok(out)
    }

    fn expand_query_recursive(
        &self,
        ctx: &EvalContext,
        missing: &[String],
        index: usize,
        out: &mut Vec<EvalContext>,
    ) -> Result<()> {
        if index == missing.len() {
            out.push(ctx.clone());
            return Ok(());
        }
        let query_name = &missing[index];
        let rows = self.query_rows.get(query_name).ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        for entity in rows {
            let next = ctx.with_binding(query_name.clone(), *entity);
            self.expand_query_recursive(&next, missing, index + 1, out)?;
        }
        Ok(())
    }

    fn entity_field_f64(&mut self, entity: Entity, component: &str, field: &str) -> Result<f64> {
        if !self.numeric_field_cache_enabled {
            return self.world.get_field_f64(entity, component, field);
        }
        let row = entity.index as usize;
        if let Some(fields) = self.numeric_field_cache.get(component) {
            if let Some(values) = fields.get(field) {
                if let Some(Some((generation, value))) = values.get(row) {
                    if *generation == entity.generation {
                        return Ok(*value);
                    }
                }
            }
        }
        let value = self.world.get_field_f64(entity, component, field)?;
        let values = self
            .numeric_field_cache
            .entry(component.to_string())
            .or_default()
            .entry(field.to_string())
            .or_default();
        if values.len() <= row {
            values.resize(row + 1, None);
        }
        values[row] = Some((entity.generation, value));
        Ok(value)
    }

    fn precomputed_spatial_f64(&self, expr_index: usize, entity: Entity) -> Option<f64> {
        let values = self.spatial_precomputed_f64.get(&expr_index)?;
        let Some(Some((generation, value))) = values.get(entity.index as usize) else {
            return None;
        };
        (*generation == entity.generation).then_some(*value)
    }

    fn store_precomputed_spatial_f64(&mut self, expr_index: usize, entity: Entity, value: f64) {
        let row = entity.index as usize;
        let values = self.spatial_precomputed_f64.entry(expr_index).or_default();
        if values.len() <= row {
            values.resize(row + 1, None);
        }
        values[row] = Some((entity.generation, value));
    }

    fn precompute_direct_spatial_aggregates_for_query(
        &mut self,
        query_name: &str,
        layout: SpatialPrecomputeLayout,
    ) -> Result<()> {
        let mut seen_relations = HashSet::new();
        let mut relations = Vec::new();
        for expr in &self.plan.expressions {
            let ExprNode::SpatialAggregate { relation, .. } = expr else {
                continue;
            };
            if relation.origin_query != query_name {
                continue;
            }
            let key = (relation.id.clone(), relation.radius, relation.exact_filter);
            if seen_relations.insert(key) {
                relations.push(relation.clone());
            }
        }
        let mut groups: Vec<(String, Vec<SpatialRelationNode>)> = Vec::new();
        for relation in relations {
            let index_key = self.spatial_index_cache_key(&relation);
            if let Some((_, group)) = groups
                .iter_mut()
                .find(|(candidate_key, _)| candidate_key == &index_key)
            {
                group.push(relation);
            } else {
                groups.push((index_key, vec![relation]));
            }
        }
        for (_, group) in groups {
            let Some(first_relation) = group.first() else {
                continue;
            };
            let Some((index_key, index)) =
                self.build_direct_spatial_index_for_relation(first_relation)?
            else {
                continue;
            };
            if self.precompute_direct_spatial_relation_group_f64(&group, &index, layout)? {
                self.spatial_indexes.insert(index_key, index);
                continue;
            }
            if self
                .precompute_multi_origin_direct_spatial_relation_group_f64(&group, &index, layout)?
            {
                self.spatial_indexes.insert(index_key, index);
                continue;
            }
            for relation in group {
                if self.precompute_direct_spatial_relation_group_f64(
                    std::slice::from_ref(&relation),
                    &index,
                    layout,
                )? {
                    continue;
                }
                self.precompute_direct_spatial_relation_f64(&relation, &index)?;
            }
            self.spatial_indexes.insert(index_key, index);
        }
        Ok(())
    }

    fn build_direct_spatial_index_for_relation(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Option<(String, BuiltSpatialIndex)>> {
        if relation.target_bounds.is_some() {
            return Ok(None);
        }
        let Some(target_coords) =
            self.match_direct_spatial_coords(&relation.target_position, &relation.item_query)
        else {
            return Ok(None);
        };
        let index_key = self.spatial_index_cache_key(relation);
        if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let item_rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let item_locations = self.query_locations(&relation.item_query)?;
        let mut target_coord_arrays = Vec::with_capacity(target_coords.len());
        for coord in &target_coords {
            target_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                &coord.component,
                &coord.field,
                &item_locations,
            )?);
        }
        let worker_count = rayon::current_num_threads().max(1);
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        if item_rows.len() >= worker_count * 32 {
            self.report.spatial_parallel_chunks += worker_count;
        }
        if relation.algorithm.kind == "hash_grid" {
            let records = item_rows
                .par_iter()
                .enumerate()
                .map(|(row_index, entity)| {
                    Ok(DirectPointRecord {
                        entity: *entity,
                        point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let signature = self.spatial_index_signature(relation);
            let structural_revision = self.world.structural_revision();
            let field_revision = self.spatial_dependency_revision(relation);
            if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
                if cached.signature == signature
                    && cached.structural_revision == structural_revision
                {
                    if let BuiltSpatialIndex::DirectPointHashGrid(direct_index) = &mut cached.index
                    {
                        if direct_index.update_sorted_points(&records)? {
                            self.report.spatial_index_incremental_updates += 1;
                        } else {
                            self.report.spatial_indexes_built += 1;
                            self.report.spatial_index_full_rebuilds += 1;
                        }
                        self.spatial_index_metadata.insert(
                            index_key.clone(),
                            (signature, structural_revision, field_revision),
                        );
                        self.report_algorithm_use(&cached.index);
                        return Ok(Some((index_key, cached.index)));
                    }
                }
            }
            let mut direct_index = DirectPointHashGrid::new(
                dimensions_from_u8(relation.algorithm.dimensions)?,
                relation.algorithm.cell_size.unwrap_or(1.0),
            )?;
            direct_index.build_sorted_points(records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            let index = BuiltSpatialIndex::DirectPointHashGrid(direct_index);
            self.spatial_index_metadata.insert(
                index_key.clone(),
                (signature, structural_revision, field_revision),
            );
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let records = item_rows
            .par_iter()
            .enumerate()
            .map(|(row_index, entity)| {
                Ok(SpatialRecord {
                    entity: *entity,
                    point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    bounds: None,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let index = self.build_or_update_spatial_index(relation, records)?;
        self.report_algorithm_use(&index);
        Ok(Some((index_key, index)))
    }

    fn direct_spatial_relation_batch(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Option<DirectSpatialRelationBatch>> {
        if relation.origin_bounds.is_some() || relation.target_bounds.is_some() {
            return Ok(None);
        }
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() {
            return Ok(None);
        }
        let radius = relation
            .radius
            .and_then(|expr| literal_expr_numeric(&self.plan.expressions[expr]));
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        if relation.exact_filter.is_some() && distance_filter.is_none() {
            return Ok(None);
        }
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let Some(query_radius) = query_radius else {
            return Ok(None);
        };
        Ok(Some(DirectSpatialRelationBatch {
            specs,
            distance_filter,
            query_radius,
        }))
    }

    fn build_fast_field_array_with_locations(
        &self,
        entities: &[Entity],
        locations: &[(usize, usize)],
        component: &str,
        field: &str,
    ) -> Result<FastFieldArray> {
        let values = self
            .world
            .field_f64_cache_for_resolved_entities(component, field, entities, locations)?;
        Ok(FastFieldArray {
            component: component.to_string(),
            field: field.to_string(),
            values,
        })
    }

    fn ensure_fast_field_array_with_locations(
        &self,
        arrays: &mut Vec<FastFieldArray>,
        entities: &[Entity],
        locations: &[(usize, usize)],
        component: &str,
        field: &str,
    ) -> Result<usize> {
        if let Some(index) = arrays
            .iter()
            .position(|array| array.component == component && array.field == field)
        {
            return Ok(index);
        }
        arrays.push(
            self.build_fast_field_array_with_locations(entities, locations, component, field)?,
        );
        Ok(arrays.len() - 1)
    }

    fn precompute_direct_spatial_relation_group_f64(
        &mut self,
        relations: &[SpatialRelationNode],
        index: &BuiltSpatialIndex,
        layout: SpatialPrecomputeLayout,
    ) -> Result<bool> {
        let profile_start = self.profile.then(Instant::now);
        let Some(first) = relations.first() else {
            return Ok(false);
        };
        if relations
            .iter()
            .any(|relation| !spatial_relations_same_direct_precompute_group(first, relation))
        {
            return Ok(false);
        }
        let Some(origin_coords) =
            self.match_direct_spatial_coords(&first.origin_position, &first.origin_query)
        else {
            return Ok(false);
        };
        let origin_rows = self
            .query_rows
            .get(&first.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    first.origin_query
                ))
            })?;
        let item_rows = self
            .query_rows
            .get(&first.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    first.item_query
                ))
            })?;
        let origin_locations = self.query_locations(&first.origin_query)?;
        let item_locations = self.query_locations(&first.item_query)?;
        let mut origin_coord_arrays = Vec::with_capacity(origin_coords.len());
        for coord in &origin_coords {
            origin_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                &coord.component,
                &coord.field,
                &origin_locations,
            )?);
        }
        let target_coords = self
            .match_direct_spatial_coords(&first.target_position, &first.item_query)
            .unwrap_or_default();
        let mut item_field_arrays: Vec<FastFieldArray> = Vec::new();
        let mut batches = Vec::with_capacity(relations.len());
        for relation in relations {
            let Some(batch) = self.direct_spatial_relation_batch(relation)? else {
                return Ok(false);
            };
            let mut specs = Vec::with_capacity(batch.specs.len());
            for spec in batch.specs {
                let value = match spec.value {
                    SpatialBatchValue::Count => FastSpatialBatchValue::Count,
                    SpatialBatchValue::DirectField { component, field } => {
                        if let Some(axis) = target_coords
                            .iter()
                            .position(|coord| coord.component == component && coord.field == field)
                        {
                            FastSpatialBatchValue::DirectPointCoord { axis }
                        } else {
                            let array_index = self.ensure_fast_field_array_with_locations(
                                &mut item_field_arrays,
                                &item_rows,
                                &item_locations,
                                &component,
                                &field,
                            )?;
                            FastSpatialBatchValue::DirectField { array_index }
                        }
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => FastSpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    },
                };
                let Some(kind) = fast_aggregate_kind(&spec.kind) else {
                    return Ok(false);
                };
                specs.push(FastSpatialBatchSpec {
                    expr_index: spec.expr_index,
                    kind,
                    value,
                });
            }
            batches.push(FastDirectSpatialRelationBatch {
                specs,
                distance_filter: batch.distance_filter,
                query_radius: batch.query_radius,
                query_radius_sq: batch.query_radius * batch.query_radius,
            });
        }
        let item_record_field_arrays = if let BuiltSpatialIndex::DirectPointHashGrid(index) = index
        {
            item_field_arrays
                .iter()
                .map(|array| fast_field_array_record_values(array, index.records()))
                .collect::<Result<Vec<_>>>()?
        } else {
            Vec::new()
        };
        let item_record_field_arrays_ref =
            (!item_record_field_arrays.is_empty()).then_some(item_record_field_arrays.as_slice());
        let dimensions = dimensions_len(first.algorithm.dimensions)?;
        let result_exprs = batches
            .iter()
            .flat_map(|batch| batch.specs.iter().map(|spec| spec.expr_index))
            .collect::<Vec<_>>();
        let result_count = result_exprs.len();
        if result_count == 0 {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(&batches);
        let max_entity_index = origin_rows
            .iter()
            .map(|entity| entity.index as usize)
            .max()
            .unwrap_or(0);
        let max_radius = batches
            .iter()
            .map(|batch| batch.query_radius)
            .fold(0.0_f64, f64::max);
        if layout == SpatialPrecomputeLayout::QueryRows {
            if let BuiltSpatialIndex::DirectPointHashGrid(item_index) = index {
                if !item_index.has_regular_grid()
                    && item_index.record_count() >= 1024
                    && item_index.record_count().saturating_mul(4) < origin_rows.len()
                    && self.precompute_inverted_direct_spatial_relation_group_f64(
                        first,
                        &batches,
                        &origin_rows,
                        &origin_coord_arrays,
                        item_index,
                        &item_field_arrays,
                        item_record_field_arrays_ref,
                        &result_exprs,
                        result_count,
                        max_radius,
                    )?
                {
                    if let Some(start) = profile_start {
                        eprintln!(
                            "ecs_profile direct_spatial_group mode=same_origin_inverted origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                            first.origin_query,
                            first.item_query,
                            relations.len(),
                            result_count,
                            origin_rows.len(),
                            start.elapsed().as_secs_f64() * 1000.0
                        );
                    }
                    return Ok(true);
                }
            }
        }
        let worker_count = rayon::current_num_threads().max(1);
        let chunk_size = (origin_rows.len() / (worker_count * 4))
            .clamp(128, 1024)
            .max(1);
        let chunk_results = origin_rows
            .par_chunks(chunk_size)
            .enumerate()
            .map(|(chunk_index, chunk)| {
                let row_start = chunk_index * chunk_size;
                let mut candidates = Vec::new();
                let mut counters = SpatialLocalCounters::default();
                let mut origins = Vec::with_capacity(chunk.len());
                let mut values = Vec::with_capacity(chunk.len() * result_count);
                let mut present = (!result_values_are_dense)
                    .then(|| Vec::with_capacity(chunk.len() * result_count));
                let mut accumulators = batches
                    .iter()
                    .map(|batch| vec![SpatialBatchAccum::default(); batch.specs.len()])
                    .collect::<Vec<_>>();
                let mut exact_counts = vec![0usize; batches.len()];
                for (chunk_offset, origin_entity) in chunk.iter().copied().enumerate() {
                    let origin_row = row_start + chunk_offset;
                    let origin_point = point_from_row_arrays(&origin_coord_arrays, origin_row)?;
                    for accumulator in &mut accumulators {
                        accumulator.fill(SpatialBatchAccum::default());
                    }
                    exact_counts.fill(0);
                    let before_capacity = candidates.capacity();
                    match index {
                        BuiltSpatialIndex::HashGrid(index) => {
                            index.visit_radius_unordered(
                                &origin_point,
                                max_radius,
                                |record, distance_sq| {
                                    process_fast_spatial_record(
                                        first,
                                        &batches,
                                        &item_field_arrays,
                                        None,
                                        origin_entity,
                                        &origin_point,
                                        None,
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators,
                                        &mut exact_counts,
                                        &mut counters,
                                    )
                                },
                            )?;
                        }
                        BuiltSpatialIndex::DirectPointHashGrid(index) => {
                            index.visit_radius_unordered_indexed(
                                &origin_point,
                                max_radius,
                                |record_index, record, distance_sq| {
                                    process_fast_spatial_record(
                                        first,
                                        &batches,
                                        &item_field_arrays,
                                        item_record_field_arrays_ref,
                                        origin_entity,
                                        &origin_point,
                                        Some(record_index),
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators,
                                        &mut exact_counts,
                                        &mut counters,
                                    )
                                },
                            )?;
                        }
                        _ => {
                            candidates.clear();
                            index.query_radius_unordered(
                                &origin_point,
                                max_radius,
                                &mut candidates,
                            )?;
                            if candidates.capacity() > before_capacity {
                                counters.candidate_buffer_growths += 1;
                            }
                            for record in candidates.iter() {
                                let distance_sq = direct_distance_squared(
                                    &origin_point,
                                    &record.point,
                                    dimensions,
                                );
                                process_fast_spatial_record(
                                    first,
                                    &batches,
                                    &item_field_arrays,
                                    None,
                                    origin_entity,
                                    &origin_point,
                                    None,
                                    record.entity,
                                    &record.point,
                                    distance_sq,
                                    &mut accumulators,
                                    &mut exact_counts,
                                    &mut counters,
                                )?;
                            }
                        }
                    }
                    if layout == SpatialPrecomputeLayout::SparseEntity {
                        origins.push(origin_entity);
                    }
                    for (batch_index, batch) in batches.iter().enumerate() {
                        let exact_count = exact_counts[batch_index];
                        for (spec, accumulator) in
                            batch.specs.iter().zip(accumulators[batch_index].iter())
                        {
                            let value = match spec.kind {
                                FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                                FastAggregateKind::Count => Some(exact_count as f64),
                                FastAggregateKind::Sum => Some(accumulator.sum),
                                FastAggregateKind::Mean if accumulator.count > 0 => {
                                    Some(accumulator.sum / accumulator.count as f64)
                                }
                                FastAggregateKind::Min if accumulator.count > 0 => {
                                    Some(accumulator.min)
                                }
                                FastAggregateKind::Max if accumulator.count > 0 => {
                                    Some(accumulator.max)
                                }
                                _ => None,
                            };
                            if result_values_are_dense {
                                values.push(value.unwrap_or(0.0));
                            } else if let Some(present) = present.as_mut() {
                                match value {
                                    Some(value) => {
                                        values.push(value);
                                        present.push(true);
                                    }
                                    None => {
                                        values.push(0.0);
                                        present.push(false);
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(SpatialChunkResult {
                    row_start,
                    origins,
                    values,
                    present,
                    counters,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        self.report.spatial_parallel_chunks += chunk_results.len();
        self.report.spatial_thread_scratch_reuses +=
            origin_rows.len().saturating_sub(chunk_results.len());
        match layout {
            SpatialPrecomputeLayout::SparseEntity => {
                let mut result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; max_entity_index + 1]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start: _,
                        origins,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let present = present.as_deref();
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for (origin_index, origin) in origins.into_iter().enumerate() {
                        let base = origin_index * result_count;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present.is_none_or(|present| present[base + slot]) {
                                result_arrays[slot].1[origin.index as usize] =
                                    Some((origin.generation, *value));
                            }
                        }
                    }
                }
                for (expr_index, values) in result_arrays {
                    self.spatial_precomputed_f64.insert(expr_index, values);
                }
            }
            SpatialPrecomputeLayout::QueryRows if result_values_are_dense => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present: _,
                        counters,
                    } = chunk;
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            row_result_arrays[slot].1[row_index] = *value;
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Dense(values));
                }
            }
            SpatialPrecomputeLayout::QueryRows => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let Some(present) = present else {
                        return Err(EcsError::InvalidPlan(
                            "optional spatial row results missing presence flags".to_string(),
                        ));
                    };
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present[base + slot] {
                                row_result_arrays[slot].1[row_index] = Some(*value);
                            }
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Optional(values));
                }
            }
        }
        if let Some(start) = profile_start {
            eprintln!(
                "ecs_profile direct_spatial_group mode=same_origin origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                first.origin_query,
                first.item_query,
                relations.len(),
                result_count,
                origin_rows.len(),
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(true)
    }

    #[allow(clippy::too_many_arguments)]
    fn precompute_inverted_direct_spatial_relation_group_f64(
        &mut self,
        relation: &SpatialRelationNode,
        batches: &[FastDirectSpatialRelationBatch],
        origin_rows: &[Entity],
        _origin_coord_arrays: &[Vec<f64>],
        item_index: &DirectPointHashGrid,
        item_field_arrays: &[FastFieldArray],
        item_record_field_arrays: Option<&[Vec<f64>]>,
        result_exprs: &[usize],
        result_count: usize,
        max_radius: f64,
    ) -> Result<bool> {
        if result_count == 0 || origin_rows.is_empty() || item_index.is_empty() {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(batches);
        let mut origin_index_relation = relation.clone();
        origin_index_relation.index_id = format!("inverted_origin:{}", relation.index_id);
        origin_index_relation.item_query = relation.origin_query.clone();
        origin_index_relation.target_position = relation.origin_position.clone();
        origin_index_relation.target_bounds = None;
        let Some((origin_index_key, BuiltSpatialIndex::DirectPointHashGrid(origin_index))) =
            self.build_direct_spatial_index_for_relation(&origin_index_relation)?
        else {
            return Ok(false);
        };
        if !origin_index.has_regular_grid()
            && item_index.record_count().saturating_mul(4) >= origin_rows.len()
        {
            self.spatial_indexes.insert(
                origin_index_key,
                BuiltSpatialIndex::DirectPointHashGrid(origin_index),
            );
            return Ok(false);
        }

        let mut spec_offsets = Vec::with_capacity(batches.len());
        let mut offset = 0usize;
        for batch in batches {
            spec_offsets.push(offset);
            offset += batch.specs.len();
        }
        if offset != result_count {
            return Ok(false);
        }

        let mut accumulators = vec![SpatialBatchAccum::default(); origin_rows.len() * result_count];
        let mut exact_counts = vec![0usize; origin_rows.len() * batches.len()];
        let mut counters = SpatialLocalCounters::default();

        for (item_record_index, item_record) in item_index.records().iter().enumerate() {
            let item_entity = item_record.entity;
            let item_point = &item_record.point;
            origin_index.visit_radius_unordered_indexed(
                item_point,
                max_radius,
                |origin_index, origin_record, distance_sq| {
                    counters.candidate_rows += 1;
                    if !relation.include_self && item_entity == origin_record.entity {
                        return Ok(());
                    }
                    if relation.pair_policy == "unique_unordered"
                        && item_entity.raw() <= origin_record.entity.raw()
                    {
                        counters.deduplicated_pairs += 1;
                        return Ok(());
                    }
                    let mut inverse_distance_cache: Option<(f64, f64)> = None;
                    for (batch_index, batch) in batches.iter().enumerate() {
                        if distance_sq > batch.query_radius_sq {
                            continue;
                        }
                        if let Some(distance_filter) = batch.distance_filter {
                            if !distance_filter.matches(distance_sq) {
                                continue;
                            }
                        }
                        exact_counts[origin_index * batches.len() + batch_index] += 1;
                        counters.rows_scanned += 1;
                        counters.exact_rows += 1;
                        let spec_offset = spec_offsets[batch_index];
                        for (spec_index, spec) in batch.specs.iter().enumerate() {
                            if matches!(
                                spec.kind,
                                FastAggregateKind::Any | FastAggregateKind::Count
                            ) {
                                continue;
                            }
                            let value = match &spec.value {
                                FastSpatialBatchValue::Count => 1.0,
                                FastSpatialBatchValue::DirectField { array_index } => {
                                    if let Some(record_arrays) = item_record_field_arrays {
                                        record_arrays[*array_index][item_record_index]
                                    } else {
                                        fast_field_array_value(
                                            &item_field_arrays[*array_index],
                                            item_entity,
                                        )?
                                    }
                                }
                                FastSpatialBatchValue::DirectPointCoord { axis } => {
                                    item_point.coord(*axis)
                                }
                                FastSpatialBatchValue::NegDeltaOverDistance {
                                    axis,
                                    minimum_distance,
                                } => {
                                    let inverse_distance = match inverse_distance_cache {
                                        Some((cached_minimum, value))
                                            if cached_minimum == *minimum_distance =>
                                        {
                                            value
                                        }
                                        _ => {
                                            let value =
                                                1.0 / distance_sq.sqrt().max(*minimum_distance);
                                            inverse_distance_cache =
                                                Some((*minimum_distance, value));
                                            value
                                        }
                                    };
                                    let delta_axis =
                                        item_point.coord(*axis) - origin_record.point.coord(*axis);
                                    -delta_axis * inverse_distance
                                }
                            };
                            let accumulator = &mut accumulators
                                [origin_index * result_count + spec_offset + spec_index];
                            match spec.kind {
                                FastAggregateKind::Sum => accumulator.sum += value,
                                FastAggregateKind::Mean => {
                                    accumulator.count += 1;
                                    accumulator.sum += value;
                                }
                                FastAggregateKind::Min => {
                                    accumulator.count += 1;
                                    accumulator.min = accumulator.min.min(value);
                                }
                                FastAggregateKind::Max => {
                                    accumulator.count += 1;
                                    accumulator.max = accumulator.max.max(value);
                                }
                                FastAggregateKind::Any | FastAggregateKind::Count => {}
                            }
                        }
                    }
                    Ok(())
                },
            )?;
        }

        if result_values_are_dense {
            let mut row_result_arrays = result_exprs
                .iter()
                .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                .collect::<Vec<_>>();
            for origin_index in 0..origin_rows.len() {
                for (batch_index, batch) in batches.iter().enumerate() {
                    let exact_count = exact_counts[origin_index * batches.len() + batch_index];
                    let spec_offset = spec_offsets[batch_index];
                    for (spec_index, spec) in batch.specs.iter().enumerate() {
                        let accumulator =
                            &accumulators[origin_index * result_count + spec_offset + spec_index];
                        let value = match spec.kind {
                            FastAggregateKind::Any => bool_f64(exact_count > 0),
                            FastAggregateKind::Count => exact_count as f64,
                            FastAggregateKind::Sum => accumulator.sum,
                            _ => 0.0,
                        };
                        row_result_arrays[spec_offset + spec_index].1[origin_index] = value;
                    }
                }
            }
            for (expr_index, values) in row_result_arrays {
                self.spatial_precomputed_f64_rows
                    .insert(expr_index, SpatialF64RowArray::Dense(values));
            }
        } else {
            let mut row_result_arrays = result_exprs
                .iter()
                .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                .collect::<Vec<_>>();
            for origin_index in 0..origin_rows.len() {
                for (batch_index, batch) in batches.iter().enumerate() {
                    let exact_count = exact_counts[origin_index * batches.len() + batch_index];
                    let spec_offset = spec_offsets[batch_index];
                    for (spec_index, spec) in batch.specs.iter().enumerate() {
                        let accumulator =
                            &accumulators[origin_index * result_count + spec_offset + spec_index];
                        let value = match spec.kind {
                            FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                            FastAggregateKind::Count => Some(exact_count as f64),
                            FastAggregateKind::Sum => Some(accumulator.sum),
                            FastAggregateKind::Mean if accumulator.count > 0 => {
                                Some(accumulator.sum / accumulator.count as f64)
                            }
                            FastAggregateKind::Min if accumulator.count > 0 => {
                                Some(accumulator.min)
                            }
                            FastAggregateKind::Max if accumulator.count > 0 => {
                                Some(accumulator.max)
                            }
                            _ => None,
                        };
                        if let Some(value) = value {
                            row_result_arrays[spec_offset + spec_index].1[origin_index] =
                                Some(value);
                        }
                    }
                }
            }
            for (expr_index, values) in row_result_arrays {
                self.spatial_precomputed_f64_rows
                    .insert(expr_index, SpatialF64RowArray::Optional(values));
            }
        }
        self.spatial_indexes.insert(
            origin_index_key,
            BuiltSpatialIndex::DirectPointHashGrid(origin_index),
        );
        self.report.spatial_candidate_rows += counters.candidate_rows;
        self.report.rows_scanned += counters.rows_scanned;
        self.report.spatial_exact_rows += counters.exact_rows;
        self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
        self.report.spatial_candidate_buffer_growths += counters.candidate_buffer_growths;
        Ok(true)
    }

    fn precompute_multi_origin_direct_spatial_relation_group_f64(
        &mut self,
        relations: &[SpatialRelationNode],
        index: &BuiltSpatialIndex,
        layout: SpatialPrecomputeLayout,
    ) -> Result<bool> {
        let profile_start = self.profile.then(Instant::now);
        let Some(first) = relations.first() else {
            return Ok(false);
        };
        if relations.len() < 2
            || relations.iter().any(|relation| {
                !spatial_relations_same_multi_origin_precompute_group(first, relation)
            })
        {
            return Ok(false);
        }
        if first.origin_bounds.is_some() || first.target_bounds.is_some() {
            return Ok(false);
        }
        let origin_rows = self
            .query_rows
            .get(&first.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    first.origin_query
                ))
            })?;
        let item_rows = self
            .query_rows
            .get(&first.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    first.item_query
                ))
            })?;
        let origin_locations = self.query_locations(&first.origin_query)?;
        let item_locations = self.query_locations(&first.item_query)?;
        let target_coords = self
            .match_direct_spatial_coords(&first.target_position, &first.item_query)
            .unwrap_or_default();
        let mut item_field_arrays: Vec<FastFieldArray> = Vec::new();
        let mut origin_coord_arrays_by_relation = Vec::with_capacity(relations.len());
        let mut batches = Vec::with_capacity(relations.len());
        for relation in relations {
            let Some(origin_coords) =
                self.match_direct_spatial_coords(&relation.origin_position, &relation.origin_query)
            else {
                return Ok(false);
            };
            let mut origin_coord_arrays = Vec::with_capacity(origin_coords.len());
            for coord in &origin_coords {
                origin_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                    &coord.component,
                    &coord.field,
                    &origin_locations,
                )?);
            }
            let Some(batch) = self.direct_spatial_relation_batch(relation)? else {
                return Ok(false);
            };
            let mut specs = Vec::with_capacity(batch.specs.len());
            for spec in batch.specs {
                let value = match spec.value {
                    SpatialBatchValue::Count => FastSpatialBatchValue::Count,
                    SpatialBatchValue::DirectField { component, field } => {
                        if let Some(axis) = target_coords
                            .iter()
                            .position(|coord| coord.component == component && coord.field == field)
                        {
                            FastSpatialBatchValue::DirectPointCoord { axis }
                        } else {
                            let array_index = self.ensure_fast_field_array_with_locations(
                                &mut item_field_arrays,
                                &item_rows,
                                &item_locations,
                                &component,
                                &field,
                            )?;
                            FastSpatialBatchValue::DirectField { array_index }
                        }
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => FastSpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    },
                };
                let Some(kind) = fast_aggregate_kind(&spec.kind) else {
                    return Ok(false);
                };
                specs.push(FastSpatialBatchSpec {
                    expr_index: spec.expr_index,
                    kind,
                    value,
                });
            }
            origin_coord_arrays_by_relation.push(origin_coord_arrays);
            batches.push(FastDirectSpatialRelationBatch {
                specs,
                distance_filter: batch.distance_filter,
                query_radius: batch.query_radius,
                query_radius_sq: batch.query_radius * batch.query_radius,
            });
        }
        let item_record_field_arrays = if let BuiltSpatialIndex::DirectPointHashGrid(index) = index
        {
            item_field_arrays
                .iter()
                .map(|array| fast_field_array_record_values(array, index.records()))
                .collect::<Result<Vec<_>>>()?
        } else {
            Vec::new()
        };
        let item_record_field_arrays_ref =
            (!item_record_field_arrays.is_empty()).then_some(item_record_field_arrays.as_slice());
        let dimensions = dimensions_len(first.algorithm.dimensions)?;
        let result_exprs = batches
            .iter()
            .flat_map(|batch| batch.specs.iter().map(|spec| spec.expr_index))
            .collect::<Vec<_>>();
        let result_count = result_exprs.len();
        if result_count == 0 {
            return Ok(false);
        }
        let result_values_are_dense = spatial_result_values_are_dense(&batches);
        let max_entity_index = origin_rows
            .iter()
            .map(|entity| entity.index as usize)
            .max()
            .unwrap_or(0);
        let worker_count = rayon::current_num_threads().max(1);
        let chunk_size = (origin_rows.len() / (worker_count * 4))
            .clamp(128, 1024)
            .max(1);
        let chunk_results = origin_rows
            .par_chunks(chunk_size)
            .enumerate()
            .map(|(chunk_index, chunk)| {
                let row_start = chunk_index * chunk_size;
                let mut candidates = Vec::new();
                let mut counters = SpatialLocalCounters::default();
                let mut origins = Vec::with_capacity(chunk.len());
                let mut values = Vec::with_capacity(chunk.len() * result_count);
                let mut present = (!result_values_are_dense)
                    .then(|| Vec::with_capacity(chunk.len() * result_count));
                let mut accumulators = batches
                    .iter()
                    .map(|batch| vec![SpatialBatchAccum::default(); batch.specs.len()])
                    .collect::<Vec<_>>();
                let mut exact_counts = vec![0usize; batches.len()];
                for (chunk_offset, origin_entity) in chunk.iter().copied().enumerate() {
                    let origin_row = row_start + chunk_offset;
                    for accumulator in &mut accumulators {
                        accumulator.fill(SpatialBatchAccum::default());
                    }
                    exact_counts.fill(0);
                    for relation_index in 0..batches.len() {
                        let origin_point = point_from_row_arrays(
                            &origin_coord_arrays_by_relation[relation_index],
                            origin_row,
                        )?;
                        let batch = &batches[relation_index];
                        let before_capacity = candidates.capacity();
                        match index {
                            BuiltSpatialIndex::HashGrid(index) => {
                                index.visit_radius_unordered(
                                    &origin_point,
                                    batch.query_radius,
                                    |record, distance_sq| {
                                        process_fast_spatial_record(
                                            &relations[relation_index],
                                            &batches[relation_index..relation_index + 1],
                                            &item_field_arrays,
                                            None,
                                            origin_entity,
                                            &origin_point,
                                            None,
                                            record.entity,
                                            &record.point,
                                            distance_sq,
                                            &mut accumulators[relation_index..relation_index + 1],
                                            &mut exact_counts[relation_index..relation_index + 1],
                                            &mut counters,
                                        )
                                    },
                                )?;
                            }
                            BuiltSpatialIndex::DirectPointHashGrid(index) => {
                                index.visit_radius_unordered_indexed(
                                    &origin_point,
                                    batch.query_radius,
                                    |record_index, record, distance_sq| {
                                        process_fast_spatial_record(
                                            &relations[relation_index],
                                            &batches[relation_index..relation_index + 1],
                                            &item_field_arrays,
                                            item_record_field_arrays_ref,
                                            origin_entity,
                                            &origin_point,
                                            Some(record_index),
                                            record.entity,
                                            &record.point,
                                            distance_sq,
                                            &mut accumulators[relation_index..relation_index + 1],
                                            &mut exact_counts[relation_index..relation_index + 1],
                                            &mut counters,
                                        )
                                    },
                                )?;
                            }
                            _ => {
                                candidates.clear();
                                index.query_radius_unordered(
                                    &origin_point,
                                    batch.query_radius,
                                    &mut candidates,
                                )?;
                                if candidates.capacity() > before_capacity {
                                    counters.candidate_buffer_growths += 1;
                                }
                                for record in candidates.iter() {
                                    let distance_sq = direct_distance_squared(
                                        &origin_point,
                                        &record.point,
                                        dimensions,
                                    );
                                    process_fast_spatial_record(
                                        &relations[relation_index],
                                        &batches[relation_index..relation_index + 1],
                                        &item_field_arrays,
                                        None,
                                        origin_entity,
                                        &origin_point,
                                        None,
                                        record.entity,
                                        &record.point,
                                        distance_sq,
                                        &mut accumulators[relation_index..relation_index + 1],
                                        &mut exact_counts[relation_index..relation_index + 1],
                                        &mut counters,
                                    )?;
                                }
                            }
                        }
                    }
                    if layout == SpatialPrecomputeLayout::SparseEntity {
                        origins.push(origin_entity);
                    }
                    for (relation_index, batch) in batches.iter().enumerate() {
                        let exact_count = exact_counts[relation_index];
                        for (spec, accumulator) in
                            batch.specs.iter().zip(accumulators[relation_index].iter())
                        {
                            let value = match spec.kind {
                                FastAggregateKind::Any => Some(bool_f64(exact_count > 0)),
                                FastAggregateKind::Count => Some(exact_count as f64),
                                FastAggregateKind::Sum => Some(accumulator.sum),
                                FastAggregateKind::Mean if accumulator.count > 0 => {
                                    Some(accumulator.sum / accumulator.count as f64)
                                }
                                FastAggregateKind::Min if accumulator.count > 0 => {
                                    Some(accumulator.min)
                                }
                                FastAggregateKind::Max if accumulator.count > 0 => {
                                    Some(accumulator.max)
                                }
                                _ => None,
                            };
                            if result_values_are_dense {
                                values.push(value.unwrap_or(0.0));
                            } else if let Some(present) = present.as_mut() {
                                match value {
                                    Some(value) => {
                                        values.push(value);
                                        present.push(true);
                                    }
                                    None => {
                                        values.push(0.0);
                                        present.push(false);
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(SpatialChunkResult {
                    row_start,
                    origins,
                    values,
                    present,
                    counters,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        self.report.spatial_parallel_chunks += chunk_results.len();
        self.report.spatial_thread_scratch_reuses +=
            origin_rows.len().saturating_sub(chunk_results.len());
        match layout {
            SpatialPrecomputeLayout::SparseEntity => {
                let mut result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; max_entity_index + 1]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start: _,
                        origins,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let present = present.as_deref();
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for (origin_index, origin) in origins.into_iter().enumerate() {
                        let base = origin_index * result_count;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present.is_none_or(|present| present[base + slot]) {
                                result_arrays[slot].1[origin.index as usize] =
                                    Some((origin.generation, *value));
                            }
                        }
                    }
                }
                for (expr_index, values) in result_arrays {
                    self.spatial_precomputed_f64.insert(expr_index, values);
                }
            }
            SpatialPrecomputeLayout::QueryRows if result_values_are_dense => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![0.0; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present: _,
                        counters,
                    } = chunk;
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            row_result_arrays[slot].1[row_index] = *value;
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Dense(values));
                }
            }
            SpatialPrecomputeLayout::QueryRows => {
                let mut row_result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, vec![None; origin_rows.len()]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present,
                        counters,
                    } = chunk;
                    let Some(present) = present else {
                        return Err(EcsError::InvalidPlan(
                            "optional spatial row results missing presence flags".to_string(),
                        ));
                    };
                    self.report.spatial_candidate_rows += counters.candidate_rows;
                    self.report.rows_scanned += counters.rows_scanned;
                    self.report.spatial_exact_rows += counters.exact_rows;
                    self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
                    self.report.spatial_candidate_buffer_growths +=
                        counters.candidate_buffer_growths;
                    for origin_index in 0..(values.len() / result_count) {
                        let base = origin_index * result_count;
                        let row_index = row_start + origin_index;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present[base + slot] {
                                row_result_arrays[slot].1[row_index] = Some(*value);
                            }
                        }
                    }
                }
                for (expr_index, values) in row_result_arrays {
                    self.spatial_precomputed_f64_rows
                        .insert(expr_index, SpatialF64RowArray::Optional(values));
                }
            }
        }
        if let Some(start) = profile_start {
            eprintln!(
                "ecs_profile direct_spatial_group mode=multi_origin origin={} item={} relations={} result_count={} origins={} elapsed_ms={:.3}",
                first.origin_query,
                first.item_query,
                relations.len(),
                result_count,
                origin_rows.len(),
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(true)
    }

    fn precompute_direct_spatial_relation_f64(
        &mut self,
        relation: &SpatialRelationNode,
        index: &BuiltSpatialIndex,
    ) -> Result<()> {
        if relation.origin_bounds.is_some() || relation.target_bounds.is_some() {
            return Ok(());
        }
        let Some(origin_coords) =
            self.match_direct_spatial_coords(&relation.origin_position, &relation.origin_query)
        else {
            return Ok(());
        };
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() {
            return Ok(());
        }

        let radius = relation
            .radius
            .and_then(|expr| literal_expr_numeric(&self.plan.expressions[expr]));
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        let generic_exact_filter = if relation.exact_filter.is_some() && distance_filter.is_none() {
            relation.exact_filter
        } else {
            None
        };
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let Some(query_radius) = query_radius else {
            return Ok(());
        };

        let origin_rows = self
            .query_rows
            .get(&relation.origin_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not part of the plan",
                    relation.origin_query
                ))
            })?;

        let dimensions = dimensions_len(relation.algorithm.dimensions)?;
        let needs_delta = specs
            .iter()
            .any(|spec| matches!(spec.value, SpatialBatchValue::NegDeltaOverDistance { .. }));
        let mut candidates = Vec::new();
        let mut accumulators = vec![SpatialBatchAccum::default(); specs.len()];
        for origin_entity in origin_rows {
            let origin_point =
                self.direct_spatial_point_for_entity(origin_entity, &origin_coords)?;

            accumulators.fill(SpatialBatchAccum::default());
            let mut exact_count = 0usize;
            let mut process_record = |executor: &mut Self,
                                      record: &SpatialRecord,
                                      visited_distance_sq: f64|
             -> Result<()> {
                executor.report.spatial_candidate_rows += 1;
                if !relation.include_self && record.entity == origin_entity {
                    return Ok(());
                }
                if relation.pair_policy == "unique_unordered"
                    && record.entity.raw() <= origin_entity.raw()
                {
                    executor.report.spatial_deduplicated_pairs += 1;
                    return Ok(());
                }
                let distance_sq = if needs_delta || distance_filter.is_some() {
                    visited_distance_sq
                } else {
                    0.0
                };
                if let Some(distance_filter) = distance_filter {
                    if !distance_filter.matches(distance_sq) {
                        return Ok(());
                    }
                }
                if let Some(filter_expr) = generic_exact_filter {
                    let mut filter_ctx = EvalContext::default();
                    filter_ctx
                        .bindings
                        .insert(relation.origin_query.clone(), origin_entity);
                    filter_ctx
                        .bindings
                        .insert(relation.item_query.clone(), record.entity);
                    let mut filter_cache = vec![None; executor.plan.expressions.len()];
                    if !truthy_f64(executor.eval_expr_f64(
                        filter_expr,
                        &filter_ctx,
                        &mut filter_cache,
                    )?) {
                        return Ok(());
                    }
                }
                exact_count += 1;
                executor.report.rows_scanned += 1;
                executor.report.spatial_exact_rows += 1;
                for (index, spec) in specs.iter().enumerate() {
                    let value = match &spec.value {
                        SpatialBatchValue::Count => 1.0,
                        SpatialBatchValue::DirectField { component, field } => {
                            executor.entity_field_f64(record.entity, component, field)?
                        }
                        SpatialBatchValue::NegDeltaOverDistance {
                            axis,
                            minimum_distance,
                        } => {
                            let delta_axis = record.point.coord(*axis) - origin_point.coord(*axis);
                            -delta_axis / distance_sq.sqrt().max(*minimum_distance)
                        }
                    };
                    let accumulator = &mut accumulators[index];
                    accumulator.count += 1;
                    accumulator.sum += value;
                    accumulator.min = accumulator.min.min(value);
                    accumulator.max = accumulator.max.max(value);
                }
                Ok(())
            };
            match &index {
                BuiltSpatialIndex::HashGrid(index) => {
                    index.visit_radius_unordered(
                        &origin_point,
                        query_radius,
                        |record, distance_sq| process_record(self, record, distance_sq),
                    )?;
                }
                _ => {
                    candidates.clear();
                    index.query_radius_unordered(&origin_point, query_radius, &mut candidates)?;
                    for record in candidates.iter() {
                        let distance_sq = if needs_delta || distance_filter.is_some() {
                            direct_distance_squared(&origin_point, &record.point, dimensions)
                        } else {
                            0.0
                        };
                        process_record(self, record, distance_sq)?;
                    }
                }
            }

            for (spec, accumulator) in specs.iter().zip(accumulators.iter()) {
                let value = match spec.kind.as_str() {
                    "any" => bool_f64(exact_count > 0),
                    "count" => exact_count as f64,
                    "sum" => accumulator.sum,
                    "mean" if accumulator.count > 0 => accumulator.sum / accumulator.count as f64,
                    "min" if accumulator.count > 0 => accumulator.min,
                    "max" if accumulator.count > 0 => accumulator.max,
                    _ => continue,
                };
                self.store_precomputed_spatial_f64(spec.expr_index, origin_entity, value);
            }
        }
        Ok(())
    }

    fn match_direct_spatial_coords(
        &self,
        coords: &[usize],
        query_name: &str,
    ) -> Option<Vec<DirectSpatialCoord>> {
        let mut direct = Vec::with_capacity(coords.len());
        for expr in coords {
            let ExprNode::Field {
                query,
                component,
                field,
            } = &self.plan.expressions[*expr]
            else {
                return None;
            };
            if query != query_name {
                return None;
            }
            direct.push(DirectSpatialCoord {
                component: component.clone(),
                field: field.clone(),
            });
        }
        Some(direct)
    }

    fn direct_spatial_point_for_entity(
        &mut self,
        entity: Entity,
        coords: &[DirectSpatialCoord],
    ) -> Result<SpatialPoint> {
        match coords {
            [x, y] => SpatialPoint::point2(
                self.entity_field_f64(entity, &x.component, &x.field)?,
                self.entity_field_f64(entity, &y.component, &y.field)?,
            ),
            [x, y, z] => SpatialPoint::point3(
                self.entity_field_f64(entity, &x.component, &x.field)?,
                self.entity_field_f64(entity, &y.component, &y.field)?,
                self.entity_field_f64(entity, &z.component, &z.field)?,
            ),
            _ => Err(EcsError::InvalidPlan(
                "spatial points must have 2 or 3 coordinates".to_string(),
            )),
        }
    }

    fn eval_expr_f64(
        &mut self,
        expr_index: usize,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if let Some(value) = cache[expr_index] {
            return Ok(value);
        }
        let value = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => *value,
            ExprNode::LiteralI64(value) => *value as f64,
            ExprNode::LiteralBool(value) => bool_f64(*value),
            ExprNode::LiteralValue(value) => numeric_f64(value)?,
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.entity_field_f64(*entity, component, field)?
            }
            ExprNode::ResourceField { resource, field } => {
                numeric_f64(&self.world.resource_field(resource, field)?)?
            }
            ExprNode::InputState { name, code } => numeric_f64(
                &self
                    .world
                    .input_state(name, *code)
                    .unwrap_or_else(|| default_input_state_value(name)),
            )?,
            ExprNode::Unary { op, input } => {
                let input = self.eval_expr_f64(*input, ctx, cache)?;
                eval_unary_f64(op, input)?
            }
            ExprNode::Binary { op, left, right } => {
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if !truthy_f64(left) {
                        0.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    if truthy_f64(left) {
                        1.0
                    } else {
                        bool_f64(truthy_f64(self.eval_expr_f64(*right, ctx, cache)?))
                    }
                } else {
                    let left = self.eval_expr_f64(*left, ctx, cache)?;
                    let right = self.eval_expr_f64(*right, ctx, cache)?;
                    eval_binary_f64(op, left, right)?
                }
            }
            ExprNode::ContextJoin { predicate, .. } => {
                self.eval_expr_f64(*predicate, ctx, cache)?
            }
            ExprNode::Exists { query, predicate } => {
                bool_f64(truthy(&self.eval_exists(query, *predicate, ctx)?)?)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => numeric_f64(&self.eval_grouped_aggregate(
                kind,
                *relation,
                group_query.as_deref(),
                *value,
                *default,
                ctx,
            )?)?,
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => numeric_f64(&self.eval_spatial_metadata(relation, kind, *axis, ctx)?)?,
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => self.eval_spatial_aggregate_f64(
                expr_index, kind, relation, *value, *default, ctx, cache,
            )?,
            ExprNode::Attribute { input, .. } => self.eval_expr_f64(*input, ctx, cache)?,
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {
                return Err(EcsError::InvalidPlan(format!(
                    "expression {expr_index} is not numeric"
                )))
            }
        };
        cache[expr_index] = Some(value);
        Ok(value)
    }

    fn eval_spatial_aggregate_f64(
        &mut self,
        expr_index: usize,
        kind: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<f64> {
        if cache[expr_index].is_none() {
            if let Some(origin_entity) = ctx.bindings.get(&relation.origin_query).copied() {
                if let Some(value) = self.precomputed_spatial_f64(expr_index, origin_entity) {
                    cache[expr_index] = Some(value);
                    return Ok(value);
                }
            }
            self.compute_spatial_aggregate_batch_f64(relation, ctx, cache)?;
        }
        if let Some(value) = cache[expr_index] {
            return Ok(value);
        }

        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        match kind {
            "any" => return Ok(bool_f64(count > 0)),
            "count" => return Ok(count as f64),
            _ => {}
        }
        let Some(value_expr) = value else {
            return numeric_f64(&aggregate_finish(
                kind,
                count,
                Vec::new(),
                default,
                self,
                ctx,
            )?);
        };
        if let Some(result) = self.try_direct_spatial_numeric_aggregate(
            kind,
            relation,
            value_expr,
            records.as_ref(),
            default,
            ctx,
        )? {
            return numeric_f64(&result);
        }
        if count == 0 {
            return numeric_f64(&aggregate_empty(kind, default, self, ctx)?);
        }
        let mut sum = 0.0;
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        for record in records.iter() {
            let mut joined = ctx.clone();
            joined
                .bindings
                .insert(relation.item_query.clone(), record.entity);
            let mut item_cache = vec![None; self.plan.expressions.len()];
            let value = self.eval_expr_f64(value_expr, &joined, &mut item_cache)?;
            sum += value;
            min_value = min_value.min(value);
            max_value = max_value.max(value);
        }
        match kind {
            "sum" => Ok(sum),
            "mean" => Ok(sum / count as f64),
            "min" => Ok(min_value),
            "max" => Ok(max_value),
            other => Err(EcsError::InvalidPlan(format!(
                "unsupported aggregate kind '{other}'"
            ))),
        }
    }

    fn spatial_batch_specs_for_relation(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Vec<SpatialBatchSpec>> {
        let spec_cache_key = (relation.id.clone(), relation.radius, relation.exact_filter);
        if let Some(specs) = self.spatial_batch_spec_cache.get(&spec_cache_key) {
            return Ok(specs.clone());
        }

        let mut specs = Vec::new();
        for (expr_index, expr) in self.plan.expressions.iter().enumerate() {
            let ExprNode::SpatialAggregate {
                kind,
                relation: candidate_relation,
                value,
                default,
            } = expr
            else {
                continue;
            };
            if candidate_relation != relation || default.is_some() {
                continue;
            }
            let value = match (kind.as_str(), value) {
                ("any" | "count", None) => SpatialBatchValue::Count,
                (_, Some(value_expr)) => {
                    if let Some((axis, minimum_distance)) =
                        self.match_neg_delta_over_clamped_distance(*value_expr, relation)?
                    {
                        SpatialBatchValue::NegDeltaOverDistance {
                            axis,
                            minimum_distance,
                        }
                    } else if let ExprNode::Field {
                        query,
                        component,
                        field,
                    } = &self.plan.expressions[*value_expr]
                    {
                        if query != &relation.item_query {
                            continue;
                        }
                        SpatialBatchValue::DirectField {
                            component: component.clone(),
                            field: field.clone(),
                        }
                    } else {
                        continue;
                    }
                }
                _ => continue,
            };
            specs.push(SpatialBatchSpec {
                expr_index,
                kind: kind.clone(),
                value,
            });
        }
        self.spatial_batch_spec_cache
            .insert(spec_cache_key, specs.clone());
        Ok(specs)
    }

    fn compute_spatial_aggregate_batch_f64(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
    ) -> Result<()> {
        let specs = self.spatial_batch_specs_for_relation(relation)?;
        if specs.is_empty() || specs.iter().all(|spec| cache[spec.expr_index].is_some()) {
            return Ok(());
        }

        let origin_entity = ctx
            .bindings
            .get(&relation.origin_query)
            .copied()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        if self.profile {
            self.profile_spatial_relation_misses += 1;
        }
        let records = self.build_spatial_relation_records(relation, ctx, origin_entity)?;
        let count = records.len();
        let dimensions = dimensions_len(relation.algorithm.dimensions)?;
        let needs_delta = specs
            .iter()
            .any(|spec| matches!(spec.value, SpatialBatchValue::NegDeltaOverDistance { .. }));
        let origin = if needs_delta {
            Some(self.eval_spatial_point(&relation.origin_position, ctx)?)
        } else {
            None
        };
        let mut accumulators = vec![SpatialBatchAccum::default(); specs.len()];
        for record in records.iter() {
            let mut distance_sq = 0.0;
            if let Some(origin) = &origin {
                for axis in 0..dimensions {
                    let delta = record.point.coord(axis) - origin.coord(axis);
                    distance_sq += delta * delta;
                }
            }
            for (index, spec) in specs.iter().enumerate() {
                let value = match &spec.value {
                    SpatialBatchValue::Count => 1.0,
                    SpatialBatchValue::DirectField { component, field } => {
                        self.entity_field_f64(record.entity, component, field)?
                    }
                    SpatialBatchValue::NegDeltaOverDistance {
                        axis,
                        minimum_distance,
                    } => {
                        let origin = origin
                            .as_ref()
                            .expect("origin computed for delta aggregate");
                        let delta_axis = record.point.coord(*axis) - origin.coord(*axis);
                        -delta_axis / distance_sq.sqrt().max(*minimum_distance)
                    }
                };
                let accumulator = &mut accumulators[index];
                accumulator.count += 1;
                accumulator.sum += value;
                accumulator.min = accumulator.min.min(value);
                accumulator.max = accumulator.max.max(value);
            }
        }
        for (spec, accumulator) in specs.into_iter().zip(accumulators) {
            let value = match spec.kind.as_str() {
                "any" => bool_f64(count > 0),
                "count" => count as f64,
                "sum" => accumulator.sum,
                "mean" if accumulator.count > 0 => accumulator.sum / accumulator.count as f64,
                "min" if accumulator.count > 0 => accumulator.min,
                "max" if accumulator.count > 0 => accumulator.max,
                _ => continue,
            };
            cache[spec.expr_index] = Some(value);
        }
        Ok(())
    }

    fn eval_expr(&mut self, expr_index: usize, ctx: &EvalContext) -> Result<EcsValue> {
        if self.profile {
            self.profile_eval_calls += 1;
        }
        let use_local_cache = ctx.loop_items.is_empty()
            && self
                .local_expr_bindings
                .as_ref()
                .is_some_and(|bindings| bindings == &ctx.bindings);
        if use_local_cache {
            if let Some(cache) = self.local_expr_cache.as_ref() {
                if let Some(Some(value)) = cache.get(expr_index) {
                    if self.profile {
                        self.profile_expr_cache_hits += 1;
                    }
                    return Ok(value.clone());
                }
            }
            if self.profile {
                self.profile_expr_cache_misses += 1;
            }
        } else {
            let cache_key = self.expr_cache_key(expr_index, ctx);
            if let Some(key) = &cache_key {
                if let Some(value) = self.expr_cache.get(key) {
                    if self.profile {
                        self.profile_expr_cache_hits += 1;
                    }
                    return Ok(value.clone());
                }
            }
            if self.profile {
                self.profile_expr_cache_misses += 1;
            }
        }
        let result = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Ok(EcsValue::F64(*value)),
            ExprNode::LiteralI64(value) => Ok(EcsValue::I64(*value)),
            ExprNode::LiteralBool(value) => Ok(EcsValue::Bool(*value)),
            ExprNode::LiteralString(value) => Ok(EcsValue::String(value.clone())),
            ExprNode::LiteralValue(value) => Ok(value.clone()),
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.world.get_field(*entity, component, field)
            }
            ExprNode::ResourceField { resource, field } => {
                self.world.resource_field(resource, field)
            }
            ExprNode::Attribute { input, attribute } => {
                let input = *input;
                let attribute = attribute.clone();
                let value = self.eval_expr(input, ctx)?;
                match value {
                    EcsValue::Struct(fields) => fields.get(&attribute).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "struct value has no attribute '{attribute}'"
                        ))
                    }),
                    other => Err(EcsError::InvalidPlan(format!(
                        "attribute access expects a struct value, got {}",
                        other.kind_name()
                    ))),
                }
            }
            ExprNode::EventStream { event_type } => Ok(EcsValue::List(
                self.world
                    .read_events(event_type)?
                    .into_iter()
                    .map(|event| event.payload)
                    .collect(),
            )),
            ExprNode::ForEachItem { slot } => ctx.loop_items.get(slot).cloned().ok_or_else(|| {
                EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
            }),
            ExprNode::Unary { op, input } => {
                let op = op.clone();
                let input = *input;
                let input = self.eval_expr(input, ctx)?;
                eval_unary(&op, input)
            }
            ExprNode::Binary { op, left, right } => {
                let op = op.clone();
                let left = *left;
                let right = *right;
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr(left, ctx)?;
                    if !truthy(&left)? {
                        return Ok(EcsValue::Bool(false));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr(left, ctx)?;
                    if truthy(&left)? {
                        return Ok(EcsValue::Bool(true));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                let left = self.eval_expr(left, ctx)?;
                let right = self.eval_expr(right, ctx)?;
                eval_binary(&op, left, right)
            }
            ExprNode::InputState { name, code } => Ok(self
                .world
                .input_state(name, *code)
                .unwrap_or_else(|| default_input_state_value(name))),
            ExprNode::ContextJoin { predicate, .. } => self.eval_expr(*predicate, ctx),
            ExprNode::Exists { query, predicate } => {
                let query = query.clone();
                self.eval_exists(&query, *predicate, ctx)
            }
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => {
                let kind = kind.clone();
                let group_query = group_query.clone();
                self.eval_grouped_aggregate(
                    &kind,
                    *relation,
                    group_query.as_deref(),
                    *value,
                    *default,
                    ctx,
                )
            }
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => {
                let relation = relation.clone();
                let kind = kind.clone();
                self.eval_spatial_metadata(&relation, &kind, *axis, ctx)
            }
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => {
                let kind = kind.clone();
                let relation = relation.clone();
                self.eval_spatial_aggregate(&kind, &relation, *value, *default, ctx)
            }
        };
        if let Ok(value) = &result {
            if use_local_cache {
                if let Some(cache) = self.local_expr_cache.as_mut() {
                    if let Some(slot) = cache.get_mut(expr_index) {
                        *slot = Some(value.clone());
                    }
                }
            } else {
                let cache_key = self.expr_cache_key(expr_index, ctx);
                if let Some(key) = cache_key {
                    self.expr_cache.insert(key, value.clone());
                }
            }
        }
        result
    }

    fn expr_cache_key(&self, expr_index: usize, ctx: &EvalContext) -> Option<ExprCacheKey> {
        if !ctx.loop_items.is_empty() {
            return None;
        }
        match ctx.bindings.len() {
            0 => Some(ExprCacheKey::Empty(expr_index)),
            1 => ctx.bindings.iter().next().map(|(query, entity)| {
                ExprCacheKey::One(
                    expr_index,
                    *self.query_indices.get(query).unwrap_or(&usize::MAX),
                    entity.raw(),
                )
            }),
            _ => {
                let mut bindings = ctx
                    .bindings
                    .iter()
                    .map(|(query, entity)| {
                        (
                            *self.query_indices.get(query).unwrap_or(&usize::MAX),
                            entity.raw(),
                        )
                    })
                    .collect::<Vec<_>>();
                bindings.sort_by_key(|(query_index, _)| *query_index);
                Some(ExprCacheKey::Many(expr_index, bindings))
            }
        }
    }

    fn eval_exists(
        &mut self,
        query: &str,
        predicate: usize,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let mut query_names = BTreeSet::new();
        query_names.insert(query.to_string());
        self.collect_expr_queries(predicate, &mut query_names)?;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            self.report.rows_scanned += 1;
            if truthy(&self.eval_expr(predicate, &joined)?)? {
                return Ok(EcsValue::Bool(true));
            }
        }
        Ok(EcsValue::Bool(false))
    }

    fn eval_grouped_aggregate(
        &mut self,
        kind: &str,
        relation: usize,
        group_query: Option<&str>,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let Some(group_query) = group_query else {
            return Err(EcsError::InvalidPlan(
                "aggregate expressions need a group query".to_string(),
            ));
        };
        let Some(target_entity) = ctx.bindings.get(group_query).copied() else {
            return aggregate_empty(kind, default, self, ctx);
        };
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(relation, &mut query_names)?;
        if let Some(value) = value {
            self.collect_expr_queries(value, &mut query_names)?;
        }
        let mut values = Vec::new();
        let mut count = 0usize;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            if joined.bindings.get(group_query).copied() != Some(target_entity) {
                continue;
            }
            self.report.rows_scanned += 1;
            if !truthy(&self.eval_expr(relation, &joined)?)? {
                continue;
            }
            count += 1;
            if kind == "any" {
                return Ok(EcsValue::Bool(true));
            }
            if let Some(value_expr) = value {
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn eval_spatial_metadata(
        &mut self,
        relation: &SpatialRelationNode,
        kind: &str,
        axis: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let origin = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let item = self.eval_spatial_point(&relation.target_position, ctx)?;
        let mut delta = [0.0_f64; 3];
        for (axis, slot) in delta
            .iter_mut()
            .enumerate()
            .take(dimensions_len(relation.algorithm.dimensions)?)
        {
            *slot = item.coord(axis) - origin.coord(axis);
        }
        if kind == "delta" {
            let axis = axis.ok_or_else(|| {
                EcsError::InvalidPlan("spatial delta metadata requires an axis".to_string())
            })?;
            return Ok(EcsValue::F64(delta[axis]));
        }
        let distance_sq = delta.iter().map(|value| value * value).sum::<f64>();
        match kind {
            "distance_sq" => Ok(EcsValue::F64(distance_sq)),
            "distance" => Ok(EcsValue::F64(distance_sq.sqrt())),
            other => Err(EcsError::InvalidPlan(format!(
                "unsupported spatial metadata kind '{other}'"
            ))),
        }
    }

    fn eval_spatial_aggregate(
        &mut self,
        kind: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        if kind == "any" {
            return Ok(EcsValue::Bool(count > 0));
        }
        if let Some(value_expr) = value {
            if let Some(result) = self.try_direct_spatial_numeric_aggregate(
                kind,
                relation,
                value_expr,
                records.as_ref(),
                default,
                ctx,
            )? {
                return Ok(result);
            }
        }
        let mut values = Vec::new();
        if let Some(value_expr) = value {
            values.reserve(records.len());
            for record in records.iter() {
                let mut joined = ctx.clone();
                joined
                    .bindings
                    .insert(relation.item_query.clone(), record.entity);
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn try_direct_spatial_numeric_aggregate(
        &mut self,
        kind: &str,
        relation: &SpatialRelationNode,
        value_expr: usize,
        records: &[SpatialRecord],
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<Option<EcsValue>> {
        let aggregate_start = self.profile.then(Instant::now);
        if kind == "sum" {
            if let Some((axis, minimum_distance)) =
                self.match_neg_delta_over_clamped_distance(value_expr, relation)?
            {
                let origin = self.eval_spatial_point(&relation.origin_position, ctx)?;
                let dimensions = dimensions_len(relation.algorithm.dimensions)?;
                let mut sum = 0.0;
                for record in records {
                    let mut distance_sq = 0.0_f64;
                    for axis_index in 0..dimensions {
                        let delta = record.point.coord(axis_index) - origin.coord(axis_index);
                        distance_sq += delta * delta;
                    }
                    let delta_axis = record.point.coord(axis) - origin.coord(axis);
                    sum += -delta_axis / distance_sq.sqrt().max(minimum_distance);
                }
                if let Some(start) = &aggregate_start {
                    self.profile_direct_aggregate_hits += 1;
                    self.profile_direct_aggregate_nanos += start.elapsed().as_nanos();
                }
                return Ok(Some(EcsValue::F64(sum)));
            }
        }

        let ExprNode::Field {
            query,
            component,
            field,
        } = &self.plan.expressions[value_expr]
        else {
            return Ok(None);
        };
        if query != &relation.item_query {
            return Ok(None);
        }

        if records.is_empty() {
            return match kind {
                "sum" => Ok(Some(EcsValue::F64(0.0))),
                "min" | "max" | "mean" => aggregate_empty(kind, default, self, ctx).map(Some),
                _ => Ok(None),
            };
        }

        let mut sum = 0.0;
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        for record in records {
            let value = self.entity_field_f64(record.entity, component, field)?;
            sum += value;
            if value < min_value {
                min_value = value;
            }
            if value > max_value {
                max_value = value;
            }
        }

        let result = match kind {
            "sum" => Some(EcsValue::F64(sum)),
            "mean" => Some(EcsValue::F64(sum / records.len() as f64)),
            "min" => Some(EcsValue::F64(min_value)),
            "max" => Some(EcsValue::F64(max_value)),
            _ => None,
        };
        if result.is_some() {
            if let Some(start) = &aggregate_start {
                self.profile_direct_aggregate_hits += 1;
                self.profile_direct_aggregate_nanos += start.elapsed().as_nanos();
            }
        }
        Ok(result)
    }

    fn match_neg_delta_over_clamped_distance(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Result<Option<(usize, f64)>> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return Ok(None);
        };
        if op != "truediv" && op != "/" {
            return Ok(None);
        }

        let Some(axis) = self.match_neg_spatial_delta(*left, relation) else {
            return Ok(None);
        };
        let Some(minimum_distance) = self.match_clamped_spatial_distance(*right, relation)? else {
            return Ok(None);
        };
        Ok(Some((axis, minimum_distance)))
    }

    fn match_neg_spatial_delta(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Option<usize> {
        let ExprNode::Unary { op, input } = &self.plan.expressions[expr_index] else {
            return None;
        };
        if op != "neg" && op != "-" {
            return None;
        }
        let ExprNode::SpatialMetadata {
            relation: metadata_relation,
            kind,
            axis,
        } = &self.plan.expressions[*input]
        else {
            return None;
        };
        if kind == "delta" && spatial_relations_same_base(metadata_relation, relation) {
            *axis
        } else {
            None
        }
    }

    fn match_clamped_spatial_distance(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Result<Option<f64>> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return Ok(None);
        };
        if op != "max" {
            return Ok(None);
        }
        if self.is_spatial_distance(*left, relation) {
            return Ok(literal_expr_numeric(&self.plan.expressions[*right]));
        }
        if self.is_spatial_distance(*right, relation) {
            return Ok(literal_expr_numeric(&self.plan.expressions[*left]));
        }
        Ok(None)
    }

    fn is_spatial_distance(&self, expr_index: usize, relation: &SpatialRelationNode) -> bool {
        matches!(
            &self.plan.expressions[expr_index],
            ExprNode::SpatialMetadata {
                relation: metadata_relation,
                kind,
                axis: None,
            } if kind == "distance" && spatial_relations_same_base(metadata_relation, relation)
        )
    }

    fn match_spatial_distance_filter(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
    ) -> Option<SpatialDistanceFilter> {
        let ExprNode::Binary { op, left, right } = &self.plan.expressions[expr_index] else {
            return None;
        };
        let comparison = comparison_from_op(op)?;
        if let Some(filter) =
            self.match_spatial_distance_filter_side(*left, *right, comparison, relation)
        {
            return Some(filter);
        }
        self.match_spatial_distance_filter_side(
            *right,
            *left,
            reverse_comparison(comparison),
            relation,
        )
    }

    fn match_spatial_distance_filter_side(
        &self,
        metadata_expr: usize,
        literal_expr: usize,
        comparison: NumericComparison,
        relation: &SpatialRelationNode,
    ) -> Option<SpatialDistanceFilter> {
        let threshold = literal_expr_numeric(&self.plan.expressions[literal_expr])?;
        let ExprNode::SpatialMetadata {
            relation: metadata_relation,
            kind,
            axis: None,
        } = &self.plan.expressions[metadata_expr]
        else {
            return None;
        };
        if !spatial_relations_same_base(metadata_relation, relation) {
            return None;
        }
        match kind.as_str() {
            "distance" => Some(SpatialDistanceFilter::Distance {
                comparison,
                threshold,
            }),
            "distance_sq" => Some(SpatialDistanceFilter::DistanceSq {
                comparison,
                threshold,
            }),
            _ => None,
        }
    }

    fn spatial_relation_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Arc<Vec<SpatialRecord>>> {
        let origin_entity = ctx
            .bindings
            .get(&relation.origin_query)
            .copied()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        let cache_key = (
            relation.id.clone(),
            relation.radius,
            relation.exact_filter,
            relation.include_self,
            relation.pair_policy.clone(),
            origin_entity.raw(),
        );
        if let Some(records) = self.spatial_relation_cache.get(&cache_key) {
            if self.profile {
                self.profile_spatial_relation_hits += 1;
            }
            return Ok(Arc::clone(records));
        }
        if self.profile {
            self.profile_spatial_relation_misses += 1;
        }

        let records =
            Arc::new(self.build_spatial_relation_records(relation, ctx, origin_entity)?);
        self.spatial_relation_cache
            .insert(cache_key, Arc::clone(&records));
        Ok(records)
    }

    fn build_spatial_relation_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
        origin_entity: Entity,
    ) -> Result<Vec<SpatialRecord>> {
        let origin_point = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let origin_bounds = relation
            .origin_bounds
            .as_ref()
            .map(|bounds| self.eval_spatial_bounds(bounds, ctx))
            .transpose()?;
        let radius = relation
            .radius
            .map(|expr| {
                self.eval_expr(expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .transpose()?;
        let distance_filter = relation
            .exact_filter
            .and_then(|expr| self.match_spatial_distance_filter(expr, relation));
        let query_radius = match (
            radius,
            distance_filter.and_then(|filter| filter.upper_radius_bound()),
        ) {
            (Some(radius), Some(bound)) => Some(radius.min(bound)),
            (Some(radius), None) => Some(radius),
            (None, Some(bound)) => Some(bound),
            (None, None) => None,
        };
        let profile = self.profile;
        let mut candidates = Vec::new();
        let index_start = profile.then(Instant::now);
        let index = self.ensure_spatial_index(relation, ctx)?;
        let index_nanos = index_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        let query_start = profile.then(Instant::now);
        if let Some(bounds) = &origin_bounds {
            index.query_aabb(bounds, &mut candidates)?;
        } else if let Some(radius) = query_radius {
            index.query_radius_unordered(&origin_point, radius, &mut candidates)?;
        } else {
            let bounds = point_bounds(&origin_point)?;
            index.query_aabb(&bounds, &mut candidates)?;
        }
        let query_nanos = query_start
            .map(|start| start.elapsed().as_nanos())
            .unwrap_or(0);
        if profile {
            self.profile_spatial_index_nanos += index_nanos;
            self.profile_spatial_query_nanos += query_nanos;
        }
        self.report.spatial_candidate_rows += candidates.len();
        let filter_start = profile.then(Instant::now);
        let mut records = Vec::new();
        for record in candidates {
            if !relation.include_self && record.entity == origin_entity {
                continue;
            }
            if relation.pair_policy == "unique_unordered"
                && record.entity.raw() <= origin_entity.raw()
            {
                self.report.spatial_deduplicated_pairs += 1;
                continue;
            }
            if let Some(bounds) = &origin_bounds {
                let record_bounds = record
                    .bounds
                    .clone()
                    .unwrap_or_else(|| point_bounds(&record.point).expect("point bounds"));
                if !bounds.overlaps(&record_bounds)? {
                    self.report.spatial_false_positive_rows += 1;
                    continue;
                }
            }
            if let Some(distance_filter) = distance_filter {
                if !distance_filter.matches(origin_point.distance_squared(&record.point)?) {
                    continue;
                }
            } else if let Some(exact_filter) = relation.exact_filter {
                let mut joined = ctx.clone();
                joined
                    .bindings
                    .insert(relation.item_query.clone(), record.entity);
                if !truthy(&self.eval_expr(exact_filter, &joined)?)? {
                    continue;
                }
            }
            self.report.rows_scanned += 1;
            self.report.spatial_exact_rows += 1;
            records.push(record);
        }
        if let Some(start) = filter_start {
            self.profile_spatial_filter_nanos += start.elapsed().as_nanos();
        }
        Ok(records)
    }

    fn persist_spatial_index_cache(&mut self) {
        for (index_id, index) in self.spatial_indexes.drain() {
            let Some((signature, structural_revision, field_revision)) =
                self.spatial_index_metadata.remove(&index_id)
            else {
                continue;
            };
            self.world.store_spatial_index_cache(
                index_id,
                CachedSpatialIndex {
                    index,
                    signature,
                    structural_revision,
                    field_revision,
                },
            );
        }
    }

    fn report_algorithm_use(&mut self, index: &BuiltSpatialIndex) {
        match index {
            BuiltSpatialIndex::HashGrid(_) | BuiltSpatialIndex::DirectPointHashGrid(_) => {
                self.report.spatial_algorithm_hash_grid += 1
            }
            BuiltSpatialIndex::Quadtree(_) => self.report.spatial_algorithm_quadtree += 1,
            BuiltSpatialIndex::Octree(_) => self.report.spatial_algorithm_octree += 1,
            BuiltSpatialIndex::Hilbert(_) => self.report.spatial_algorithm_hilbert_curve += 1,
        }
    }

    fn spatial_dependency_revision(&self, relation: &SpatialRelationNode) -> u64 {
        let mut dependencies = Vec::new();
        let mut complete = true;
        for expr in &relation.target_position {
            complete &= self.collect_spatial_field_dependencies(
                *expr,
                &relation.item_query,
                &mut dependencies,
                &mut HashSet::new(),
            );
        }
        if let Some(bounds) = &relation.target_bounds {
            for expr in bounds.minimum.iter().chain(bounds.maximum.iter()) {
                complete &= self.collect_spatial_field_dependencies(
                    *expr,
                    &relation.item_query,
                    &mut dependencies,
                    &mut HashSet::new(),
                );
            }
        }
        if complete && !dependencies.is_empty() {
            dependencies
                .iter()
                .map(|(component, field)| self.world.component_field_revision(component, field))
                .max()
                .unwrap_or(0)
        } else {
            self.world.field_revision()
        }
    }

    fn collect_spatial_field_dependencies(
        &self,
        expr_index: usize,
        query_name: &str,
        dependencies: &mut Vec<(String, String)>,
        visiting: &mut HashSet<usize>,
    ) -> bool {
        if !visiting.insert(expr_index) {
            return true;
        }
        let complete = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_) => true,
            ExprNode::Field {
                query,
                component,
                field,
            } if query == query_name => {
                dependencies.push((component.clone(), field.clone()));
                true
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.collect_spatial_field_dependencies(*input, query_name, dependencies, visiting)
            }
            ExprNode::Binary { left, right, .. } => {
                self.collect_spatial_field_dependencies(*left, query_name, dependencies, visiting)
                    & self.collect_spatial_field_dependencies(
                        *right,
                        query_name,
                        dependencies,
                        visiting,
                    )
            }
            _ => false,
        };
        visiting.remove(&expr_index);
        complete
    }

    fn spatial_index_signature(&self, relation: &SpatialRelationNode) -> String {
        format!(
            "{};item_query_fingerprint={}",
            spatial_index_base_signature(relation),
            self.query_fingerprint(&relation.item_query)
        )
    }

    fn spatial_index_cache_key(&self, relation: &SpatialRelationNode) -> String {
        format!(
            "{}|{}",
            relation.index_id,
            self.spatial_index_signature(relation)
        )
    }

    fn query_fingerprint(&self, query_name: &str) -> u64 {
        let mut hasher = DefaultHasher::new();
        query_name.hash(&mut hasher);
        if let Some(query) = self
            .plan
            .queries
            .iter()
            .find(|query| query.name == query_name)
        {
            query.filter.hash(&mut hasher);
            query.allowed_entities.hash(&mut hasher);
        }
        hasher.finish()
    }

    fn take_fresh_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Option<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let Some(cached) = self.world.take_spatial_index_cache(&index_key) else {
            return None;
        };
        if cached.signature == signature
            && cached.structural_revision == structural_revision
            && cached.field_revision == field_revision
        {
            self.report.spatial_index_reuses += 1;
            self.spatial_index_metadata
                .insert(index_key, (signature, structural_revision, field_revision));
            return Some(cached.index);
        }
        self.world.store_spatial_index_cache(index_key, cached);
        None
    }

    fn build_or_update_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        records: Vec<SpatialRecord>,
    ) -> Result<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let index = if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
            if cached.signature == signature {
                if cached.structural_revision == structural_revision
                    && cached.field_revision == field_revision
                {
                    self.report.spatial_index_reuses += 1;
                    self.spatial_index_metadata
                        .insert(index_key, (signature, structural_revision, field_revision));
                    return Ok(cached.index);
                }
                if should_try_incremental_spatial_update(
                    records.len(),
                    cached.field_revision,
                    field_revision,
                ) {
                    if cached.index.update_incremental(&records)? {
                        self.report.spatial_index_incremental_updates += 1;
                    } else {
                        self.report.spatial_indexes_built += 1;
                        self.report.spatial_index_full_rebuilds += 1;
                    }
                } else {
                    cached.index.build(&records)?;
                    self.report.spatial_indexes_built += 1;
                    self.report.spatial_index_full_rebuilds += 1;
                }
                cached.index
            } else {
                let mut index = build_spatial_index(&relation.algorithm)?;
                index.build(&records)?;
                self.report.spatial_indexes_built += 1;
                self.report.spatial_index_full_rebuilds += 1;
                index
            }
        } else {
            let mut index = build_spatial_index(&relation.algorithm)?;
            index.build(&records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            index
        };
        self.spatial_index_metadata
            .insert(index_key, (signature, structural_revision, field_revision));
        Ok(index)
    }

    fn ensure_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<&BuiltSpatialIndex> {
        let index_key = self.spatial_index_cache_key(relation);
        if self.spatial_indexes.contains_key(&index_key) {
            self.report.spatial_index_reuses += 1;
        } else if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        } else {
            let records = self.build_spatial_records(relation, ctx)?;
            let index = self.build_or_update_spatial_index(relation, records)?;
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        }
        self.spatial_indexes.get(&index_key).ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial index '{}' was not built",
                relation.index_id
            ))
        })
    }

    fn build_spatial_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Vec<SpatialRecord>> {
        let rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let mut records = Vec::with_capacity(rows.len());
        for entity in rows {
            let mut item_ctx = ctx.clone();
            item_ctx
                .bindings
                .insert(relation.item_query.clone(), entity);
            let point = self.eval_spatial_point(&relation.target_position, &item_ctx)?;
            let bounds = relation
                .target_bounds
                .as_ref()
                .map(|bounds| self.eval_spatial_bounds(bounds, &item_ctx))
                .transpose()?;
            records.push(SpatialRecord {
                entity,
                point,
                bounds,
            });
        }
        Ok(records)
    }

    fn eval_spatial_point(&mut self, coords: &[usize], ctx: &EvalContext) -> Result<SpatialPoint> {
        let values = coords
            .iter()
            .map(|expr| {
                self.eval_expr(*expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .collect::<Result<Vec<_>>>()?;
        match values.as_slice() {
            [x, y] => SpatialPoint::point2(*x, *y),
            [x, y, z] => SpatialPoint::point3(*x, *y, *z),
            _ => Err(EcsError::InvalidPlan(
                "spatial points must have 2 or 3 coordinates".to_string(),
            )),
        }
    }

    fn eval_spatial_bounds(
        &mut self,
        bounds: &SpatialBoundsExprNode,
        ctx: &EvalContext,
    ) -> Result<SpatialAabb> {
        let minimum = self.eval_spatial_point(&bounds.minimum, ctx)?;
        let maximum = self.eval_spatial_point(&bounds.maximum, ctx)?;
        SpatialAabb::new(minimum, maximum)
    }

    fn expr_queries_cached(
        &self,
        expr_index: usize,
        cache: &mut HashMap<usize, BTreeSet<String>>,
    ) -> Result<BTreeSet<String>> {
        if let Some(queries) = cache.get(&expr_index) {
            return Ok(queries.clone());
        }
        let mut out = BTreeSet::new();
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                out.extend(self.expr_queries_cached(*input, cache)?);
            }
            ExprNode::Binary { left, right, .. } => {
                out.extend(self.expr_queries_cached(*left, cache)?);
                out.extend(self.expr_queries_cached(*right, cache)?);
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                out.extend(self.expr_queries_cached(*predicate, cache)?);
            }
            ExprNode::Exists { query, predicate } => {
                out.extend(self.expr_queries_cached(*predicate, cache)?);
                out.remove(query);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        cache.insert(expr_index, out.clone());
        Ok(out)
    }

    fn collect_expr_queries(&self, expr_index: usize, out: &mut BTreeSet<String>) -> Result<()> {
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Attribute { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Binary { left, right, .. } => {
                self.collect_expr_queries(*left, out)?;
                self.collect_expr_queries(*right, out)?;
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                self.collect_expr_queries(*predicate, out)?;
            }
            ExprNode::Exists { query, predicate } => {
                let mut inner = BTreeSet::new();
                self.collect_expr_queries(*predicate, &mut inner)?;
                inner.remove(query);
                out.extend(inner);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        Ok(())
    }
}

fn fast_field_array_value(array: &FastFieldArray, entity: Entity) -> Result<f64> {
    let Some(Some((generation, value))) = array.values.get(entity.index as usize) else {
        return Err(EcsError::InvalidPlan(format!(
            "missing cached f64 value for entity {}:{} field {}.{}",
            entity.index, entity.generation, array.component, array.field
        )));
    };
    if *generation != entity.generation {
        return Err(EcsError::InvalidPlan(format!(
            "fast numeric field array has stale entity generation for {}:{}",
            entity.index, entity.generation
        )));
    };
    Ok(*value)
}

fn fast_field_array_record_values(
    array: &FastFieldArray,
    records: &[DirectPointRecord],
) -> Result<Vec<f64>> {
    records
        .iter()
        .map(|record| fast_field_array_value(array, record.entity))
        .collect()
}

fn point_from_row_arrays(arrays: &[Vec<f64>], row_index: usize) -> Result<SpatialPoint> {
    let row_value = |values: &Vec<f64>| -> Result<f64> {
        values.get(row_index).copied().ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial coordinate cache missing query row {row_index}"
            ))
        })
    };
    match arrays {
        [x, y] => SpatialPoint::point2(row_value(x)?, row_value(y)?),
        [x, y, z] => SpatialPoint::point3(row_value(x)?, row_value(y)?, row_value(z)?),
        _ => Err(EcsError::InvalidPlan(
            "spatial points must have 2 or 3 coordinates".to_string(),
        )),
    }
}

fn fast_aggregate_kind(kind: &str) -> Option<FastAggregateKind> {
    match kind {
        "any" => Some(FastAggregateKind::Any),
        "count" => Some(FastAggregateKind::Count),
        "sum" => Some(FastAggregateKind::Sum),
        "mean" => Some(FastAggregateKind::Mean),
        "min" => Some(FastAggregateKind::Min),
        "max" => Some(FastAggregateKind::Max),
        _ => None,
    }
}

fn spatial_result_values_are_dense(batches: &[FastDirectSpatialRelationBatch]) -> bool {
    batches.iter().all(|batch| {
        batch.specs.iter().all(|spec| {
            matches!(
                spec.kind,
                FastAggregateKind::Any | FastAggregateKind::Count | FastAggregateKind::Sum
            )
        })
    })
}

fn query_rows_for_plan(
    world: &mut World,
    plan: &PhysicalPlan,
) -> Result<(QueryRows, QueryIndices)> {
    let mut query_rows = QueryRows::new();
    let mut query_indices = QueryIndices::new();
    for (query_index, query) in plan.queries.iter().enumerate() {
        query_indices.insert(query.name.clone(), query_index);
        query_rows.insert(
            query.name.clone(),
            query_rows_for_world(world, plan, &query.name)?,
        );
    }
    Ok((query_rows, query_indices))
}

fn query_rows_for_world(
    world: &mut World,
    plan: &PhysicalPlan,
    query_name: &str,
) -> Result<Vec<Entity>> {
    let query = plan
        .queries
        .iter()
        .find(|query| query.name == query_name)
        .ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
    let mut rows = world.query_filter(query.filter.clone())?;
    if let Some(allowed) = &query.allowed_entities {
        let allowed = allowed
            .iter()
            .map(|entity| entity.raw())
            .collect::<HashSet<_>>();
        rows.retain(|entity| allowed.contains(&entity.raw()));
    }
    Ok(rows)
}

fn process_fast_spatial_record(
    relation: &SpatialRelationNode,
    batches: &[FastDirectSpatialRelationBatch],
    item_field_arrays: &[FastFieldArray],
    item_record_field_arrays: Option<&[Vec<f64>]>,
    origin_entity: Entity,
    origin_point: &SpatialPoint,
    record_index: Option<usize>,
    record_entity: Entity,
    record_point: &SpatialPoint,
    distance_sq: f64,
    accumulators: &mut [Vec<SpatialBatchAccum>],
    exact_counts: &mut [usize],
    counters: &mut SpatialLocalCounters,
) -> Result<()> {
    counters.candidate_rows += 1;
    if !relation.include_self && record_entity == origin_entity {
        return Ok(());
    }
    if relation.pair_policy == "unique_unordered" && record_entity.raw() <= origin_entity.raw() {
        counters.deduplicated_pairs += 1;
        return Ok(());
    }
    for (batch_index, batch) in batches.iter().enumerate() {
        if distance_sq > batch.query_radius_sq {
            continue;
        }
        if let Some(distance_filter) = batch.distance_filter {
            if !distance_filter.matches(distance_sq) {
                continue;
            }
        }
        exact_counts[batch_index] += 1;
        counters.rows_scanned += 1;
        counters.exact_rows += 1;
        let mut inverse_distance_cache: Option<(f64, f64)> = None;
        for (spec_index, spec) in batch.specs.iter().enumerate() {
            if matches!(spec.kind, FastAggregateKind::Any | FastAggregateKind::Count) {
                continue;
            }
            let value = match &spec.value {
                FastSpatialBatchValue::Count => 1.0,
                FastSpatialBatchValue::DirectField { array_index } => {
                    if let (Some(record_arrays), Some(record_index)) =
                        (item_record_field_arrays, record_index)
                    {
                        record_arrays[*array_index][record_index]
                    } else {
                        fast_field_array_value(&item_field_arrays[*array_index], record_entity)?
                    }
                }
                FastSpatialBatchValue::DirectPointCoord { axis } => record_point.coord(*axis),
                FastSpatialBatchValue::NegDeltaOverDistance {
                    axis,
                    minimum_distance,
                } => {
                    let inverse_distance = match inverse_distance_cache {
                        Some((cached_minimum, value)) if cached_minimum == *minimum_distance => {
                            value
                        }
                        _ => {
                            let value = 1.0 / distance_sq.sqrt().max(*minimum_distance);
                            inverse_distance_cache = Some((*minimum_distance, value));
                            value
                        }
                    };
                    let delta_axis = record_point.coord(*axis) - origin_point.coord(*axis);
                    -delta_axis * inverse_distance
                }
            };
            let accumulator = &mut accumulators[batch_index][spec_index];
            match spec.kind {
                FastAggregateKind::Sum => {
                    accumulator.sum += value;
                }
                FastAggregateKind::Mean => {
                    accumulator.count += 1;
                    accumulator.sum += value;
                }
                FastAggregateKind::Min => {
                    accumulator.count += 1;
                    accumulator.min = accumulator.min.min(value);
                }
                FastAggregateKind::Max => {
                    accumulator.count += 1;
                    accumulator.max = accumulator.max.max(value);
                }
                FastAggregateKind::Any | FastAggregateKind::Count => {}
            }
        }
    }
    Ok(())
}

fn aggregate_empty(
    kind: &str,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if let Some(default_expr) = default {
        return executor.eval_expr(default_expr, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(false)),
        "count" => Ok(EcsValue::I64(0)),
        "sum" => Ok(EcsValue::F64(0.0)),
        "min" | "max" | "mean" => Err(EcsError::InvalidPlan(format!(
            "{kind} aggregate is empty and no default was provided"
        ))),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn aggregate_finish(
    kind: &str,
    count: usize,
    values: Vec<EcsValue>,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if count == 0 && matches!(kind, "min" | "max" | "mean") {
        return aggregate_empty(kind, default, executor, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(count > 0)),
        "count" => Ok(EcsValue::I64(count as i64)),
        "sum" => Ok(EcsValue::F64(
            values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum(),
        )),
        "min" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("min aggregate has no values".to_string()))?;
            for value in iter {
                best = best.min(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "max" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("max aggregate has no values".to_string()))?;
            for value in iter {
                best = best.max(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "mean" => {
            if values.is_empty() {
                return aggregate_empty(kind, default, executor, ctx);
            }
            let sum = values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum::<f64>();
            Ok(EcsValue::F64(sum / values.len() as f64))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn dimensions_from_u8(dimensions: u8) -> Result<Dimensions> {
    match dimensions {
        2 => Ok(Dimensions::D2),
        3 => Ok(Dimensions::D3),
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn dimensions_len(dimensions: u8) -> Result<usize> {
    Ok(dimensions_from_u8(dimensions)?.len())
}

fn point_bounds(point: &SpatialPoint) -> Result<SpatialAabb> {
    SpatialAabb::new(point.clone(), point.clone())
}

fn direct_distance_squared(left: &SpatialPoint, right: &SpatialPoint, dimensions: usize) -> f64 {
    let mut distance_sq = 0.0;
    for axis in 0..dimensions {
        let delta = right.coord(axis) - left.coord(axis);
        distance_sq += delta * delta;
    }
    distance_sq
}

fn should_try_incremental_spatial_update(
    record_count: usize,
    previous_field_revision: u64,
    current_field_revision: u64,
) -> bool {
    let changed_field_writes = current_field_revision.saturating_sub(previous_field_revision);
    let incremental_write_budget = (record_count / 4).max(1) as u64;
    changed_field_writes <= incremental_write_budget
}

fn spatial_index_base_signature(relation: &SpatialRelationNode) -> String {
    format!(
        "item={};target_pos={:?};target_bounds={:?};algorithm={:?}",
        relation.item_query, relation.target_position, relation.target_bounds, relation.algorithm
    )
}

fn spatial_relations_same_direct_precompute_group(
    left: &SpatialRelationNode,
    right: &SpatialRelationNode,
) -> bool {
    left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.origin_position == right.origin_position
        && left.target_position == right.target_position
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn spatial_relations_same_multi_origin_precompute_group(
    left: &SpatialRelationNode,
    right: &SpatialRelationNode,
) -> bool {
    left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.target_position == right.target_position
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn spatial_relations_same_base(left: &SpatialRelationNode, right: &SpatialRelationNode) -> bool {
    left.id == right.id
        && left.index_id == right.index_id
        && left.origin_query == right.origin_query
        && left.item_query == right.item_query
        && left.origin_position == right.origin_position
        && left.target_position == right.target_position
        && left.radius == right.radius
        && left.origin_bounds == right.origin_bounds
        && left.target_bounds == right.target_bounds
        && left.algorithm == right.algorithm
        && left.include_self == right.include_self
        && left.pair_policy == right.pair_policy
}

fn bounds_from_values(dimensions: u8, values: &[f64]) -> Result<SpatialAabb> {
    match dimensions {
        2 => {
            if values.len() != 4 {
                return Err(EcsError::InvalidPlan(
                    "2D spatial bounds require four values".to_string(),
                ));
            }
            SpatialAabb::point2(values[0], values[1], values[2], values[3])
        }
        3 => {
            if values.len() != 6 {
                return Err(EcsError::InvalidPlan(
                    "3D spatial bounds require six values".to_string(),
                ));
            }
            SpatialAabb::point3(
                values[0], values[1], values[2], values[3], values[4], values[5],
            )
        }
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn build_spatial_index(algorithm: &crate::plan::SpatialAlgorithmNode) -> Result<BuiltSpatialIndex> {
    let dimensions = dimensions_from_u8(algorithm.dimensions)?;
    match algorithm.kind.as_str() {
        "hash_grid" => Ok(BuiltSpatialIndex::HashGrid(HashGridIndex::new(
            dimensions,
            algorithm.cell_size.unwrap_or(1.0),
        )?)),
        "quadtree" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "quadtree spatial algorithm requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("quadtree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Quadtree(QuadtreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "octree" => {
            if dimensions != Dimensions::D3 {
                return Err(EcsError::InvalidPlan(
                    "octree spatial algorithm requires 3D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                3,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("octree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Octree(OctreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "hilbert_curve" | "hilbert" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "Hilbert spatial algorithm currently requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("Hilbert spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Hilbert(HilbertIndex::new(
                bounds,
                algorithm.bits.unwrap_or(16),
            )?))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported spatial algorithm '{other}'"
        ))),
    }
}

#[cfg(test)]
mod tests;
