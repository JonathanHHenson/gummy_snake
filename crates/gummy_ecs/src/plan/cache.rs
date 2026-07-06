use std::collections::HashMap;
use std::sync::Arc;

use crate::error::Result;

use super::validation::validate_plan;
use super::{PhysicalPlan, PhysicalPlanHandle};

#[derive(Debug, Clone, PartialEq)]
pub struct PlanCache {
    compiled: HashMap<PhysicalPlanHandle, Arc<PhysicalPlan>>,
    next_handle: PhysicalPlanHandle,
}

impl Default for PlanCache {
    fn default() -> Self {
        Self {
            compiled: HashMap::new(),
            next_handle: 1,
        }
    }
}

impl PlanCache {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&mut self, plan: PhysicalPlan) -> Result<PhysicalPlanHandle> {
        validate_plan(&plan)?;
        let handle = self.next_handle;
        self.next_handle = self.next_handle.saturating_add(1).max(1);
        self.compiled.insert(handle, Arc::new(plan));
        Ok(handle)
    }

    pub fn get(&self, handle: PhysicalPlanHandle) -> Option<Arc<PhysicalPlan>> {
        self.compiled.get(&handle).cloned()
    }

    pub fn remove(&mut self, handle: PhysicalPlanHandle) -> Option<Arc<PhysicalPlan>> {
        self.compiled.remove(&handle)
    }

    pub fn len(&self) -> usize {
        self.compiled.len()
    }

    pub fn is_empty(&self) -> bool {
        self.compiled.is_empty()
    }
}
