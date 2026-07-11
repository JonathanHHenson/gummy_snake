use crate::error::Result;
use crate::execution::CachedSpatialIndex;
use crate::plan::{compile_bridge_plan, BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle};

use super::World;

impl World {
    pub fn compile_bridge_plan(&self, payload: BridgePlanPayload) -> Result<PhysicalPlan> {
        compile_bridge_plan(payload, &self.schemas)
    }

    pub fn store_compiled_plan(&mut self, plan: PhysicalPlan) -> Result<PhysicalPlanHandle> {
        self.compiled_plans.insert(plan)
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
        self.compiled_plans.remove(handle).is_some()
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
