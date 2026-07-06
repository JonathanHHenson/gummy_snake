use std::collections::{BTreeSet, HashSet};

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, PhysicalPlan};
use crate::world::World;

use super::{EvalContext, PlanExecutor, QueryIndices, QueryRows, SpatialPrecomputeLayout};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn query_locations(
        &mut self,
        query_name: &str,
    ) -> Result<Vec<(usize, usize)>> {
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

    pub(in crate::execution) fn preload_numeric_fields_for_query(
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

    pub(in crate::execution) fn expand_context_for_queries(
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

    pub(in crate::execution) fn entity_field_f64(
        &mut self,
        entity: Entity,
        component: &str,
        field: &str,
    ) -> Result<f64> {
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
}

pub(in crate::execution) fn query_rows_for_plan(
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

pub(in crate::execution) fn query_rows_for_world(
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
