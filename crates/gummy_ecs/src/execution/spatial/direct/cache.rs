use std::collections::HashMap;

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::SpatialPoint;

use super::super::super::PlanExecutor;
use super::super::helpers::spatial_relations_same_base;
use super::super::support::{
    effective_query_radius, DirectSpatialCoord, DirectSpatialRelationBatch, FastFieldArray,
    FastSpatialBinaryOp, FastSpatialValueExpr, SpatialChunkResult, SpatialF64RowArray,
    SpatialLocalCounters, SpatialPrecomputeLayout,
};
use crate::execution::interpreter::value_ops::literal_expr_numeric;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn precomputed_spatial_f64(
        &self,
        expr_index: usize,
        entity: Entity,
    ) -> Option<f64> {
        self.spatial_precomputed_f64
            .get(&expr_index)?
            .get(&entity)
            .copied()
    }

    pub(in crate::execution) fn store_precomputed_spatial_f64(
        &mut self,
        expr_index: usize,
        entity: Entity,
        value: f64,
    ) {
        self.spatial_precomputed_f64
            .entry(expr_index)
            .or_default()
            .insert(entity, value);
    }

    #[allow(clippy::too_many_arguments)]
    pub(in crate::execution) fn store_spatial_chunk_results_f64(
        &mut self,
        layout: SpatialPrecomputeLayout,
        chunk_results: Vec<SpatialChunkResult>,
        result_exprs: &[usize],
        result_count: usize,
        row_count: usize,
        result_values_are_dense: bool,
    ) -> Result<()> {
        match layout {
            SpatialPrecomputeLayout::SparseEntity => {
                let mut result_arrays = result_exprs
                    .iter()
                    .map(|expr_index| (*expr_index, HashMap::with_capacity(row_count)))
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
                    self.report_spatial_local_counters(counters);
                    for (origin_index, origin) in origins.into_iter().enumerate() {
                        let base = origin_index * result_count;
                        for (slot, value) in values[base..base + result_count].iter().enumerate() {
                            if present.is_none_or(|present| present[base + slot]) {
                                result_arrays[slot].1.insert(origin, *value);
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
                    .map(|expr_index| (*expr_index, vec![0.0; row_count]))
                    .collect::<Vec<_>>();
                for chunk in chunk_results {
                    let SpatialChunkResult {
                        row_start,
                        origins: _,
                        values,
                        present: _,
                        counters,
                    } = chunk;
                    self.report_spatial_local_counters(counters);
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
                    .map(|expr_index| (*expr_index, vec![None; row_count]))
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
                    self.report_spatial_local_counters(counters);
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
        Ok(())
    }

    pub(in crate::execution) fn report_spatial_local_counters(
        &mut self,
        counters: SpatialLocalCounters,
    ) {
        self.report.spatial_candidate_rows += counters.candidate_rows;
        self.report.rows_scanned += counters.rows_scanned;
        self.report.spatial_exact_rows += counters.exact_rows;
        self.report.spatial_deduplicated_pairs += counters.deduplicated_pairs;
        self.report.spatial_candidate_buffer_growths += counters.candidate_buffer_growths;
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
        let query_radius = effective_query_radius(radius, distance_filter);
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
            .field_f64_rows_for_resolved_entities(component, field, locations)?;
        Ok(FastFieldArray {
            component: component.to_string(),
            field: field.to_string(),
            entities: entities.to_vec(),
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

    #[allow(clippy::too_many_arguments)]
    pub(in crate::execution) fn compile_fast_spatial_value_expr(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
        origin_coords: &[DirectSpatialCoord],
        target_coords: &[DirectSpatialCoord],
        item_field_arrays: &mut Vec<FastFieldArray>,
        item_rows: &[Entity],
        item_locations: &[(usize, usize)],
    ) -> Result<Option<FastSpatialValueExpr>> {
        self.compile_fast_spatial_value_expr_inner(
            expr_index,
            relation,
            origin_coords,
            target_coords,
            item_field_arrays,
            item_rows,
            item_locations,
            &mut std::collections::HashSet::new(),
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn compile_fast_spatial_value_expr_inner(
        &self,
        expr_index: usize,
        relation: &SpatialRelationNode,
        origin_coords: &[DirectSpatialCoord],
        target_coords: &[DirectSpatialCoord],
        item_field_arrays: &mut Vec<FastFieldArray>,
        item_rows: &[Entity],
        item_locations: &[(usize, usize)],
        seen: &mut std::collections::HashSet<usize>,
    ) -> Result<Option<FastSpatialValueExpr>> {
        if !seen.insert(expr_index) {
            return Ok(None);
        }
        let result = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(value) => Some(FastSpatialValueExpr::Literal(*value)),
            ExprNode::LiteralI64(value) => Some(FastSpatialValueExpr::Literal(*value as f64)),
            ExprNode::LiteralBool(value) => Some(FastSpatialValueExpr::Literal(if *value {
                1.0
            } else {
                0.0
            })),
            ExprNode::LiteralValue(_) => literal_expr_numeric(&self.plan.expressions[expr_index])
                .map(FastSpatialValueExpr::Literal),
            ExprNode::Field {
                query,
                component,
                field,
            } if query == &relation.origin_query => origin_coords
                .iter()
                .position(|coord| coord.component == *component && coord.field == *field)
                .map(|axis| FastSpatialValueExpr::OriginPointCoord { axis }),
            ExprNode::Field {
                query,
                component,
                field,
            } if query == &relation.item_query => {
                if let Some(axis) = target_coords
                    .iter()
                    .position(|coord| coord.component == *component && coord.field == *field)
                {
                    Some(FastSpatialValueExpr::ItemPointCoord { axis })
                } else {
                    let array_index = self.ensure_fast_field_array_with_locations(
                        item_field_arrays,
                        item_rows,
                        item_locations,
                        component,
                        field,
                    )?;
                    Some(FastSpatialValueExpr::ItemField { array_index })
                }
            }
            ExprNode::SpatialMetadata {
                relation: metadata_relation,
                kind,
                axis,
            } if spatial_relations_same_base(metadata_relation, relation) => match kind.as_str() {
                "delta" => axis.map(|axis| FastSpatialValueExpr::SpatialDelta { axis }),
                "distance" => Some(FastSpatialValueExpr::SpatialDistance),
                "distance_sq" => Some(FastSpatialValueExpr::SpatialDistanceSq),
                _ => None,
            },
            ExprNode::Unary { op, input } if matches!(op.as_str(), "neg" | "-") => self
                .compile_fast_spatial_value_expr_inner(
                    *input,
                    relation,
                    origin_coords,
                    target_coords,
                    item_field_arrays,
                    item_rows,
                    item_locations,
                    seen,
                )?
                .map(|input| FastSpatialValueExpr::Neg(Box::new(input))),
            ExprNode::Binary { op, left, right } => {
                let op = match op.as_str() {
                    "add" | "+" => Some(FastSpatialBinaryOp::Add),
                    "sub" | "-" => Some(FastSpatialBinaryOp::Sub),
                    "mul" | "*" => Some(FastSpatialBinaryOp::Mul),
                    "truediv" | "/" => Some(FastSpatialBinaryOp::Div),
                    "min" => Some(FastSpatialBinaryOp::Min),
                    "max" => Some(FastSpatialBinaryOp::Max),
                    _ => None,
                };
                if let Some(op) = op {
                    let left = self.compile_fast_spatial_value_expr_inner(
                        *left,
                        relation,
                        origin_coords,
                        target_coords,
                        item_field_arrays,
                        item_rows,
                        item_locations,
                        seen,
                    )?;
                    let right = self.compile_fast_spatial_value_expr_inner(
                        *right,
                        relation,
                        origin_coords,
                        target_coords,
                        item_field_arrays,
                        item_rows,
                        item_locations,
                        seen,
                    )?;
                    match (left, right) {
                        (Some(left), Some(right)) => Some(FastSpatialValueExpr::Binary {
                            op,
                            left: Box::new(left),
                            right: Box::new(right),
                        }),
                        _ => None,
                    }
                } else {
                    None
                }
            }
            ExprNode::Attribute { input, .. } => self.compile_fast_spatial_value_expr_inner(
                *input,
                relation,
                origin_coords,
                target_coords,
                item_field_arrays,
                item_rows,
                item_locations,
                seen,
            )?,
            _ => None,
        };
        seen.remove(&expr_index);
        Ok(result)
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
