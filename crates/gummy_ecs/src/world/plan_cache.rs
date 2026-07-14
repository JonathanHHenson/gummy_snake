use std::sync::Arc;

use crate::error::Result;
use crate::execution::CachedSpatialIndex;
use crate::plan::{
    compile_bridge_plan, BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle, PreparedPlan,
};

use super::World;

impl World {
    pub fn compile_bridge_plan(&self, payload: BridgePlanPayload) -> Result<PhysicalPlan> {
        compile_bridge_plan(payload, &self.schemas)
    }

    pub fn store_compiled_plan(&mut self, plan: PhysicalPlan) -> Result<PhysicalPlanHandle> {
        let handle = self
            .compiled_plans
            .insert_with_schemas(plan, &self.schemas)?;
        let prepared = self
            .compiled_plans
            .get(handle)
            .expect("newly inserted prepared plan handle must resolve");
        let spatial_cache_keys = prepared.spatial_cache_keys().to_vec();
        for cache_key in &spatial_cache_keys {
            *self
                .spatial_cache_ref_counts
                .entry(cache_key.clone())
                .or_default() += 1;
        }
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

    pub(crate) fn compiled_prepared_plan(
        &self,
        handle: PhysicalPlanHandle,
    ) -> Option<Arc<PreparedPlan>> {
        self.compiled_plans.get(handle)
    }

    pub fn release_compiled_plan(&mut self, handle: PhysicalPlanHandle) -> bool {
        if self.compiled_plans.remove(handle).is_none() {
            return false;
        }
        for cache_key in self
            .compiled_plan_spatial_cache_keys
            .remove(&handle)
            .unwrap_or_default()
        {
            let remove = if let Some(ref_count) = self.spatial_cache_ref_counts.get_mut(&cache_key)
            {
                *ref_count = ref_count.saturating_sub(1);
                *ref_count == 0
            } else {
                false
            };
            if remove {
                self.spatial_cache_ref_counts.remove(&cache_key);
                self.spatial_index_cache.remove(&cache_key);
            }
        }
        true
    }

    pub fn compiled_plan_count(&self) -> usize {
        self.compiled_plans.len()
    }

    pub fn unique_prepared_plan_count(&self) -> usize {
        self.compiled_plans.unique_prepared_len()
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
