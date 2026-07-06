use std::collections::{BTreeSet, HashSet};
use std::time::Instant;

use rayon::prelude::*;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::ExprNode;
use crate::schema::StorageType;

use super::f64_program::{
    compile_f64_readonly_program, compiled_f64_eval_order, eval_compiled_f64_linear_order,
    eval_compiled_f64_readonly,
};
use super::{
    storage_type_is_numeric, DirectF64SetSpec, EvalContext, PlanExecutor, SpatialPrecomputeLayout,
};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn execute_fused_parallel_set_collect_f64_direct(
        &mut self,
        direct_specs: &[DirectF64SetSpec],
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..direct_specs.len())
            .map(|_| Vec::<(Entity, f64)>::new())
            .collect::<Vec<_>>();
        let mut dense_apply: Option<(Vec<Entity>, Vec<(usize, usize)>, Vec<f64>, usize)> = None;
        let mut cache = vec![None; self.plan.expressions.len()];
        let collect_start: Option<Instant>;
        if query_names.len() == 1 {
            let query_name = query_names
                .iter()
                .next()
                .expect("single query name")
                .clone();
            if contexts.len() == 1
                && contexts[0].bindings.is_empty()
                && contexts[0].loop_items.is_empty()
            {
                let precompute_start = self.profile.then(Instant::now);
                self.precompute_direct_spatial_aggregates_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::QueryRows,
                )?;
                if let Some(start) = precompute_start {
                    eprintln!(
                        "ecs_profile direct_f64_precompute elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                collect_start = self.profile.then(Instant::now);
                let preload_start = self.profile.then(Instant::now);
                self.preload_numeric_fields_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::QueryRows,
                )?;
                if let Some(start) = preload_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_preload elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                let rows = self.query_rows.get(&query_name).cloned().ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
                })?;
                let plan = self.plan;
                let numeric_field_cache = &self.numeric_field_cache;
                let numeric_field_cache_rows = &self.numeric_field_cache_rows;
                let spatial_precomputed_f64 = &self.spatial_precomputed_f64;
                let spatial_precomputed_f64_rows = &self.spatial_precomputed_f64_rows;
                let world = &*self.world;
                let compile_start = self.profile.then(Instant::now);
                let compiled = compile_f64_readonly_program(
                    plan,
                    world,
                    &query_name,
                    numeric_field_cache,
                    numeric_field_cache_rows,
                    spatial_precomputed_f64,
                    spatial_precomputed_f64_rows,
                );
                let expr_count = self.plan.expressions.len();
                let spec_count = direct_specs.len();
                let eval_order = compiled_f64_eval_order(
                    &compiled,
                    direct_specs.iter().map(|spec| spec.value_expr),
                );
                if let Some(start) = compile_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_compile elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                if self.profile {
                    eprintln!(
                        "ecs_profile direct_f64_eval linear={} order_len={}",
                        eval_order.is_some(),
                        eval_order.as_ref().map_or(0, Vec::len)
                    );
                }
                let mut flat_values = vec![0.0; rows.len() * spec_count];
                let eval_start = self.profile.then(Instant::now);
                if let Some(eval_order) = eval_order {
                    flat_values
                        .par_chunks_mut(spec_count)
                        .zip(rows.par_iter().enumerate())
                        .try_for_each_init(
                            || {
                                let mut values = vec![0.0; expr_count];
                                for (index, value) in &compiled.initial_values {
                                    values[*index] = *value;
                                }
                                values
                            },
                            |values, (out, (row_index, entity))| {
                                eval_compiled_f64_linear_order(
                                    &eval_order,
                                    row_index,
                                    *entity,
                                    &compiled,
                                    world,
                                    values,
                                )?;
                                for (slot, spec) in direct_specs.iter().enumerate() {
                                    out[slot] = values[compiled.aliases[spec.value_expr]];
                                }
                                Ok::<(), EcsError>(())
                            },
                        )?;
                } else {
                    flat_values
                        .par_chunks_mut(spec_count)
                        .zip(rows.par_iter().enumerate())
                        .try_for_each_init(
                            || vec![None; expr_count],
                            |row_cache, (out, (row_index, entity))| {
                                row_cache.fill(None);
                                for (slot, spec) in direct_specs.iter().enumerate() {
                                    out[slot] = eval_compiled_f64_readonly(
                                        spec.value_expr,
                                        row_index,
                                        *entity,
                                        &compiled,
                                        world,
                                        row_cache,
                                    )?;
                                }
                                Ok::<(), EcsError>(())
                            },
                        )?;
                }
                if let Some(start) = eval_start {
                    eprintln!(
                        "ecs_profile direct_f64_collect_eval elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                self.report.rows_scanned += rows.len();
                let row_locations = self.query_locations(&query_name)?;
                dense_apply = Some((rows, row_locations, flat_values, spec_count));
            } else {
                let precompute_start = self.profile.then(Instant::now);
                self.precompute_direct_spatial_aggregates_for_query(
                    &query_name,
                    SpatialPrecomputeLayout::SparseEntity,
                )?;
                if let Some(start) = precompute_start {
                    eprintln!(
                        "ecs_profile direct_f64_precompute elapsed_ms={:.3}",
                        start.elapsed().as_secs_f64() * 1000.0
                    );
                }
                collect_start = self.profile.then(Instant::now);
                for base_ctx in contexts {
                    if base_ctx.bindings.contains_key(&query_name) {
                        cache.fill(None);
                        self.report.rows_scanned += 1;
                        self.collect_direct_f64_row_writes(
                            direct_specs,
                            base_ctx,
                            &mut cache,
                            &mut child_writes,
                        )?;
                        continue;
                    }
                    let rows = self.query_rows.get(&query_name).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "query '{query_name}' is not part of the plan"
                        ))
                    })?;
                    let mut ctx = base_ctx.clone();
                    for entity in rows {
                        ctx.bindings.insert(query_name.clone(), entity);
                        cache.fill(None);
                        self.report.rows_scanned += 1;
                        self.collect_direct_f64_row_writes(
                            direct_specs,
                            &ctx,
                            &mut cache,
                            &mut child_writes,
                        )?;
                    }
                }
            }
        } else {
            collect_start = self.profile.then(Instant::now);
            for base_ctx in contexts {
                let joined = self.expand_context_for_queries(base_ctx, query_names)?;
                self.report.rows_scanned += joined.len();
                for ctx in joined {
                    cache.fill(None);
                    self.collect_direct_f64_row_writes(
                        direct_specs,
                        &ctx,
                        &mut cache,
                        &mut child_writes,
                    )?;
                }
            }
        }

        if let Some(start) = collect_start {
            eprintln!(
                "ecs_profile direct_f64_collect elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }

        let apply_start = self.profile.then(Instant::now);
        let mut target_slots = Vec::with_capacity(direct_specs.len());
        let mut unique_targets: Vec<(&str, &str)> = Vec::new();
        for spec in direct_specs {
            let slot = unique_targets
                .iter()
                .position(|(component, field)| {
                    *component == spec.component.as_str() && *field == spec.field.as_str()
                })
                .unwrap_or_else(|| {
                    unique_targets.push((spec.component.as_str(), spec.field.as_str()));
                    unique_targets.len() - 1
                });
            target_slots.push(slot);
        }
        if let Some((rows, locations, flat_values, spec_count)) = dense_apply {
            let duplicate_targets = (0..unique_targets.len())
                .map(|slot| {
                    target_slots
                        .iter()
                        .filter(|target_slot| **target_slot == slot)
                        .count()
                })
                .map(|count| count.saturating_sub(1))
                .sum::<usize>();
            self.report.duplicate_writes += duplicate_targets * rows.len();
            for (child_index, spec) in direct_specs.iter().enumerate() {
                self.report.fields_written += self.world.set_field_f64_resolved_strided(
                    &spec.component,
                    &spec.field,
                    &locations,
                    &flat_values,
                    child_index,
                    spec_count,
                )?;
            }
        } else {
            let mut targets_seen = HashSet::new();
            for (child_index, writes) in child_writes.into_iter().enumerate() {
                let spec = &direct_specs[child_index];
                let target_slot = target_slots[child_index];
                for (entity, _) in &writes {
                    let key = (entity.raw(), target_slot);
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                }
                self.report.fields_written +=
                    self.world
                        .set_field_f64_many(&spec.component, &spec.field, &writes)?;
            }
        }
        if let Some(start) = apply_start {
            eprintln!(
                "ecs_profile direct_f64_apply elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        Ok(())
    }

    fn collect_direct_f64_row_writes(
        &mut self,
        direct_specs: &[DirectF64SetSpec],
        ctx: &EvalContext,
        cache: &mut [Option<f64>],
        child_writes: &mut [Vec<(Entity, f64)>],
    ) -> Result<()> {
        for (child_index, spec) in direct_specs.iter().enumerate() {
            let entity = ctx.bindings.get(&spec.query).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "query '{}' is not bound for set target",
                    spec.query
                ))
            })?;
            let value = self.eval_expr_f64(spec.value_expr, ctx, cache)?;
            child_writes[child_index].push((entity, value));
        }
        Ok(())
    }

    pub(in crate::execution) fn direct_f64_set_specs(
        &self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
    ) -> Option<Vec<DirectF64SetSpec>> {
        let mut direct = Vec::with_capacity(specs.len());
        for (_, target, value, _) in specs {
            let ExprNode::Field {
                query,
                component,
                field,
            } = &self.plan.expressions[*target]
            else {
                return None;
            };
            let storage_type = self.world.storage_type_for_field(component, field).ok()?;
            if !matches!(storage_type, StorageType::Float32 | StorageType::Float64) {
                return None;
            }
            direct.push(DirectF64SetSpec {
                query: query.clone(),
                component: component.clone(),
                field: field.clone(),
                value_expr: *value,
            });
        }
        Some(direct)
    }

    pub(in crate::execution) fn fused_parallel_specs_support_f64(
        &self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
    ) -> bool {
        specs.iter().all(|(_, target, value, _)| {
            self.target_supports_f64(*target) && self.expr_supports_f64(*value, &mut HashSet::new())
        })
    }

    fn target_supports_f64(&self, target: usize) -> bool {
        match &self.plan.expressions[target] {
            ExprNode::Field {
                component, field, ..
            }
            | ExprNode::ResourceField {
                resource: component,
                field,
            } => self
                .world
                .storage_type_for_field(component, field)
                .is_ok_and(storage_type_is_numeric),
            _ => false,
        }
    }

    pub(in crate::execution) fn expr_supports_f64(
        &self,
        expr_index: usize,
        seen: &mut HashSet<usize>,
    ) -> bool {
        if !seen.insert(expr_index) {
            return true;
        }
        match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_) | ExprNode::LiteralI64(_) | ExprNode::LiteralBool(_) => true,
            ExprNode::LiteralValue(value) => matches!(
                value,
                EcsValue::Bool(_) | EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_)
            ),
            ExprNode::Field {
                component, field, ..
            }
            | ExprNode::ResourceField {
                resource: component,
                field,
            } => self
                .world
                .storage_type_for_field(component, field)
                .is_ok_and(storage_type_is_numeric),
            ExprNode::InputState { .. } => true,
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.expr_supports_f64(*input, seen)
            }
            ExprNode::Binary { left, right, .. } => {
                self.expr_supports_f64(*left, seen) && self.expr_supports_f64(*right, seen)
            }
            ExprNode::ContextJoin { predicate, .. } => self.expr_supports_f64(*predicate, seen),
            ExprNode::Exists { predicate, .. } => self.expr_supports_f64(*predicate, seen),
            ExprNode::Aggregate {
                relation,
                value,
                default,
                ..
            } => {
                self.expr_supports_f64(*relation, seen)
                    && value.is_none_or(|value| self.expr_supports_f64(value, seen))
                    && default.is_none_or(|default| self.expr_supports_f64(default, seen))
            }
            ExprNode::SpatialMetadata { .. } => true,
            ExprNode::SpatialAggregate { value, default, .. } => {
                value.is_none_or(|value| self.expr_supports_f64(value, seen))
                    && default.is_none_or(|default| self.expr_supports_f64(default, seen))
            }
            ExprNode::LiteralString(_)
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => false,
        }
    }
}
