use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Instant;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::typed_ir::PairPolicy;
use crate::plan::{
    BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle, PreparedPlan, SpatialRelationNode,
};
use crate::scheduler::install_on_ecs_worker_pool;
use crate::schema::StorageType;
use crate::spatial::SpatialRecord;
use crate::world::World;

use super::access_analysis::{
    collect_action_query_access, query_access_conflicts, QueryAccessSummary,
};
use super::interpreter::query_context::{query_rows_for_plan, query_rows_for_world};
use super::interpreter::value_ops::coerce_value_for_storage;
use super::report::ExecutionReport;
use super::spatial::support::{
    BuiltSpatialIndex, SpatialBatchSpec, SpatialF64RowArray, SpatialPrecomputeLayout,
};
use super::{TypedExecutorPlan, TypedExpr, TypedSpatialRelation};

#[derive(Debug, Clone, Default, PartialEq)]
pub(in crate::execution) struct EvalContext {
    pub(in crate::execution) bindings: Vec<Option<Entity>>,
    pub(in crate::execution) loop_items: Vec<Option<EcsValue>>,
}

impl EvalContext {
    pub(in crate::execution) fn new(query_slots: usize, loop_slots: usize) -> Self {
        Self {
            bindings: vec![None; query_slots],
            loop_items: vec![None; loop_slots],
        }
    }

    pub(in crate::execution) fn with_binding(&self, slot: usize, entity: Entity) -> Self {
        let mut next = self.clone();
        next.bindings[slot] = Some(entity);
        next
    }

    pub(in crate::execution) fn has_bindings(&self) -> bool {
        self.bindings.iter().any(Option::is_some)
    }

