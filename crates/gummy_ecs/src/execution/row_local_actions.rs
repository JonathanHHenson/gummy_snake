use std::collections::{HashMap, HashSet};
use std::time::Instant;

use rayon::prelude::*;

use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, ExprNode};

use super::f64_program::{
    build_row_local_field_dependents, compile_f64_readonly_program, compiled_field_f64_value,
    execute_row_local_f64_action, invalidate_row_local_f64_cache, CompiledF64ReadOnlyProgram,
    RowLocalAction, RowLocalTarget,
};
use super::{storage_type_is_numeric, EvalContext, PlanExecutor, SpatialPrecomputeLayout};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn row_local_numeric_action_query(
        &self,
        action_index: usize,
        contexts: &[EvalContext],
    ) -> Option<String> {
        if contexts.len() != 1
            || !contexts[0].bindings.is_empty()
            || !contexts[0].loop_items.is_empty()
        {
            return None;
        }
        if !self.action_contains_when(action_index) {
            return None;
        }
        let mut query_name = None;
        if self.row_local_numeric_action_supported(action_index, &mut query_name) {
            query_name
        } else {
            None
        }
    }

    fn action_contains_when(&self, action_index: usize) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::When { .. } => true,
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => children
                .iter()
                .any(|child| self.action_contains_when(*child)),
            ActionNode::ForEach { action, .. } => self.action_contains_when(*action),
            ActionNode::Noop
            | ActionNode::SetField { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::Udf { .. } => false,
        }
    }

    fn row_local_numeric_action_supported(
        &self,
        action_index: usize,
        query_name: &mut Option<String>,
    ) -> bool {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => true,
            ActionNode::Sequence(children) => children
                .iter()
                .all(|child| self.row_local_numeric_action_supported(*child, query_name)),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return false;
                };
                if !self.note_row_local_query(query_name, query) {
                    return false;
                }
                if !self
                    .world
                    .storage_type_for_field(component, field)
                    .is_ok_and(storage_type_is_numeric)
                {
                    return false;
                }
                self.expr_supports_f64(*value, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*value, query)
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                let Some(primary_query) = query_name.as_deref() else {
                    return false;
                };
                self.expr_supports_f64(*condition, &mut HashSet::new())
                    && self.expr_uses_only_row_local_direct_fields(*condition, primary_query)
                    && self.row_local_numeric_action_supported(*then_action, query_name)
                    && otherwise_action.is_none_or(|action| {
                        self.row_local_numeric_action_supported(action, query_name)
                    })
            }
            ActionNode::Parallel(_)
            | ActionNode::ForEach { .. }
            | ActionNode::EmitEvent { .. }
            | ActionNode::AddComponent { .. }
            | ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. }
            | ActionNode::Udf { .. } => false,
        }
    }

    fn note_row_local_query(&self, query_name: &mut Option<String>, candidate: &str) -> bool {
        match query_name {
            Some(existing) => existing == candidate,
            None => {
                *query_name = Some(candidate.to_string());
                true
            }
        }
    }

    fn expr_uses_only_row_local_direct_fields(&self, expr_index: usize, query_name: &str) -> bool {
        self.expr_uses_only_row_local_direct_fields_inner(
            expr_index,
            query_name,
            &mut HashSet::new(),
        )
    }

    fn expr_uses_only_row_local_direct_fields_inner(
        &self,
        expr_index: usize,
        query_name: &str,
        seen: &mut HashSet<usize>,
    ) -> bool {
        if !seen.insert(expr_index) {
            return true;
        }
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::SpatialAggregate { .. } => true,
            ExprNode::Field { query, .. } => query == query_name,
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*input, query_name, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_uses_only_row_local_direct_fields_inner(*left, query_name, seen)
                    && self.expr_uses_only_row_local_direct_fields_inner(*right, query_name, seen)
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. }
            | ExprNode::ContextJoin { .. }
            | ExprNode::Exists { .. }
            | ExprNode::Aggregate { .. }
            | ExprNode::SpatialMetadata { .. } => false,
        }
    }

    fn compile_row_local_action(
        &self,
        action_index: usize,
        query_name: &str,
        program: &CompiledF64ReadOnlyProgram<'_>,
        targets: &mut Vec<RowLocalTarget>,
        target_slots: &mut HashMap<(String, String), usize>,
    ) -> Result<RowLocalAction> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(RowLocalAction::Noop),
            ActionNode::Sequence(children) => children
                .iter()
                .map(|child| {
                    self.compile_row_local_action(
                        *child,
                        query_name,
                        program,
                        targets,
                        target_slots,
                    )
                })
                .collect::<Result<Vec<_>>>()
                .map(RowLocalAction::Sequence),
            ActionNode::SetField { target, value } => {
                let ExprNode::Field {
                    query,
                    component,
                    field,
                } = &self.plan.expressions[*target]
                else {
                    return Err(EcsError::InvalidPlan(
                        "row-local numeric action target must be a field".to_string(),
                    ));
                };
                if query != query_name {
                    return Err(EcsError::InvalidPlan(format!(
                        "row-local numeric action cannot write query '{query}' from primary query '{query_name}'"
                    )));
                }
                let key = (component.clone(), field.clone());
                let field_slot = *program.field_slot_by_key.get(&key).ok_or_else(|| {
                    EcsError::InvalidPlan(format!(
                        "row-local numeric field cache missing target '{component}.{field}'"
                    ))
                })?;
                let target_slot = if let Some(slot) = target_slots.get(&key) {
                    *slot
                } else {
                    let slot = targets.len();
                    target_slots.insert(key, slot);
                    targets.push(RowLocalTarget {
                        component: component.clone(),
                        field: field.clone(),
                    });
                    slot
                };
                Ok(RowLocalAction::SetField {
                    field_slot,
                    target_slot,
                    value_expr: *value,
                })
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => Ok(RowLocalAction::When {
                condition_expr: *condition,
                then_action: Box::new(self.compile_row_local_action(
                    *then_action,
                    query_name,
                    program,
                    targets,
                    target_slots,
                )?),
                otherwise_action: otherwise_action
                    .map(|action| {
                        self.compile_row_local_action(
                            action,
                            query_name,
                            program,
                            targets,
                            target_slots,
                        )
                        .map(Box::new)
                    })
                    .transpose()?,
            }),
            other => Err(EcsError::InvalidPlan(format!(
                "row-local numeric executor does not support action {other:?}"
            ))),
        }
    }

    pub(in crate::execution) fn execute_row_local_numeric_action(
        &mut self,
        action_index: usize,
        query_name: &str,
    ) -> Result<()> {
        let rows = self.query_rows.get(query_name).cloned().ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        if rows.is_empty() {
            return Ok(());
        }

        let precompute_start = self.profile.then(Instant::now);
        self.precompute_direct_spatial_aggregates_for_query(
            query_name,
            SpatialPrecomputeLayout::QueryRows,
        )?;
        if let Some(start) = precompute_start {
            eprintln!(
                "ecs_profile row_local_f64_precompute elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let preload_start = self.profile.then(Instant::now);
        self.preload_numeric_fields_for_query(query_name, SpatialPrecomputeLayout::QueryRows)?;
        if let Some(start) = preload_start {
            eprintln!(
                "ecs_profile row_local_f64_preload elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        let locations = self.query_locations(query_name)?;
        let program = compile_f64_readonly_program(
            self.plan,
            self.world,
            query_name,
            &self.numeric_field_cache,
            &self.numeric_field_cache_rows,
            &self.spatial_precomputed_f64,
            &self.spatial_precomputed_f64_rows,
        );
        let mut targets = Vec::new();
        let mut target_slots = HashMap::new();
        let action = self.compile_row_local_action(
            action_index,
            query_name,
            &program,
            &mut targets,
            &mut target_slots,
        )?;
        let target_count = targets.len();
        if target_count == 0 {
            return Ok(());
        }

        let expr_count = self.plan.expressions.len();
        let field_count = program.field_arrays.len();
        let field_dependents = build_row_local_field_dependents(&program);
        let mut flat_values = vec![0.0; rows.len() * target_count];
        let mut dirty = vec![false; rows.len() * target_count];
        let eval_start = self.profile.then(Instant::now);
        let world = &*self.world;
        flat_values
            .par_chunks_mut(target_count)
            .zip(dirty.par_chunks_mut(target_count))
            .zip(rows.par_iter().enumerate())
            .try_for_each_init(
                || {
                    (
                        vec![0.0; expr_count],
                        vec![0_u32; expr_count],
                        1_u32,
                        vec![0.0; field_count],
                    )
                },
                |(cache_values, cache_marks, cache_generation, field_values),
                 ((out, dirty_row), (row_index, entity))| {
                    invalidate_row_local_f64_cache(cache_marks, cache_generation);
                    for (slot, value) in field_values.iter_mut().enumerate() {
                        *value = compiled_field_f64_value(
                            program.field_arrays[slot],
                            row_index,
                            *entity,
                        )?;
                    }
                    execute_row_local_f64_action(
                        &action,
                        row_index,
                        *entity,
                        &program,
                        world,
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        &field_dependents,
                        out,
                        dirty_row,
                    )
                },
            )?;
        if let Some(start) = eval_start {
            eprintln!(
                "ecs_profile row_local_f64_eval elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        self.report.rows_scanned += rows.len();

        let apply_start = self.profile.then(Instant::now);
        for (target_index, target) in targets.iter().enumerate() {
            let all_dirty = (0..rows.len()).all(|row| dirty[row * target_count + target_index]);
            if all_dirty {
                self.report.fields_written += self.world.set_field_f64_resolved_strided(
                    &target.component,
                    &target.field,
                    &locations,
                    &flat_values,
                    target_index,
                    target_count,
                )?;
                continue;
            }
            let mut writes = Vec::new();
            for (row_index, entity) in rows.iter().enumerate() {
                if dirty[row_index * target_count + target_index] {
                    writes.push((
                        *entity,
                        flat_values[row_index * target_count + target_index],
                    ));
                }
            }
            if !writes.is_empty() {
                self.report.fields_written +=
                    self.world
                        .set_field_f64_many(&target.component, &target.field, &writes)?;
            }
        }
        if let Some(start) = apply_start {
            eprintln!(
                "ecs_profile row_local_f64_apply elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }
}
