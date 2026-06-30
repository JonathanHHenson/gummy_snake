use std::collections::HashMap;

use crate::archetype::{Archetype, ComponentRow, ComponentSetKey, EntityRowData};
use crate::column::EcsValue;
use crate::command::{Command, CommandBuffer};
use crate::diagnostics::Diagnostics;
use crate::entity::{Entity, EntityAllocator};
use crate::error::{EcsError, Result};
use crate::event::{EventRecord, EventStore};
use crate::plan::{
    compile_bridge_plan, BridgePlanPayload, PhysicalPlan, PhysicalPlanHandle, PlanCache,
};
use crate::query::{CachedQuery, QueryFilter, QuerySnapshot};
use crate::resource::ResourceStore;
use crate::schema::{ComponentSchema, SchemaRegistry};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct EntityLocation {
    archetype: usize,
    row: usize,
}

#[derive(Debug, Default, Clone)]
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
    diagnostics: Diagnostics,
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
        Ok(entity)
    }

    pub fn despawn(&mut self, entity: Entity) -> Result<()> {
        self.entities.validate(entity)?;
        self.remove_entity_row(entity)?;
        self.entities.despawn(entity)?;
        self.diagnostics.structural_commands_applied += 1;
        self.invalidate_query_cache();
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
        Ok(())
    }

    pub fn set_field(
        &mut self,
        entity: Entity,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<()> {
        let value = self.coerce_value_for_component_field(component, field, value)?;
        let location = self.location(entity)?;
        self.archetypes[location.archetype].set_field(location.row, component, field, value)
    }

    pub(crate) fn set_field_f64(
        &mut self,
        entity: Entity,
        component: &str,
        field: &str,
        value: f64,
    ) -> Result<()> {
        let location = self.location(entity)?;
        self.archetypes[location.archetype].set_field_f64(location.row, component, field, value)
    }

    pub fn get_field(&self, entity: Entity, component: &str, field: &str) -> Result<EcsValue> {
        let location = self.location(entity)?;
        self.archetypes[location.archetype].get_field(location.row, component, field)
    }

    pub fn get_field_f64(&self, entity: Entity, component: &str, field: &str) -> Result<f64> {
        let location = self.location(entity)?;
        self.archetypes[location.archetype].get_field_f64(location.row, component, field)
    }

    pub fn insert_resource(&mut self, name: impl Into<String>, value: ComponentRow) -> Result<()> {
        let name = name.into();
        let value = self.coerce_component_row(&name, value)?;
        self.resources.insert(&self.schemas, name, value)
    }

    pub fn remove_resource(&mut self, name: &str) -> Result<ComponentRow> {
        self.resources.remove(name)
    }

    pub fn resource_field(&self, name: &str, field: &str) -> Result<EcsValue> {
        self.resources.get_field(name, field)
    }

    pub fn set_resource_field(&mut self, name: &str, field: &str, value: EcsValue) -> Result<()> {
        let value = self.coerce_value_for_component_field(name, field, value)?;
        self.resources.set_field(name, field, value)
    }

    pub fn has_resource(&self, name: &str) -> bool {
        self.resources.contains(name)
    }

    pub fn resource_count(&self) -> usize {
        self.resources.len()
    }

    pub fn resource_revision(&self, name: &str) -> u64 {
        self.resources.revision(name)
    }

    pub fn set_frame(&mut self, frame: u64) {
        self.current_frame = frame;
        self.events.begin_frame(frame);
    }

    pub fn emit_event(&mut self, event_type: &str, payload: EcsValue) -> Result<()> {
        self.events.validate_type(event_type)?;
        self.events.emit(event_type, self.current_frame, payload);
        Ok(())
    }

    pub fn read_events(&self, event_type: &str) -> Result<Vec<EventRecord>> {
        self.events.validate_type(event_type)?;
        Ok(self.events.read(event_type))
    }

    pub fn clear_events(&mut self, event_type: Option<&str>) {
        self.events.clear(event_type);
    }

    pub fn event_queue_len(&self, event_type: &str) -> usize {
        self.events.queue_len(event_type)
    }

    pub fn stage_spawn(&mut self, components: impl IntoIterator<Item = String>) {
        self.staged.push(Command::Spawn {
            components: components.into_iter().collect(),
        });
    }

    pub fn stage_despawn(&mut self, entity: Entity) {
        self.staged.push(Command::Despawn { entity });
    }

    pub fn stage_add_component(&mut self, entity: Entity, component: impl Into<String>) {
        self.staged.push(Command::AddComponent {
            entity,
            component: component.into(),
        });
    }

    pub fn stage_remove_component(&mut self, entity: Entity, component: impl Into<String>) {
        self.staged.push(Command::RemoveComponent {
            entity,
            component: component.into(),
        });
    }

    pub fn apply_staged(&mut self) -> Result<()> {
        let commands: Vec<_> = self.staged.drain().collect();
        for command in commands {
            match command {
                Command::Spawn { components } => {
                    self.spawn_with_defaults(components)?;
                }
                Command::Despawn { entity } => {
                    self.despawn(entity)?;
                }
                Command::AddComponent { entity, component } => {
                    self.add_component_default(entity, component)?;
                }
                Command::RemoveComponent { entity, component } => {
                    self.remove_component(entity, &component)?;
                }
            }
            self.diagnostics.staged_commands_applied += 1;
        }
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

    fn invalidate_query_cache(&mut self) {
        if !self.query_cache.is_empty() || !self.filtered_query_cache.is_empty() {
            self.diagnostics.query_cache_invalidations += 1;
        }
        self.query_cache.clear();
        self.filtered_query_cache.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::query::{QueryFilter, QueryTerm};
    use crate::schema::{FieldSchema, StorageType};

    fn register_position_velocity(world: &mut World) {
        world
            .register_schema(ComponentSchema::new(
                "Position",
                vec![
                    FieldSchema::new("x", StorageType::Float64),
                    FieldSchema::new("y", StorageType::Float64),
                ],
            ))
            .unwrap();
        world
            .register_schema(ComponentSchema::new(
                "Velocity",
                vec![FieldSchema::new("dx", StorageType::Float64)],
            ))
            .unwrap();
    }

    #[test]
    fn archetype_spawn_query_and_structural_moves_are_deterministic() {
        let mut world = World::new();
        register_position_velocity(&mut world);
        let first = world
            .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
            .unwrap();
        let second = world.spawn_with_defaults(["Position".to_string()]).unwrap();
        world
            .set_field(first, "Position", "x", EcsValue::F64(12.0))
            .unwrap();

        assert_eq!(
            world.query(["Position".to_string()]).unwrap(),
            vec![first, second]
        );
        assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![first]);
        assert_eq!(
            world.get_field(first, "Position", "x").unwrap(),
            EcsValue::F64(12.0)
        );

        world.add_component_default(second, "Velocity").unwrap();
        assert_eq!(
            world.query(["Velocity".to_string()]).unwrap(),
            vec![first, second]
        );
        world.remove_component(first, "Velocity").unwrap();
        assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![second]);
    }

    #[test]
    fn command_buffer_applies_in_submission_order() {
        let mut world = World::new();
        register_position_velocity(&mut world);
        let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
        world.stage_add_component(entity, "Velocity");
        world.stage_remove_component(entity, "Velocity");
        world.apply_staged().unwrap();
        assert_eq!(
            world.entity_components(entity).unwrap(),
            vec!["Position".to_string()]
        );
        assert_eq!(world.diagnostics().staged_commands_applied, 2);
    }

    #[test]
    fn cached_queries_are_invalidated_by_structural_changes() {
        let mut world = World::new();
        register_position_velocity(&mut world);
        let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
        assert_eq!(
            world.query(["Velocity".to_string()]).unwrap(),
            Vec::<Entity>::new()
        );
        assert_eq!(
            world.query(["Velocity".to_string()]).unwrap(),
            Vec::<Entity>::new()
        );
        world.add_component_default(entity, "Velocity").unwrap();
        assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![entity]);
        let diagnostics = world.diagnostics();
        assert!(diagnostics.query_cache_hits >= 1);
        assert!(diagnostics.query_cache_invalidations >= 1);
        assert!(diagnostics.query_matched_archetypes >= 1);
        assert!(diagnostics.query_matched_rows >= 1);
    }

    #[test]
    fn filtered_queries_support_required_and_excluded_tags() {
        let mut world = World::new();
        register_position_velocity(&mut world);
        let hero = world.spawn_with_defaults(["Position".to_string()]).unwrap();
        let enemy = world
            .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
            .unwrap();
        world.add_tag(hero, "Hero").unwrap();
        world.add_tag(enemy, "Enemy").unwrap();

        let heroes_without_velocity = world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::WithTag("Hero".to_string()),
                QueryTerm::WithoutComponent("Velocity".to_string()),
                QueryTerm::WithoutTag("Enemy".to_string()),
            ]))
            .unwrap();
        assert_eq!(heroes_without_velocity, vec![hero]);
        assert_eq!(world.entity_tags(hero).unwrap(), vec!["Hero".to_string()]);
        assert_eq!(
            world
                .snapshot_query_filter(QueryFilter::default())
                .unwrap()
                .len(),
            2
        );
    }

    #[test]
    fn resources_and_events_are_owned_by_world() {
        let mut world = World::new();
        world
            .register_schema(ComponentSchema::new(
                "Clock",
                vec![FieldSchema::new("tick", StorageType::Int64)],
            ))
            .unwrap();
        let mut row = ComponentRow::new();
        row.insert("tick".to_string(), EcsValue::I64(1));
        world.insert_resource("Clock", row).unwrap();
        world
            .set_resource_field("Clock", "tick", EcsValue::I64(2))
            .unwrap();
        assert_eq!(
            world.resource_field("Clock", "tick").unwrap(),
            EcsValue::I64(2)
        );
        assert_eq!(world.resource_revision("Clock"), 2);

        world.set_frame(3);
        world.emit_event("Ping", EcsValue::I64(7)).unwrap();
        let events = world.read_events("Ping").unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].payload, EcsValue::I64(7));
        assert_eq!(world.diagnostics().event_queues_total, 1);
    }
}
