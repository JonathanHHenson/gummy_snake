use crate::archetype::{Archetype, ComponentSetKey, EntityRowData};
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::schema::ComponentSchema;

use super::{ChangeKind, EntityLocation, World};

impl World {
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
        self.change_journal.record(entity, ChangeKind::Spawned);
        self.note_structural_revision();
        entity
    }

    pub fn spawn_with_defaults(
        &mut self,
        components: impl IntoIterator<Item = String>,
    ) -> Result<Entity> {
        let key = ComponentSetKey::new(components);
        self.validate_component_set(&key)?;
        let component_names = key.component_names().cloned().collect::<Vec<_>>();
        let tag_names = key.tag_names().map(ToString::to_string).collect::<Vec<_>>();
        let entity = self.entities.spawn();
        let archetype = self.ensure_archetype(key)?;
        let row = self.archetypes[archetype].push_default_row(entity)?;
        self.locations
            .insert(entity.raw(), EntityLocation { archetype, row });
        self.change_journal.record(entity, ChangeKind::Spawned);
        for component in component_names {
            self.change_journal
                .record(entity, ChangeKind::ComponentAdded { component });
        }
        for tag in tag_names {
            self.change_journal
                .record(entity, ChangeKind::TagAdded { tag });
        }
        self.note_structural_revision();
        Ok(entity)
    }

    pub fn despawn(&mut self, entity: Entity) -> Result<()> {
        let location = self.location(entity)?;
        let key = self.archetypes[location.archetype].key().clone();
        self.remove_entity_row(entity)?;
        self.entities.despawn(entity)?;
        for component in key.component_names() {
            self.change_journal.record(
                entity,
                ChangeKind::ComponentRemoved {
                    component: component.clone(),
                },
            );
        }
        for tag in key.tag_names() {
            self.change_journal.record(
                entity,
                ChangeKind::TagRemoved {
                    tag: tag.to_string(),
                },
            );
        }
        self.change_journal.record(entity, ChangeKind::Despawned);
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

    pub fn add_component_default(
        &mut self,
        entity: Entity,
        component: impl Into<String>,
    ) -> Result<()> {
        let component: String = component.into();
        if !self.schemas.contains(&component) {
            return Err(EcsError::UnknownSchema(component));
        }
        let location = self.location(entity)?;
        let old_key = self.archetypes[location.archetype].key().clone();
        if old_key.contains_component(&component) {
            return Err(EcsError::DuplicateComponent(component));
        }
        let new_key = old_key.with(&component);
        self.move_entity_to_archetype(entity, new_key, None)?;
        self.change_journal
            .record(entity, ChangeKind::ComponentAdded { component });
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
        self.change_journal.record(
            entity,
            ChangeKind::ComponentRemoved {
                component: component.to_string(),
            },
        );
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
        self.change_journal.record(
            entity,
            ChangeKind::TagAdded {
                tag: tag.to_string(),
            },
        );
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
        self.change_journal.record(
            entity,
            ChangeKind::TagRemoved {
                tag: tag.to_string(),
            },
        );
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub(super) fn validate_component_set(&self, key: &ComponentSetKey) -> Result<()> {
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

    pub(super) fn location(&self, entity: Entity) -> Result<EntityLocation> {
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
}
