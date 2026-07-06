use std::collections::{HashMap, HashSet};
use std::time::Instant;

use rayon::prelude::*;

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::plan::{BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle};
use crate::scheduler::install_on_ecs_worker_pool;
use crate::schema::StorageType;
use crate::world::World;

use super::access_analysis::{
    collect_action_query_access, query_access_conflicts, QueryAccessSummary,
};
use super::query_context::{query_rows_for_plan, query_rows_for_world};
use super::spatial_support::SpatialPrecomputeLayout;
use super::value_ops::coerce_value_for_storage;
use super::{EvalContext, ExecutionReport, PlanExecutor};

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
