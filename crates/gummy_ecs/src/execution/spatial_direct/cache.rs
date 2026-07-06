use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::SpatialPoint;

use super::super::spatial_support::{
    DirectSpatialCoord, DirectSpatialRelationBatch, FastFieldArray,
};
use super::super::value_ops::literal_expr_numeric;
use super::super::PlanExecutor;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn precomputed_spatial_f64(
        &self,
        expr_index: usize,
        entity: Entity,
    ) -> Option<f64> {
        let values = self.spatial_precomputed_f64.get(&expr_index)?;
        let Some(Some((generation, value))) = values.get(entity.index as usize) else {
            return None;
        };
        (*generation == entity.generation).then_some(*value)
    }

    pub(in crate::execution) fn store_precomputed_spatial_f64(
        &mut self,
        expr_index: usize,
        entity: Entity,
        value: f64,
    ) {
        let row = entity.index as usize;
        let values = self.spatial_precomputed_f64.entry(expr_index).or_default();
        if values.len() <= row {
            values.resize(row + 1, None);
        }
        values[row] = Some((entity.generation, value));
    }

    pub(in crate::execution) fn direct_spatial_relation_batch(
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

    pub(in crate::execution) fn build_fast_field_array_with_locations(
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

    pub(in crate::execution) fn ensure_fast_field_array_with_locations(
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

    pub(in crate::execution) fn match_direct_spatial_coords(
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

    pub(in crate::execution) fn direct_spatial_point_for_entity(
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
}
