use std::collections::{BTreeSet, HashMap, HashSet};
use std::time::Instant;

use crate::column::EcsValue;

use crate::error::{EcsError, Result};
use crate::plan::{ActionNode, ExprNode};

use super::{EvalContext, ExecutionReport, ExecutionWrite, PlanExecutor, WriteKey};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn execute_parallel(
        &mut self,
        children: &[usize],
        contexts: &[EvalContext],
    ) -> Result<()> {
        if children
            .iter()
            .all(|child| matches!(self.plan.actions[*child], ActionNode::SetField { .. }))
        {
            return self.execute_parallel_set_fields(children, contexts);
        }

        let snapshot = self.world.clone();
        let mut targets_seen = HashSet::new();
        let mut shared_spatial_indexes = HashMap::new();
        let mut shared_spatial_index_metadata = HashMap::new();
        let mut shared_spatial_relation_cache = HashMap::new();
        let mut shared_expr_cache = HashMap::new();
        for child in children {
            let share_expr_cache_after_child = matches!(
                self.plan.actions[*child],
                ActionNode::SetField { .. } | ActionNode::When { .. }
            );
            let mut child_world = snapshot.clone();
            let mut child_executor = PlanExecutor::new(
                &mut child_world,
                self.plan,
                self.query_rows.clone(),
                self.query_indices.clone(),
                true,
                self.profile,
            );
            child_executor.query_location_cache = self.query_location_cache.clone();
            child_executor.spatial_indexes = shared_spatial_indexes;
            child_executor.spatial_index_metadata = shared_spatial_index_metadata;
            child_executor.spatial_relation_cache = shared_spatial_relation_cache;
            child_executor.expr_cache = shared_expr_cache;
            child_executor.execute_action(*child, contexts)?;
            shared_spatial_indexes = child_executor.spatial_indexes;
            shared_spatial_index_metadata = child_executor.spatial_index_metadata;
            shared_spatial_relation_cache = child_executor.spatial_relation_cache;
            shared_expr_cache = if share_expr_cache_after_child {
                child_executor.expr_cache
            } else {
                HashMap::new()
            };
            self.merge_parallel_report(child_executor.report, &mut targets_seen)?;
        }
        self.spatial_indexes.extend(shared_spatial_indexes);
        self.spatial_index_metadata
            .extend(shared_spatial_index_metadata);
        Ok(())
    }

    pub(in crate::execution) fn execute_parallel_set_fields(
        &mut self,
        children: &[usize],
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut specs = Vec::with_capacity(children.len());
        let mut expr_query_cache = HashMap::new();
        for child in children {
            let ActionNode::SetField { target, value } = self.plan.actions[*child] else {
                unreachable!("parallel set fast path only receives set actions");
            };
            let mut query_names = self.expr_queries_cached(value, &mut expr_query_cache)?;
            self.add_set_target_query(target, &mut query_names)?;
            specs.push((*child, target, value, query_names));
        }

        let can_fuse = specs
            .first()
            .map(|(_, _, _, first_queries)| {
                specs
                    .iter()
                    .all(|(_, _, _, query_names)| query_names == first_queries)
            })
            .unwrap_or(true);

        let query_rows = self.query_rows.clone();
        let query_indices = self.query_indices.clone();
        let collector_report;
        let collector_spatial_indexes;
        let collector_spatial_index_metadata;
        {
            let profile = self.profile;
            let parallel_start = profile.then(Instant::now);
            let mut collector = PlanExecutor::new(
                &mut *self.world,
                self.plan,
                query_rows,
                query_indices,
                self.report_writes,
                profile,
            );
            collector.numeric_field_cache_enabled = true;

            if can_fuse {
                collector.execute_fused_parallel_set_collect(&specs, contexts)?;
            } else {
                for (child, target, value, _) in &specs {
                    let child_start = profile.then(Instant::now);
                    collector.execute_set_collect(*target, *value, contexts)?;
                    if let Some(start) = child_start {
                        eprintln!(
                            "ecs_profile parallel_set_child action={child} target={target} value={value} elapsed_ms={:.3} eval_calls={} expr_hits={} expr_misses={} relation_hits={} relation_misses={} spatial_index_ms={:.3} spatial_query_ms={:.3} spatial_filter_ms={:.3} direct_agg_hits={} direct_agg_ms={:.3}",
                            start.elapsed().as_secs_f64() * 1000.0,
                            collector.profile_eval_calls,
                            collector.profile_expr_cache_hits,
                            collector.profile_expr_cache_misses,
                            collector.profile_spatial_relation_hits,
                            collector.profile_spatial_relation_misses,
                            collector.profile_spatial_index_nanos as f64 / 1_000_000.0,
                            collector.profile_spatial_query_nanos as f64 / 1_000_000.0,
                            collector.profile_spatial_filter_nanos as f64 / 1_000_000.0,
                            collector.profile_direct_aggregate_hits,
                            collector.profile_direct_aggregate_nanos as f64 / 1_000_000.0,
                        );
                    }
                }
            }
            if let Some(start) = parallel_start {
                eprintln!(
                    "ecs_profile parallel_set_collect_total fused={} elapsed_ms={:.3} eval_calls={} expr_hits={} expr_misses={} relation_hits={} relation_misses={} spatial_index_ms={:.3} spatial_query_ms={:.3} spatial_filter_ms={:.3} direct_agg_hits={} direct_agg_ms={:.3}",
                    can_fuse,
                    start.elapsed().as_secs_f64() * 1000.0,
                    collector.profile_eval_calls,
                    collector.profile_expr_cache_hits,
                    collector.profile_expr_cache_misses,
                    collector.profile_spatial_relation_hits,
                    collector.profile_spatial_relation_misses,
                    collector.profile_spatial_index_nanos as f64 / 1_000_000.0,
                    collector.profile_spatial_query_nanos as f64 / 1_000_000.0,
                    collector.profile_spatial_filter_nanos as f64 / 1_000_000.0,
                    collector.profile_direct_aggregate_hits,
                    collector.profile_direct_aggregate_nanos as f64 / 1_000_000.0,
                );
            }
            let drop_start = profile.then(Instant::now);
            collector_report = std::mem::take(&mut collector.report);
            collector_spatial_indexes = std::mem::take(&mut collector.spatial_indexes);
            collector_spatial_index_metadata =
                std::mem::take(&mut collector.spatial_index_metadata);
            drop(collector);
            if let Some(start) = drop_start {
                eprintln!(
                    "ecs_profile parallel_set_collector_drop elapsed_ms={:.3}",
                    start.elapsed().as_secs_f64() * 1000.0
                );
            }
        }

        self.spatial_indexes.extend(collector_spatial_indexes);
        self.spatial_index_metadata
            .extend(collector_spatial_index_metadata);

        let merge_start = self.profile.then(Instant::now);
        let write_count = collector_report.writes.len();
        let mut targets_seen = HashSet::new();
        let result = self.merge_parallel_report(collector_report, &mut targets_seen);
        if let Some(start) = merge_start {
            eprintln!(
                "ecs_profile parallel_set_merge elapsed_ms={:.3} writes={write_count}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        result
    }

    fn merge_parallel_report(
        &mut self,
        child_report: ExecutionReport,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        self.merge_parallel_counters(&child_report);
        self.report.events.extend(child_report.events);
        self.report
            .canvas_commands
            .extend(child_report.canvas_commands);
        self.report
            .canvas_fill_batches
            .extend(child_report.canvas_fill_batches);
        if child_report.writes.is_empty() {
            self.report.fields_written += child_report.fields_written;
            self.report.resource_fields_written += child_report.resource_fields_written;
        }
        for write in child_report.writes {
            self.apply_parallel_write(&write, targets_seen)?;
            if self.report_writes {
                self.report.writes.push(write);
            }
        }
        Ok(())
    }

    fn merge_parallel_counters(&mut self, child_report: &ExecutionReport) {
        self.report.rows_scanned += child_report.rows_scanned;
        self.report.events_emitted += child_report.events_emitted;
        self.report.structural_commands += child_report.structural_commands;
        self.report.duplicate_writes += child_report.duplicate_writes;
        self.report.spatial_indexes_built += child_report.spatial_indexes_built;
        self.report.spatial_candidate_rows += child_report.spatial_candidate_rows;
        self.report.spatial_exact_rows += child_report.spatial_exact_rows;
        self.report.spatial_false_positive_rows += child_report.spatial_false_positive_rows;
        self.report.spatial_deduplicated_pairs += child_report.spatial_deduplicated_pairs;
        self.report.spatial_algorithm_hash_grid += child_report.spatial_algorithm_hash_grid;
        self.report.spatial_algorithm_quadtree += child_report.spatial_algorithm_quadtree;
        self.report.spatial_algorithm_octree += child_report.spatial_algorithm_octree;
        self.report.spatial_algorithm_hilbert_curve += child_report.spatial_algorithm_hilbert_curve;
        self.report.spatial_index_reuses += child_report.spatial_index_reuses;
        self.report.spatial_index_full_rebuilds += child_report.spatial_index_full_rebuilds;
        self.report.spatial_index_incremental_updates +=
            child_report.spatial_index_incremental_updates;
        self.report.spatial_parallel_chunks += child_report.spatial_parallel_chunks;
        self.report.spatial_parallel_workers = self
            .report
            .spatial_parallel_workers
            .max(child_report.spatial_parallel_workers);
        self.report.spatial_thread_scratch_reuses += child_report.spatial_thread_scratch_reuses;
        self.report.spatial_candidate_buffer_growths +=
            child_report.spatial_candidate_buffer_growths;
    }

    fn apply_parallel_write(
        &mut self,
        write: &ExecutionWrite,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        match write {
            ExecutionWrite::ComponentField {
                entity,
                component,
                field,
                value,
            } => {
                let key = WriteKey::Component {
                    entity: *entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_field(*entity, component, field, value.clone())?;
                self.report.fields_written += 1;
            }
            ExecutionWrite::ResourceField {
                resource,
                field,
                value,
            } => {
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_resource_field(resource, field, value.clone())?;
                self.report.resource_fields_written += 1;
            }
        }
        Ok(())
    }

    fn execute_set_collect(
        &mut self,
        target_index: usize,
        value_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(value_index, &mut query_names)?;
        self.add_set_target_query(target_index, &mut query_names)?;

        let mut targets_seen = HashSet::new();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let value = self.eval_expr(value_index, &ctx)?;
                self.collect_target_write(target_index, value, &ctx, &mut targets_seen)?;
            }
        }
        Ok(())
    }

    fn execute_fused_parallel_set_collect(
        &mut self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        if self.fused_parallel_specs_support_f64(specs) {
            return self.execute_fused_parallel_set_collect_f64(specs, contexts);
        }

        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..specs.len()).map(|_| Vec::new()).collect::<Vec<_>>();
        let mut child_targets_seen = (0..specs.len()).map(|_| HashSet::new()).collect::<Vec<_>>();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                self.local_expr_cache = Some(vec![None; self.plan.expressions.len()]);
                self.local_expr_bindings = Some(ctx.bindings.clone());
                for (child_index, (_, target, value, _)) in specs.iter().enumerate() {
                    let value = self.eval_expr(*value, &ctx)?;
                    let write = self.collect_target_write_record(
                        *target,
                        value,
                        &ctx,
                        &mut child_targets_seen[child_index],
                    )?;
                    child_writes[child_index].push(write);
                }
                self.local_expr_cache = None;
                self.local_expr_bindings = None;
            }
        }
        for writes in child_writes {
            self.report.writes.extend(writes);
        }
        Ok(())
    }

    fn execute_fused_parallel_set_collect_f64(
        &mut self,
        specs: &[(usize, usize, usize, BTreeSet<String>)],
        contexts: &[EvalContext],
    ) -> Result<()> {
        if !self.report_writes {
            if let Some(direct_specs) = self.direct_f64_set_specs(specs) {
                return self.execute_fused_parallel_set_collect_f64_direct(
                    &direct_specs,
                    specs,
                    contexts,
                );
            }
        }

        let Some((_, _, _, query_names)) = specs.first() else {
            return Ok(());
        };
        let mut child_writes = (0..specs.len()).map(|_| Vec::new()).collect::<Vec<_>>();
        let mut child_targets_seen = (0..specs.len()).map(|_| HashSet::new()).collect::<Vec<_>>();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let mut cache = vec![None; self.plan.expressions.len()];
                for (child_index, (_, target, value, _)) in specs.iter().enumerate() {
                    let value = self.eval_expr_f64(*value, &ctx, &mut cache)?;
                    let write = self.collect_target_write_record(
                        *target,
                        EcsValue::F64(value),
                        &ctx,
                        &mut child_targets_seen[child_index],
                    )?;
                    child_writes[child_index].push(write);
                }
            }
        }
        for writes in child_writes {
            self.report.writes.extend(writes);
        }
        Ok(())
    }

    fn collect_target_write(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        let write = self.collect_target_write_record(target_index, value, ctx, targets_seen)?;
        self.report.writes.push(write);
        Ok(())
    }

    fn collect_target_write_record(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<ExecutionWrite> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = *ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self
                    .world
                    .coerce_value_for_component_field(component, field, value)?;
                let key = WriteKey::Component {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                Ok(ExecutionWrite::ComponentField {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                    value,
                })
            }
            ExprNode::ResourceField { resource, field } => {
                let value = self
                    .world
                    .coerce_value_for_component_field(resource, field, value)?;
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                Ok(ExecutionWrite::ResourceField {
                    resource: resource.clone(),
                    field: field.clone(),
                    value,
                })
            }
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }
}
