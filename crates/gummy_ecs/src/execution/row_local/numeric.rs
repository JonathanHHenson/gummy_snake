use std::collections::HashMap;
use std::time::Instant;

use rayon::prelude::*;

use crate::error::{EcsError, Result};

use super::super::f64_program::{
    build_row_local_field_dependents, compile_f64_readonly_program, compiled_field_f64_value,
    execute_row_local_f64_action, invalidate_row_local_f64_cache, RowLocalAction,
};
use super::super::{ExecutionEvent, PlanExecutor, SpatialPrecomputeLayout};

fn row_local_action_emits_events(action: &RowLocalAction) -> bool {
    match action {
        RowLocalAction::EmitConstEvent { .. } => true,
        RowLocalAction::Sequence(children) => children.iter().any(row_local_action_emits_events),
        RowLocalAction::ForEachListField { action, .. } => row_local_action_emits_events(action),
        RowLocalAction::When {
            then_action,
            otherwise_action,
            ..
        } => {
            row_local_action_emits_events(then_action)
                || otherwise_action
                    .as_deref()
                    .is_some_and(row_local_action_emits_events)
        }
        RowLocalAction::Noop | RowLocalAction::SetField { .. } => false,
    }
}

impl<'a> PlanExecutor<'a> {
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
            &self.typed_plan,
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
        let action_emits_events = row_local_action_emits_events(&action);
        if target_count == 0 && !action_emits_events {
            return Ok(());
        }

        let expr_count = self.plan.expressions.len();
        let field_count = program.field_arrays.len();
        let field_dependents = build_row_local_field_dependents(&program);
        let mut flat_values = vec![0.0; rows.len() * target_count];
        let mut dirty = vec![false; rows.len() * target_count];
        let mut emitted_events = Vec::new();
        let eval_start = self.profile.then(Instant::now);
        let world = &*self.world;
        if action_emits_events {
            let mut cache_values = vec![0.0; expr_count];
            let mut cache_marks = vec![0_u32; expr_count];
            let mut cache_generation = 1_u32;
            let mut field_values = vec![0.0; field_count];
            let mut loop_items = Vec::new();
            for (row_index, entity) in rows.iter().copied().enumerate() {
                invalidate_row_local_f64_cache(&mut cache_marks, &mut cache_generation);
                for (slot, value) in field_values.iter_mut().enumerate() {
                    *value =
                        compiled_field_f64_value(program.field_arrays[slot], row_index, entity)?;
                }
                let out_start = row_index * target_count;
                let out_end = out_start + target_count;
                execute_row_local_f64_action(
                    &action,
                    row_index,
                    entity,
                    &program,
                    world,
                    &mut cache_values,
                    &mut cache_marks,
                    &mut cache_generation,
                    &mut field_values,
                    &field_dependents,
                    &mut flat_values[out_start..out_end],
                    &mut dirty[out_start..out_end],
                    &mut emitted_events,
                    &mut loop_items,
                )?;
            }
        } else {
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
                            Vec::new(),
                            Vec::new(),
                        )
                    },
                    |(
                        cache_values,
                        cache_marks,
                        cache_generation,
                        field_values,
                        event_out,
                        loop_items,
                    ),
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
                            event_out,
                            loop_items,
                        )
                    },
                )?;
        }
        if let Some(start) = eval_start {
            eprintln!(
                "ecs_profile row_local_f64_eval elapsed_ms={:.3}",
                start.elapsed().as_secs_f64() * 1000.0
            );
        }
        self.report.rows_scanned += rows.len();
        for (event_type, payload) in emitted_events {
            self.world.emit_event(&event_type, payload.clone())?;
            self.report.events_emitted += 1;
            if self.report_writes {
                self.report.events.push(ExecutionEvent {
                    event_type,
                    payload,
                });
            }
        }

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
