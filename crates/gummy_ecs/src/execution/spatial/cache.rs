use std::collections::hash_map::DefaultHasher;
use std::collections::HashSet;
use std::hash::{Hash, Hasher};

use crate::error::{EcsError, Result};
use crate::plan::{ExprNode, SpatialRelationNode};
use crate::spatial::SpatialRecord;

use super::super::{EvalContext, PlanExecutor};
use super::helpers::{
    build_spatial_index, should_try_incremental_spatial_update, spatial_index_base_signature,
};
use super::support::{BuiltSpatialIndex, CachedSpatialIndex};

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn persist_spatial_index_cache(&mut self) {
        for (index_id, index) in self.spatial_indexes.drain() {
            let Some((signature, structural_revision, field_revision)) =
                self.spatial_index_metadata.remove(&index_id)
            else {
                continue;
            };
            self.world.store_spatial_index_cache(
                index_id,
                CachedSpatialIndex {
                    index,
                    signature,
                    structural_revision,
                    field_revision,
                },
            );
        }
    }

    pub(in crate::execution) fn report_algorithm_use(&mut self, index: &BuiltSpatialIndex) {
        match index {
            BuiltSpatialIndex::HashGrid(_) | BuiltSpatialIndex::DirectPointHashGrid(_) => {
                self.report.spatial_algorithm_hash_grid += 1
            }
            BuiltSpatialIndex::Quadtree(_) => self.report.spatial_algorithm_quadtree += 1,
            BuiltSpatialIndex::Octree(_) => self.report.spatial_algorithm_octree += 1,
            BuiltSpatialIndex::Hilbert(_) => self.report.spatial_algorithm_hilbert_curve += 1,
        }
    }

    pub(in crate::execution) fn spatial_dependency_revision(
        &self,
        relation: &SpatialRelationNode,
    ) -> u64 {
        let mut dependencies = Vec::new();
        let mut complete = true;
        for expr in &relation.target_position {
            complete &= self.collect_spatial_field_dependencies(
                *expr,
                &relation.item_query,
                &mut dependencies,
                &mut HashSet::new(),
            );
        }
        if let Some(bounds) = &relation.target_bounds {
            for expr in bounds.minimum.iter().chain(bounds.maximum.iter()) {
                complete &= self.collect_spatial_field_dependencies(
                    *expr,
                    &relation.item_query,
                    &mut dependencies,
                    &mut HashSet::new(),
                );
            }
        }
        if complete && !dependencies.is_empty() {
            dependencies
                .iter()
                .map(|(component, field)| self.world.component_field_revision(component, field))
                .max()
                .unwrap_or(0)
        } else {
            self.world.field_revision()
        }
    }

    pub(in crate::execution) fn collect_spatial_field_dependencies(
        &self,
        expr_index: usize,
        query_name: &str,
        dependencies: &mut Vec<(String, String)>,
        visiting: &mut HashSet<usize>,
    ) -> bool {
        if !visiting.insert(expr_index) {
            return true;
        }
        let complete = match &self.plan.expressions[expr_index] {
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_) => true,
            ExprNode::Field {
                query,
                component,
                field,
            } if query == query_name => {
                dependencies.push((component.clone(), field.clone()));
                true
            }
            ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
                self.collect_spatial_field_dependencies(*input, query_name, dependencies, visiting)
            }
            ExprNode::Binary { left, right, .. } => {
                self.collect_spatial_field_dependencies(*left, query_name, dependencies, visiting)
                    & self.collect_spatial_field_dependencies(
                        *right,
                        query_name,
                        dependencies,
                        visiting,
                    )
            }
            _ => false,
        };
        visiting.remove(&expr_index);
        complete
    }

    pub(in crate::execution) fn spatial_index_signature(
        &self,
        relation: &SpatialRelationNode,
    ) -> String {
        format!(
            "{};item_query_fingerprint={}",
            spatial_index_base_signature(relation),
            self.query_fingerprint(&relation.item_query)
        )
    }

    pub(in crate::execution) fn spatial_index_cache_key(
        &self,
        relation: &SpatialRelationNode,
    ) -> String {
        format!(
            "{}|{}",
            relation.index_id,
            self.spatial_index_signature(relation)
        )
    }

    pub(in crate::execution) fn query_fingerprint(&self, query_name: &str) -> u64 {
        let mut hasher = DefaultHasher::new();
        query_name.hash(&mut hasher);
        if let Some(query) = self
            .plan
            .queries
            .iter()
            .find(|query| query.name == query_name)
        {
            query.filter.hash(&mut hasher);
        }
        hasher.finish()
    }

    pub(in crate::execution) fn take_fresh_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Option<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let cached = self.world.take_spatial_index_cache(&index_key)?;
        if cached.signature == signature
            && cached.structural_revision == structural_revision
            && cached.field_revision == field_revision
        {
            self.report.spatial_index_reuses += 1;
            self.spatial_index_metadata
                .insert(index_key, (signature, structural_revision, field_revision));
            return Some(cached.index);
        }
        self.world.store_spatial_index_cache(index_key, cached);
        None
    }

    pub(in crate::execution) fn build_or_update_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        records: Vec<SpatialRecord>,
    ) -> Result<BuiltSpatialIndex> {
        let signature = self.spatial_index_signature(relation);
        let index_key = self.spatial_index_cache_key(relation);
        let structural_revision = self.world.structural_revision();
        let field_revision = self.spatial_dependency_revision(relation);
        let algorithm_kind = self.typed_spatial_relation(relation).algorithm;
        let index = if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
            if cached.signature == signature {
                if cached.structural_revision == structural_revision
                    && cached.field_revision == field_revision
                {
                    self.report.spatial_index_reuses += 1;
                    self.spatial_index_metadata
                        .insert(index_key, (signature, structural_revision, field_revision));
                    return Ok(cached.index);
                }
                if should_try_incremental_spatial_update(
                    records.len(),
                    cached.field_revision,
                    field_revision,
                ) {
                    if cached.index.update_incremental(&records)? {
                        self.report.spatial_index_incremental_updates += 1;
                    } else {
                        self.report.spatial_indexes_built += 1;
                        self.report.spatial_index_full_rebuilds += 1;
                    }
                } else {
                    cached.index.build(&records)?;
                    self.report.spatial_indexes_built += 1;
                    self.report.spatial_index_full_rebuilds += 1;
                }
                cached.index
            } else {
                let mut index = build_spatial_index(&relation.algorithm, algorithm_kind)?;
                index.build(&records)?;
                self.report.spatial_indexes_built += 1;
                self.report.spatial_index_full_rebuilds += 1;
                index
            }
        } else {
            let mut index = build_spatial_index(&relation.algorithm, algorithm_kind)?;
            index.build(&records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            index
        };
        self.spatial_index_metadata
            .insert(index_key, (signature, structural_revision, field_revision));
        Ok(index)
    }

    pub(in crate::execution) fn ensure_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<&BuiltSpatialIndex> {
        let index_key = self.spatial_index_cache_key(relation);
        if self.spatial_indexes.contains_key(&index_key) {
            self.report.spatial_index_reuses += 1;
        } else if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        } else {
            let records = self.build_spatial_records(relation, ctx)?;
            let index = self.build_or_update_spatial_index(relation, records)?;
            self.report_algorithm_use(&index);
            self.spatial_indexes.insert(index_key.clone(), index);
        }
        self.spatial_indexes.get(&index_key).ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial index '{}' was not built",
                relation.index_id
            ))
        })
    }

    pub(in crate::execution) fn build_spatial_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Vec<SpatialRecord>> {
        let rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let mut records = Vec::with_capacity(rows.len());
        let item_slot = self.query_slot(&relation.item_query)?;
        for entity in rows {
            let mut item_ctx = ctx.clone();
            item_ctx.bindings[item_slot] = Some(entity);
            let point = self.eval_spatial_point(&relation.target_position, &item_ctx)?;
            let bounds = relation
                .target_bounds
                .as_ref()
                .map(|bounds| self.eval_spatial_bounds(bounds, &item_ctx))
                .transpose()?;
            records.push(SpatialRecord {
                entity,
                point,
                bounds,
            });
        }
        Ok(records)
    }
}
