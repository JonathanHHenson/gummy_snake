use std::sync::Arc;
use std::time::Instant;

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{SpatialBoundsExprNode, SpatialRelationNode};
use crate::spatial::{SpatialAabb, SpatialPoint, SpatialRecord};

use super::super::value_ops::{numeric_f64, truthy};
use super::super::{EvalContext, PlanExecutor};
use super::helpers::point_bounds;
use super::support::effective_query_radius;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn spatial_relation_records(
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

    pub(in crate::execution) fn build_spatial_relation_records(
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
        let query_radius = effective_query_radius(radius, distance_filter);
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
        let unique_unordered_pairs = self.unique_unordered_pairs(relation);
        let mut records = Vec::new();
        for record in candidates {
            if !relation.include_self && record.entity == origin_entity {
                continue;
            }
            if unique_unordered_pairs && record.entity.raw() <= origin_entity.raw() {
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

    pub(in crate::execution) fn eval_spatial_point(
        &mut self,
        coords: &[usize],
        ctx: &EvalContext,
    ) -> Result<SpatialPoint> {
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

    pub(in crate::execution) fn eval_spatial_bounds(
        &mut self,
        bounds: &SpatialBoundsExprNode,
        ctx: &EvalContext,
    ) -> Result<SpatialAabb> {
        let minimum = self.eval_spatial_point(&bounds.minimum, ctx)?;
        let maximum = self.eval_spatial_point(&bounds.maximum, ctx)?;
        SpatialAabb::new(minimum, maximum)
    }
}
