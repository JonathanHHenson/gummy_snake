use std::collections::{HashMap, HashSet};

use crate::archetype::{Archetype, ComponentSetKey};
use crate::column::EcsValue;
use crate::command::CommandBuffer;
use crate::diagnostics::Diagnostics;
use crate::entity::EntityAllocator;
use crate::event::EventStore;
use crate::execution::CachedSpatialIndex;
use crate::plan::PlanCache;
use crate::query::{CachedQuery, QueryFilter};
use crate::resource::ResourceStore;
use crate::schema::SchemaRegistry;

mod commands;
mod entity_archetype;
mod fields;
mod plan_cache;
mod queries;
mod resources_events;
mod state_diagnostics;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct EntityLocation {
    archetype: usize,
    row: usize,
}

#[derive(Debug, Default)]
pub struct World {
    entities: EntityAllocator,
    schemas: SchemaRegistry,
    archetypes: Vec<Archetype>,
    archetype_by_key: HashMap<ComponentSetKey, usize>,
    archetype_generation: u64,
    locations: HashMap<u64, EntityLocation>,
    staged: CommandBuffer,
    query_cache: HashMap<ComponentSetKey, CachedQuery>,
    filtered_query_cache: HashMap<QueryFilter, CachedQuery>,
    resources: ResourceStore,
    events: EventStore,
    compiled_plans: PlanCache,
    compiled_plan_spatial_cache_keys: HashMap<u64, HashSet<String>>,
    input_states: HashMap<(String, Option<i64>), EcsValue>,
    current_frame: u64,
    structural_revision: u64,
    field_revision: u64,
    field_revisions: HashMap<(String, String), u64>,
    spatial_index_cache: HashMap<String, CachedSpatialIndex>,
    diagnostics: Diagnostics,
}

impl Clone for World {
    fn clone(&self) -> Self {
        Self {
            entities: self.entities.clone(),
            schemas: self.schemas.clone(),
            archetypes: self.archetypes.clone(),
            archetype_by_key: self.archetype_by_key.clone(),
            archetype_generation: self.archetype_generation,
            locations: self.locations.clone(),
            staged: self.staged.clone(),
            query_cache: HashMap::new(),
            filtered_query_cache: HashMap::new(),
            resources: self.resources.clone(),
            events: self.events.clone(),
            compiled_plans: self.compiled_plans.clone(),
            compiled_plan_spatial_cache_keys: self.compiled_plan_spatial_cache_keys.clone(),
            input_states: self.input_states.clone(),
            current_frame: self.current_frame,
            structural_revision: self.structural_revision,
            field_revision: self.field_revision,
            field_revisions: self.field_revisions.clone(),
            spatial_index_cache: HashMap::new(),
            diagnostics: self.diagnostics.clone(),
        }
    }
}

impl World {
    pub fn new() -> Self {
        Self::default()
    }
}

#[cfg(test)]
mod tests;
