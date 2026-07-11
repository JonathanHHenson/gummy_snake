use std::collections::hash_map::DefaultHasher;
use std::collections::HashSet;
use std::hash::{Hash, Hasher};

use crate::error::Result;
use crate::execution::CachedSpatialIndex;
use crate::plan::{
    compile_bridge_plan, BridgePlanPayload, ExprNode, PhysicalPlan, PhysicalPlanHandle,
    SpatialRelationNode,
};

use super::World;

impl World {
    pub fn compile_bridge_plan(&self, payload: BridgePlanPayload) -> Result<PhysicalPlan> {
        compile_bridge_plan(payload, &self.schemas)
    }

    pub fn store_compiled_plan(&mut self, plan: PhysicalPlan) -> Result<PhysicalPlanHandle> {
        let spatial_cache_keys = compiled_plan_spatial_cache_keys(&plan);
        let handle = self.compiled_plans.insert(plan)?;
        self.compiled_plan_spatial_cache_keys
            .insert(handle, spatial_cache_keys);
        Ok(handle)
    }

    pub fn compile_bridge_plan_handle(
        &mut self,
        payload: BridgePlanPayload,
    ) -> Result<PhysicalPlanHandle> {
        let plan = self.compile_bridge_plan(payload)?;
        self.store_compiled_plan(plan)
    }

    pub(crate) fn compiled_plan(
        &self,
        handle: PhysicalPlanHandle,
    ) -> Option<std::sync::Arc<PhysicalPlan>> {
        self.compiled_plans.get(handle)
    }

    pub fn release_compiled_plan(&mut self, handle: PhysicalPlanHandle) -> bool {
        if self.compiled_plans.remove(handle).is_none() {
            return false;
        }
        let Some(cache_keys) = self.compiled_plan_spatial_cache_keys.remove(&handle) else {
            return true;
        };
        for cache_key in cache_keys {
            let still_owned = self
                .compiled_plan_spatial_cache_keys
                .values()
                .any(|owner_keys| owner_keys.contains(&cache_key));
            if !still_owned {
                self.spatial_index_cache.remove(&cache_key);
            }
        }
        true
    }

    pub fn compiled_plan_count(&self) -> usize {
        self.compiled_plans.len()
    }

    pub(crate) fn take_spatial_index_cache(
        &mut self,
        index_id: &str,
    ) -> Option<CachedSpatialIndex> {
        self.spatial_index_cache.remove(index_id)
    }

    pub(crate) fn store_spatial_index_cache(
        &mut self,
        index_id: String,
        cached: CachedSpatialIndex,
    ) {
        self.spatial_index_cache.insert(index_id, cached);
    }

    pub fn spatial_index_cache_len(&self) -> usize {
        self.spatial_index_cache.len()
    }
}

fn compiled_plan_spatial_cache_keys(plan: &PhysicalPlan) -> HashSet<String> {
    plan.expressions
        .iter()
        .filter_map(|expression| match expression {
            ExprNode::SpatialMetadata { relation, .. }
            | ExprNode::SpatialAggregate { relation, .. } => {
                Some(spatial_index_cache_key(plan, relation))
            }
            _ => None,
        })
        .collect()
}

fn spatial_index_cache_key(plan: &PhysicalPlan, relation: &SpatialRelationNode) -> String {
    format!(
        "{}|item={};target_pos={:?};target_bounds={:?};algorithm={:?};item_query_fingerprint={}",
        relation.index_id,
        relation.item_query,
        relation.target_position,
        relation.target_bounds,
        relation.algorithm,
        query_fingerprint(plan, &relation.item_query),
    )
}

fn query_fingerprint(plan: &PhysicalPlan, query_name: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    query_name.hash(&mut hasher);
    if let Some(query) = plan.queries.iter().find(|query| query.name == query_name) {
        query.filter.hash(&mut hasher);
        query.allowed_entities.hash(&mut hasher);
    }
    hasher.finish()
}