    pub(in crate::execution) fn has_loop_items(&self) -> bool {
        self.loop_items.iter().any(Option::is_some)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(in crate::execution) enum WriteKey {
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
pub(in crate::execution) enum ExprCacheKey {
    Empty(usize),
    One(usize, usize, u64),
    Many(usize, Vec<(usize, u64)>),
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct DirectF64SetSpec {
    pub(in crate::execution) query: String,
    pub(in crate::execution) component: String,
    pub(in crate::execution) field: String,
    pub(in crate::execution) value_expr: usize,
}

pub(in crate::execution) type QueryRows = HashMap<String, Arc<Vec<Entity>>>;
pub(in crate::execution) type QueryIndices = HashMap<String, usize>;
pub(in crate::execution) type QueryLocationCache = HashMap<String, Arc<Vec<(usize, usize)>>>;
type SpatialIndexMetadata = HashMap<String, (String, u64, u64)>;
type SpatialRelationCacheKey = (String, Option<usize>, Option<usize>, bool, String, u64);
type SpatialRelationCache = HashMap<SpatialRelationCacheKey, Arc<Vec<SpatialRecord>>>;
type NumericFieldCache = HashMap<String, HashMap<String, HashMap<Entity, f64>>>;
type NumericFieldRowCache = HashMap<String, HashMap<String, Vec<f64>>>;
type SpatialBatchSpecCache = HashMap<(String, Option<usize>, Option<usize>), Vec<SpatialBatchSpec>>;
type SparseSpatialF64Cache = HashMap<usize, HashMap<Entity, f64>>;
type RowSpatialF64Cache = HashMap<usize, SpatialF64RowArray>;

pub(in crate::execution) struct PlanExecutor<'a> {
    // Plan and query state.
    pub(in crate::execution) world: &'a mut World,
    pub(in crate::execution) prepared: &'a PreparedPlan,
    pub(in crate::execution) plan: &'a PhysicalPlan,
    pub(in crate::execution) typed_plan: &'a TypedExecutorPlan,
    pub(in crate::execution) query_rows: QueryRows,
    pub(in crate::execution) query_indices: QueryIndices,
    pub(in crate::execution) query_location_cache: QueryLocationCache,

    // Execution output.
    pub(in crate::execution) report: ExecutionReport,
    pub(in crate::execution) report_writes: bool,

    // Spatial index and precomputation state.
    pub(in crate::execution) spatial_indexes: HashMap<String, BuiltSpatialIndex>,
    pub(in crate::execution) spatial_index_metadata: SpatialIndexMetadata,
    pub(in crate::execution) spatial_relation_cache: SpatialRelationCache,
    // Expression and numeric field caches.
    pub(in crate::execution) expr_cache: HashMap<ExprCacheKey, EcsValue>,
    pub(in crate::execution) local_expr_cache: Option<Vec<Option<EcsValue>>>,
    pub(in crate::execution) local_expr_bindings: Option<Vec<Option<Entity>>>,
    pub(in crate::execution) numeric_field_cache_enabled: bool,
    pub(in crate::execution) numeric_field_cache: NumericFieldCache,
    pub(in crate::execution) numeric_field_cache_rows: NumericFieldRowCache,
    pub(in crate::execution) spatial_batch_spec_cache: SpatialBatchSpecCache,
    pub(in crate::execution) spatial_precomputed_f64: SparseSpatialF64Cache,
    pub(in crate::execution) spatial_precomputed_f64_rows: RowSpatialF64Cache,

    // Optional profiling counters.
    pub(in crate::execution) profile: bool,
    pub(in crate::execution) profile_eval_calls: usize,
    pub(in crate::execution) profile_expr_cache_hits: usize,
    pub(in crate::execution) profile_expr_cache_misses: usize,
    pub(in crate::execution) profile_spatial_relation_hits: usize,
    pub(in crate::execution) profile_spatial_relation_misses: usize,
    pub(in crate::execution) profile_spatial_index_nanos: u128,
    pub(in crate::execution) profile_spatial_query_nanos: u128,
    pub(in crate::execution) profile_spatial_filter_nanos: u128,
    pub(in crate::execution) profile_direct_aggregate_nanos: u128,
    pub(in crate::execution) profile_direct_aggregate_hits: usize,
}

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn new(
        world: &'a mut World,
        prepared: &'a PreparedPlan,
        query_rows: QueryRows,
        query_indices: QueryIndices,
        query_location_cache: QueryLocationCache,
        report_writes: bool,
        profile: bool,
    ) -> Self {
        Self {
            world,
            prepared,
            plan: prepared.plan(),
            typed_plan: prepared.typed_executor(),
            query_rows,
            query_indices,
            query_location_cache,
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

    pub(in crate::execution) fn typed_expr(&self, index: usize) -> TypedExpr {
        self.typed_plan.expression(index)
    }

    pub(in crate::execution) fn query_slot(&self, query: &str) -> Result<usize> {
        self.prepared
            .query_slot(query)
            .map(|slot| slot.0)
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{query}' is not part of the plan"))
            })
    }

    pub(in crate::execution) fn bound_entity(
        &self,
        ctx: &EvalContext,
        query: &str,
    ) -> Result<Entity> {
        let slot = self.query_slot(query)?;
        ctx.bindings
            .get(slot)
            .copied()
            .flatten()
            .ok_or_else(|| EcsError::InvalidPlan(format!("query '{query}' is not bound")))
    }

    pub(in crate::execution) fn query_is_bound(
        &self,
        ctx: &EvalContext,
        query: &str,
    ) -> Result<bool> {
        let slot = self.query_slot(query)?;
        Ok(ctx.bindings.get(slot).is_some_and(Option::is_some))
    }

    pub(in crate::execution) fn coerce_plan_field_value(
        &self,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<EcsValue> {
        let storage_type = self.world.storage_type_for_field(component, field)?;
        let value = match (storage_type, value) {
            (
                StorageType::Int8 | StorageType::Int16 | StorageType::Int32 | StorageType::Int64,
                EcsValue::F64(value),
            ) if value.is_finite()
                && value.fract() == 0.0
                && (-9_223_372_036_854_775_808.0..9_223_372_036_854_775_808.0).contains(&value) =>
            {
                EcsValue::I64(value as i64)
            }
            (
                StorageType::UInt8
                | StorageType::UInt16
                | StorageType::UInt32
                | StorageType::UInt64,
                EcsValue::F64(value),
            ) if value.is_finite()
                && value.fract() == 0.0
                && (0.0..18_446_744_073_709_551_616.0).contains(&value) =>
            {
                EcsValue::U64(value as u64)
            }
            (_, value) => value,
        };
        self.world
            .coerce_value_for_component_field(component, field, value)
    }

    pub(in crate::execution) fn typed_spatial_relation(
        &self,
        relation: &SpatialRelationNode,
    ) -> TypedSpatialRelation {
        self.typed_plan.spatial_relation(self.plan, relation)
    }

    pub(in crate::execution) fn unique_unordered_pairs(
        &self,
        relation: &SpatialRelationNode,
    ) -> bool {
        self.typed_spatial_relation(relation).pair_policy == PairPolicy::UniqueUnordered
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
        let prepared = self.validated_compiled_plan(handle)?;
        self.execute_prepared_plan_with_options(prepared.as_ref(), include_writes)
    }

    pub fn execute_compiled_plans_sequential_with_options(
        &mut self,
        handles: &[PhysicalPlanHandle],
        include_writes: bool,
    ) -> Result<Vec<ExecutionReport>> {
        if handles.is_empty() {
            return Ok(Vec::new());
        }
        let plans = handles
            .iter()
            .map(|handle| self.validated_compiled_plan(*handle))
            .collect::<Result<Vec<_>>>()?;
        install_on_ecs_worker_pool(|| {
            let mut reports = Vec::with_capacity(plans.len());
            for prepared in plans {
                reports
                    .push(self.execute_plan_with_options_inner(prepared.as_ref(), include_writes)?);
            }
            Ok(reports)
        })
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
            return self.execute_compiled_plans_sequential_with_options(handles, include_writes);
        }
        let plans = handles
            .iter()
            .map(|handle| self.validated_compiled_plan(*handle))
            .collect::<Result<Vec<_>>>()?;
        let access = plans
            .iter()
            .map(|prepared| self.query_access_summary(prepared.plan()))
            .collect::<Result<Vec<_>>>()?;
        let mut query_sets: HashMap<(usize, String), HashSet<u64>> = HashMap::new();
        for (plan_index, prepared) in plans.iter().enumerate() {
            let plan = prepared.plan();
            for query in &plan.queries {
                let rows = query_rows_for_world(self, plan, &query.name)?;
                query_sets.insert(
                    (plan_index, query.name.clone()),
                    rows.iter().map(|entity| entity.raw()).collect(),
                );
            }
        }

        let mut waves: Vec<Vec<usize>> = Vec::new();
        let mut current = Vec::new();
        for plan_index in 0..plans.len() {
            let conflicts = current.iter().any(|other| {
                query_access_conflicts(
                    &access[*other],
                    *other,
                    &access[plan_index],
                    plan_index,
                    &query_sets,
                )
            });
            if conflicts && !current.is_empty() {
                waves.push(std::mem::take(&mut current));
            }
            current.push(plan_index);
        }
        if !current.is_empty() {
            waves.push(current);
        }

        self.note_schedule_waves(waves.len(), plans.len());
        let mut reports_by_index: Vec<Option<ExecutionReport>> = vec![None; plans.len()];
        for wave in waves {
            // A wave contains no read/write overlap. Executing its plans in stable
            // order against the canonical world therefore has the same result as
            // snapshot execution while avoiding whole-world clones. Row-level
            // chunk parallelism remains inside the typed executor.
            for plan_index in wave {
                let report =
                    self.execute_prepared_plan_with_options(plans[plan_index].as_ref(), false)?;
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
        &mut self,
        handle: PhysicalPlanHandle,
    ) -> Result<std::sync::Arc<PreparedPlan>> {
        let prepared = self.compiled_prepared_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if prepared.plan().schema_fingerprint != current_schema_fingerprint
            || prepared.schema_version() != self.schema_version()
        {
            self.note_plan_schema_invalidation();
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {} at version {}, \
                 but the world schema fingerprint is {} at version {}; recompile the plan",
                prepared.plan().schema_fingerprint,
                prepared.schema_version(),
                current_schema_fingerprint,
                self.schema_version(),
            )));
        }
        Ok(prepared)
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

    pub fn warm_compiled_plan_spatial_indexes(
        &mut self,
        handle: PhysicalPlanHandle,
    ) -> Result<ExecutionReport> {
        let prepared = self.validated_compiled_plan(handle)?;
        if prepared.spatial_cache_keys().is_empty() {
            return Ok(ExecutionReport::default());
        }
        self.warm_prepared_plan_spatial_indexes(prepared.as_ref())
    }

    pub fn execute_plan(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        self.execute_plan_with_options(plan, true)
    }

    pub fn execute_plan_with_options(
        &mut self,
        plan: &PhysicalPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let prepared = PreparedPlan::compile(plan.clone(), self.schema_registry())?;
        self.execute_prepared_plan_with_options(&prepared, include_writes)
    }

    fn execute_prepared_plan_with_options(
        &mut self,
        prepared: &PreparedPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| {
            self.execute_plan_with_options_inner(prepared, include_writes)
        })
    }

    pub fn warm_plan_spatial_indexes(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        let prepared = PreparedPlan::compile(plan.clone(), self.schema_registry())?;
        self.warm_prepared_plan_spatial_indexes(&prepared)
    }

    fn warm_prepared_plan_spatial_indexes(
        &mut self,
        prepared: &PreparedPlan,
    ) -> Result<ExecutionReport> {
        install_on_ecs_worker_pool(|| self.warm_plan_spatial_indexes_inner(prepared))
    }

    fn warm_plan_spatial_indexes_inner(
        &mut self,
        prepared: &PreparedPlan,
    ) -> Result<ExecutionReport> {
        let (query_rows, query_indices, query_locations) = query_rows_for_plan(self, prepared)?;
        let mut executor = PlanExecutor::new(
            self,
            prepared,
            query_rows,
            query_indices,
            query_locations,
            false,
            false,
        );
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
        prepared: &PreparedPlan,
        include_writes: bool,
    ) -> Result<ExecutionReport> {
        let plan = prepared.plan();
        self.note_fixed_slot_execution();
        let profile = std::env::var_os("GUMMY_ECS_PROFILE").is_some();
        let total_start = profile.then(Instant::now);
        let query_start = profile.then(Instant::now);
        let (query_rows, query_indices, query_locations) = query_rows_for_plan(self, prepared)?;
        if let Some(start) = query_start {
            eprintln!(
                "ecs_profile execute_query_prep elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let mut executor = PlanExecutor::new(
            self,
            prepared,
            query_rows,
            query_indices,
            query_locations,
            include_writes,
            profile,
        );
        let execute_result = executor.execute_action(
            plan.root_action,
            &[EvalContext::new(
                prepared.query_slot_count(),
                prepared.loop_slot_count(),
            )],
        );
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
