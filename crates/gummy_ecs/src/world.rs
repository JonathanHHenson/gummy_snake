use std::collections::{BTreeSet, HashMap};
use std::sync::Arc;

use crate::archetype::{Archetype, ComponentSetKey};
use crate::column::EcsValue;
use crate::command::CommandBuffer;
use crate::diagnostics::Diagnostics;
use crate::entity::{Entity, EntityAllocator};
use crate::event::EventStore;
use crate::execution::CachedSpatialIndex;
use crate::plan::PlanCache;
use crate::query::{ArchetypeFilterKey, CachedQuery, CompiledQueryFilter, QueryFilter};
use crate::resource::ResourceStore;
use crate::schema::SchemaRegistry;
use crate::tag::{EntityTags, TagRegistry};

mod change_journal;
mod commands;
mod entity_archetype;
mod fields;
mod location;
mod plan_cache;
mod queries;
mod resources_events;
mod state_diagnostics;

use location::{DenseEntityLocations, EntityLocation};

pub use change_journal::{
    ChangeEpoch, ChangeJournal, ChangeKind, ChangeRecord, ChangeRevision, ComponentChange,
    EntityChange, TagChange,
};

#[derive(Debug, Clone)]
pub(crate) struct CachedExecutionQuery {
    pub(crate) structural_revision: u64,
    pub(crate) rows: Arc<Vec<Entity>>,
    pub(crate) locations: Arc<Vec<(usize, usize)>>,
}

#[derive(Debug, Default)]
pub struct World {
    entities: EntityAllocator,
    schemas: SchemaRegistry,
    archetypes: Vec<Archetype>,
    archetype_by_key: HashMap<ComponentSetKey, usize>,
    archetype_generation: u64,
    locations: DenseEntityLocations,
    entity_order: BTreeSet<Entity>,
    tag_registry: TagRegistry,
    entity_tags: EntityTags,
    staged: CommandBuffer,
    query_cache: HashMap<ComponentSetKey, CachedQuery>,
    filtered_query_cache: HashMap<ArchetypeFilterKey, CachedQuery>,
    compiled_query_cache: HashMap<QueryFilter, CompiledQueryFilter>,
    execution_query_cache: HashMap<QueryFilter, CachedExecutionQuery>,
    resources: ResourceStore,
    events: EventStore,
    compiled_plans: PlanCache,
    compiled_plan_spatial_cache_keys: HashMap<u64, Vec<String>>,
    spatial_cache_ref_counts: HashMap<String, usize>,
    input_states: HashMap<(String, Option<i64>), EcsValue>,
    current_frame: u64,
    structural_revision: u64,
    field_revision: u64,
    field_revisions: HashMap<(String, String), u64>,
    change_journal: ChangeJournal,
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
            entity_order: self.entity_order.clone(),
            tag_registry: self.tag_registry.clone(),
            entity_tags: self.entity_tags.clone(),
            staged: self.staged.clone(),
            query_cache: self.query_cache.clone(),
            filtered_query_cache: self.filtered_query_cache.clone(),
            compiled_query_cache: self.compiled_query_cache.clone(),
            execution_query_cache: self.execution_query_cache.clone(),
            resources: self.resources.clone(),
            events: self.events.clone(),
            compiled_plans: self.compiled_plans.clone(),
            compiled_plan_spatial_cache_keys: self.compiled_plan_spatial_cache_keys.clone(),
            spatial_cache_ref_counts: self.spatial_cache_ref_counts.clone(),
            input_states: self.input_states.clone(),
            current_frame: self.current_frame,
            structural_revision: self.structural_revision,
            field_revision: self.field_revision,
            field_revisions: self.field_revisions.clone(),
            change_journal: self.change_journal.clone(),
            spatial_index_cache: HashMap::new(),
            diagnostics: self.diagnostics.clone(),
        }
    }
}

impl World {
    pub fn new() -> Self {
        Self::default()
    }

    pub(crate) fn schema_registry(&self) -> &SchemaRegistry {
        &self.schemas
    }

    pub(crate) fn schema_version(&self) -> u64 {
        self.schemas.version()
    }

    pub(crate) fn note_plan_schema_invalidation(&mut self) {
        self.compiled_plans.note_schema_invalidation();
    }
}

#[cfg(test)]
mod tests;
