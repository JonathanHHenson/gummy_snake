use std::collections::HashMap;

use crate::archetype::{Archetype, ComponentSetKey, EntityRowData};
use crate::column::EcsValue;
use crate::command::CommandBuffer;
use crate::diagnostics::Diagnostics;
use crate::entity::{Entity, EntityAllocator};
use crate::error::{EcsError, Result};
use crate::event::EventStore;
use crate::execution::CachedSpatialIndex;
use crate::plan::{
    compile_bridge_plan, BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle, PlanCache,
};
use crate::query::{CachedQuery, QueryFilter, QuerySnapshot};
use crate::resource::ResourceStore;
use crate::schema::{ComponentSchema, SchemaRegistry};

mod commands;
mod fields;
mod resources_events;

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

    pub fn spawn_empty(&mut self) -> Entity {
        let entity = self.entities.spawn();
        let archetype = self
            .ensure_archetype(ComponentSetKey::empty())
            .expect("empty archetype");
        let row = self.archetypes[archetype]
            .push_default_row(entity)
            .expect("empty archetype row");
        self.locations
            .insert(entity.raw(), EntityLocation { archetype, row });
        self.note_structural_revision();
        entity
    }

    pub fn spawn_with_defaults(
        &mut self,
        components: impl IntoIterator<Item = String>,
    ) -> Result<Entity> {
        let key = ComponentSetKey::new(components);
        self.validate_component_set(&key)?;
        let entity = self.entities.spawn();
        let archetype = self.ensure_archetype(key)?;
        let row = self.archetypes[archetype].push_default_row(entity)?;
        self.locations
            .insert(entity.raw(), EntityLocation { archetype, row });
        self.note_structural_revision();
        Ok(entity)
    }

    pub fn despawn(&mut self, entity: Entity) -> Result<()> {
        self.entities.validate(entity)?;
        self.remove_entity_row(entity)?;
        self.entities.despawn(entity)?;
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn validate_entity(&self, entity: Entity) -> Result<()> {
        self.entities.validate(entity)
    }

    pub fn alive_count(&self) -> usize {
        self.entities.alive_count()
    }

    pub fn register_schema(&mut self, schema: ComponentSchema) -> Result<()> {
        self.schemas.register(schema)?;
        self.diagnostics.component_schemas_total = self.schemas.len();
        Ok(())
    }

    pub fn schema(&self, name: &str) -> Option<&ComponentSchema> {
        self.schemas.get(name)
    }

    pub fn schema_count(&self) -> usize {
        self.schemas.len()
    }

    pub fn schema_fingerprint(&self) -> u64 {
        self.schemas.fingerprint()
    }

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

    pub fn structural_revision(&self) -> u64 {
        self.structural_revision
    }

    pub fn field_revision(&self) -> u64 {
        self.field_revision
    }

    pub fn component_field_revision(&self, component: &str, field: &str) -> u64 {
        self.field_revisions
            .get(&(component.to_string(), field.to_string()))
            .copied()
            .unwrap_or(0)
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

    pub fn set_input_state(&mut self, name: impl Into<String>, code: Option<i64>, value: EcsValue) {
        self.input_states.insert((name.into(), code), value);
    }

    pub(crate) fn input_state(&self, name: &str, code: Option<i64>) -> Option<EcsValue> {
        self.input_states.get(&(name.to_string(), code)).cloned()
    }

    pub fn archetype_count(&self) -> usize {
        self.archetypes.len()
    }

    pub fn staged_command_count(&self) -> usize {
        self.staged.len()
    }

    pub fn diagnostics(&self) -> Diagnostics {
        let mut diagnostics = self.diagnostics.clone();
        diagnostics.entities_alive = self.entities.alive_count();
        diagnostics.entity_generation_reuses = self.entities.generation_reuses();
        diagnostics.component_schemas_total = self.schemas.len();
        diagnostics.archetypes_total = self.archetypes.len();
        diagnostics.resources_total = self.resources.len();
        diagnostics.event_queues_total = self.events.queue_count();
        diagnostics
    }

    pub fn reset_diagnostics(&mut self) {
        self.diagnostics = Diagnostics::default();
    }

    pub fn entity_components(&self, entity: Entity) -> Result<Vec<String>> {
        let location = self.location(entity)?;
        Ok(self.archetypes[location.archetype]
            .key()
            .component_names()
            .cloned()
            .collect())
    }

    pub fn entity_tags(&self, entity: Entity) -> Result<Vec<String>> {
        let location = self.location(entity)?;
        Ok(self.archetypes[location.archetype]
            .key()
            .tag_names()
            .map(ToString::to_string)
            .collect())
    }

    pub fn query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<Vec<Entity>> {
        let required = ComponentSetKey::new(required_components);
        self.validate_component_set(&required)?;
        let archetypes = self.matching_archetypes(required);
        let mut entities = Vec::new();
        for archetype_index in archetypes {
            entities.extend_from_slice(self.archetypes[archetype_index].entities());
        }
        entities.sort_by_key(|entity| entity.raw());
        self.diagnostics.query_matched_rows += entities.len();
        Ok(entities)
    }

    pub fn snapshot_query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<QuerySnapshot> {
        self.query(required_components).map(QuerySnapshot::new)
    }

    pub fn query_filter(&mut self, filter: QueryFilter) -> Result<Vec<Entity>> {
        let required = filter.required_components();
        self.validate_component_set(&required)?;
        let archetypes = self.matching_archetypes_for_filter(filter);
        let mut entities = Vec::new();
        for archetype_index in archetypes {
            entities.extend_from_slice(self.archetypes[archetype_index].entities());
        }
        entities.sort_by_key(|entity| entity.raw());
        self.diagnostics.query_matched_rows += entities.len();
        Ok(entities)
    }

    pub fn snapshot_query_filter(&mut self, filter: QueryFilter) -> Result<QuerySnapshot> {
        self.query_filter(filter).map(QuerySnapshot::new)
    }

    pub fn add_component_default(
        &mut self,
        entity: Entity,
        component: impl Into<String>,
    ) -> Result<()> {
        let component = component.into();
        if !self.schemas.contains(&component) {
            return Err(EcsError::UnknownSchema(component));
        }
        let location = self.location(entity)?;
        let old_key = self.archetypes[location.archetype].key().clone();
        if old_key.contains_component(&component) {
            return Err(EcsError::DuplicateComponent(component));
        }
        let new_key = old_key.with(component);
        self.move_entity_to_archetype(entity, new_key, None)?;
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn remove_component(&mut self, entity: Entity, component: &str) -> Result<()> {
        let location = self.location(entity)?;
        let old_key = self.archetypes[location.archetype].key().clone();
        if !old_key.contains_component(component) {
            return Err(EcsError::MissingComponent(component.to_string()));
        }
        let new_key = old_key.without(component);
        self.move_entity_to_archetype(entity, new_key, Some(component))?;
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn add_tag(&mut self, entity: Entity, tag: &str) -> Result<()> {
        if tag.is_empty() {
            return Err(EcsError::InvalidPlan(
                "ECS tag name cannot be empty".to_string(),
            ));
        }
        let location = self.location(entity)?;
        let old_key = self.archetypes[location.archetype].key().clone();
        if old_key.contains_tag(tag) {
            return Ok(());
        }
        self.move_entity_to_archetype(entity, old_key.with_tag(tag), None)?;
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn remove_tag(&mut self, entity: Entity, tag: &str) -> Result<()> {
        let location = self.location(entity)?;
        let old_key = self.archetypes[location.archetype].key().clone();
        if !old_key.contains_tag(tag) {
            return Ok(());
        }
        self.move_entity_to_archetype(entity, old_key.without_tag(tag), None)?;
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    fn validate_component_set(&self, key: &ComponentSetKey) -> Result<()> {
        for component in key.component_names() {
            if !self.schemas.contains(component) {
                return Err(EcsError::UnknownSchema(component.clone()));
            }
        }
        Ok(())
    }

    fn ensure_archetype(&mut self, key: ComponentSetKey) -> Result<usize> {
        if let Some(index) = self.archetype_by_key.get(&key) {
            return Ok(*index);
        }
        let index = self.archetypes.len();
        let archetype = Archetype::new(key.clone(), self.schemas.all())?;
        self.archetypes.push(archetype);
        self.archetype_by_key.insert(key, index);
        self.archetype_generation = self.archetype_generation.wrapping_add(1);
        self.diagnostics.archetypes_total = self.archetypes.len();
        self.invalidate_query_cache();
        Ok(index)
    }

    fn location(&self, entity: Entity) -> Result<EntityLocation> {
        self.entities.validate(entity)?;
        self.locations
            .get(&entity.raw())
            .copied()
            .ok_or(EcsError::StaleEntity {
                index: entity.index,
                generation: entity.generation,
            })
    }

    fn remove_entity_row(&mut self, entity: Entity) -> Result<EntityRowData> {
        let location = self.location(entity)?;
        let removed = self.archetypes[location.archetype].remove_row_swap_remove(location.row)?;
        debug_assert_eq!(removed.entity, entity);
        self.locations.remove(&entity.raw());
        if let Some(swapped) = removed.swapped_entity {
            self.locations.insert(
                swapped.raw(),
                EntityLocation {
                    archetype: location.archetype,
                    row: location.row,
                },
            );
        }
        Ok(removed.data)
    }

    fn move_entity_to_archetype(
        &mut self,
        entity: Entity,
        new_key: ComponentSetKey,
        removed_component: Option<&str>,
    ) -> Result<()> {
        self.validate_component_set(&new_key)?;
        let mut data = self.remove_entity_row(entity)?;
        if let Some(component) = removed_component {
            data.remove(component);
        }
        let new_archetype = self.ensure_archetype(new_key)?;
        let row = self.archetypes[new_archetype].push_row(entity, Some(&data))?;
        self.locations.insert(
            entity.raw(),
            EntityLocation {
                archetype: new_archetype,
                row,
            },
        );
        self.diagnostics.archetype_moves += 1;
        self.invalidate_query_cache();
        Ok(())
    }

    fn matching_archetypes(&mut self, required: ComponentSetKey) -> Vec<usize> {
        if let Some(cached) = self.query_cache.get(&required) {
            if cached.generation_seen == self.archetype_generation {
                self.diagnostics.query_cache_hits += 1;
                self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
                return cached.matched_archetypes.clone();
            }
            self.diagnostics.query_cache_refreshes += 1;
        } else {
            self.diagnostics.query_cache_misses += 1;
        }
        let matches = self
            .archetypes
            .iter()
            .enumerate()
            .filter_map(|(index, archetype)| {
                archetype.key().is_superset_of(&required).then_some(index)
            })
            .collect::<Vec<_>>();
        self.diagnostics.query_matched_archetypes += matches.len();
        self.query_cache.insert(
            required,
            CachedQuery::new(self.archetype_generation, matches.clone()),
        );
        matches
    }

    fn matching_archetypes_for_filter(&mut self, filter: QueryFilter) -> Vec<usize> {
        if let Some(cached) = self.filtered_query_cache.get(&filter) {
            if cached.generation_seen == self.archetype_generation {
                self.diagnostics.query_cache_hits += 1;
                self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
                return cached.matched_archetypes.clone();
            }
            self.diagnostics.query_cache_refreshes += 1;
        } else {
            self.diagnostics.query_cache_misses += 1;
        }
        let matches = self
            .archetypes
            .iter()
            .enumerate()
            .filter_map(|(index, archetype)| filter.matches_key(archetype.key()).then_some(index))
            .collect::<Vec<_>>();
        self.diagnostics.query_matched_archetypes += matches.len();
        self.filtered_query_cache.insert(
            filter,
            CachedQuery::new(self.archetype_generation, matches.clone()),
        );
        matches
    }

    fn note_structural_revision(&mut self) {
        self.structural_revision = self.structural_revision.saturating_add(1);
        self.invalidate_query_cache();
    }

    fn note_field_revision(&mut self, component: &str, field: &str) {
        self.note_field_revision_by(component, field, 1);
    }

    fn note_field_revision_by(&mut self, component: &str, field: &str, count: u64) {
        if count == 0 {
            return;
        }
        self.field_revision = self.field_revision.saturating_add(count);
        let key = (component.to_string(), field.to_string());
        let revision = self.field_revisions.entry(key).or_default();
        *revision = revision.saturating_add(count);
    }

    fn invalidate_query_cache(&mut self) {
        if !self.query_cache.is_empty() || !self.filtered_query_cache.is_empty() {
            self.diagnostics.query_cache_invalidations += 1;
        }
        self.query_cache.clear();
        self.filtered_query_cache.clear();
    }
}

#[cfg(test)]
mod tests;
