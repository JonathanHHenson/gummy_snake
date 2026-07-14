use std::collections::HashMap;
use std::sync::{Arc, Weak};
use std::time::Instant;

use crate::error::Result;
use crate::schema::SchemaRegistry;

use super::validation::validate_plan;
use super::{PhysicalPlan, PhysicalPlanHandle, PreparedPlan};

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PlanCacheDiagnostics {
    pub preparation_count: usize,
    pub preparation_cache_hits: usize,
    pub preparation_cache_misses: usize,
    pub canonical_reuses: usize,
    pub preparation_nanos: u128,
    pub prepared_bytes_current: usize,
    pub prepared_bytes_peak: usize,
    pub schema_invalidations: usize,
}

#[derive(Debug, Clone)]
pub struct PlanCache {
    handles: HashMap<PhysicalPlanHandle, Arc<PreparedPlan>>,
    canonical: HashMap<u64, Vec<Weak<PreparedPlan>>>,
    owner_counts: HashMap<usize, usize>,
    next_handle: PhysicalPlanHandle,
    diagnostics: PlanCacheDiagnostics,
}

impl Default for PlanCache {
    fn default() -> Self {
        Self {
            handles: HashMap::new(),
            canonical: HashMap::new(),
            owner_counts: HashMap::new(),
            next_handle: 1,
            diagnostics: PlanCacheDiagnostics::default(),
        }
    }
}

impl PlanCache {
    pub fn new() -> Self {
        Self::default()
    }

    /// Insert a plan that does not reference schemas.
    ///
    /// Worlds should use [`Self::insert_with_schemas`] so component, field,
    /// resource, and spatial references are resolved into immutable prepared IDs.
    pub fn insert(&mut self, plan: PhysicalPlan) -> Result<PhysicalPlanHandle> {
        self.insert_with_schemas(plan, &SchemaRegistry::new())
    }

    pub fn insert_with_schemas(
        &mut self,
        plan: PhysicalPlan,
        schemas: &SchemaRegistry,
    ) -> Result<PhysicalPlanHandle> {
        validate_plan(&plan)?;
        let semantic_hash = semantic_hash(&plan);
        if let Some(prepared) = self.find_equivalent(semantic_hash, &plan) {
            self.diagnostics.preparation_cache_hits += 1;
            self.diagnostics.canonical_reuses += 1;
            return Ok(self.insert_handle(prepared));
        }

        self.diagnostics.preparation_cache_misses += 1;
        let started = Instant::now();
        let prepared = Arc::new(PreparedPlan::compile(plan, schemas)?);
        self.diagnostics.preparation_nanos = self
            .diagnostics
            .preparation_nanos
            .saturating_add(started.elapsed().as_nanos());
        self.diagnostics.preparation_count += 1;
        self.canonical
            .entry(prepared.semantic_hash())
            .or_default()
            .push(Arc::downgrade(&prepared));
        Ok(self.insert_handle(prepared))
    }

    fn find_equivalent(
        &mut self,
        semantic_hash: u64,
        plan: &PhysicalPlan,
    ) -> Option<Arc<PreparedPlan>> {
        let bucket = self.canonical.get_mut(&semantic_hash)?;
        let mut equivalent = None;
        bucket.retain(|candidate| {
            let Some(candidate) = candidate.upgrade() else {
                return false;
            };
            if equivalent.is_none() && candidate.semantically_equivalent(plan) {
                equivalent = Some(candidate);
            }
            true
        });
        equivalent
    }

    fn insert_handle(&mut self, prepared: Arc<PreparedPlan>) -> PhysicalPlanHandle {
        let handle = self.next_handle;
        self.next_handle = self.next_handle.saturating_add(1).max(1);
        let identity = Arc::as_ptr(&prepared) as usize;
        let owners = self.owner_counts.entry(identity).or_default();
        if *owners == 0 {
            self.diagnostics.prepared_bytes_current = self
                .diagnostics
                .prepared_bytes_current
                .saturating_add(prepared.stats().estimated_bytes);
            self.diagnostics.prepared_bytes_peak = self
                .diagnostics
                .prepared_bytes_peak
                .max(self.diagnostics.prepared_bytes_current);
        }
        *owners += 1;
        self.handles.insert(handle, prepared);
        handle
    }

    pub fn get(&self, handle: PhysicalPlanHandle) -> Option<Arc<PreparedPlan>> {
        self.handles.get(&handle).cloned()
    }

    pub fn remove(&mut self, handle: PhysicalPlanHandle) -> Option<Arc<PreparedPlan>> {
        let prepared = self.handles.remove(&handle)?;
        let identity = Arc::as_ptr(&prepared) as usize;
        let mut final_owner = false;
        if let Some(owners) = self.owner_counts.get_mut(&identity) {
            *owners = owners.saturating_sub(1);
            if *owners == 0 {
                final_owner = true;
                self.owner_counts.remove(&identity);
                self.diagnostics.prepared_bytes_current = self
                    .diagnostics
                    .prepared_bytes_current
                    .saturating_sub(prepared.stats().estimated_bytes);
            }
        }
        self.canonical.retain(|_, bucket| {
            bucket.retain(|candidate| {
                candidate.strong_count() > 0
                    && (!final_owner || candidate.as_ptr() as usize != identity)
            });
            !bucket.is_empty()
        });
        Some(prepared)
    }

    pub fn note_schema_invalidation(&mut self) {
        self.diagnostics.schema_invalidations += 1;
    }

    pub fn diagnostics(&self) -> &PlanCacheDiagnostics {
        &self.diagnostics
    }

    pub fn reset_diagnostics(&mut self) {
        let current = self.diagnostics.prepared_bytes_current;
        self.diagnostics = PlanCacheDiagnostics {
            prepared_bytes_current: current,
            prepared_bytes_peak: current,
            ..PlanCacheDiagnostics::default()
        };
    }

    pub fn len(&self) -> usize {
        self.handles.len()
    }

    pub fn unique_prepared_len(&self) -> usize {
        self.owner_counts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.handles.is_empty()
    }
}

fn semantic_hash(plan: &PhysicalPlan) -> u64 {
    use std::hash::{Hash, Hasher};

    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    format!("{plan:?}").hash(&mut hasher);
    hasher.finish()
}
