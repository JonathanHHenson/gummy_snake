use crate::archetype::{Archetype, ComponentSetKey, EntityRowData, SpawnEntity};
use crate::column::coerce_value_for_storage;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::schema::{ComponentId, ComponentSchema};

use super::{ChangeKind, EntityLocation, World};

const TAG_PREFIX: &str = "#tag:";

struct PreparedSpawn {
    key: ComponentSetKey,
    component_names: Vec<String>,
    components: EntityRowData,
    tags: Vec<String>,
}

impl World {
    pub fn spawn_empty(&mut self) -> Entity {
        let archetype = self
            .ensure_archetype(ComponentSetKey::empty())
            .expect("empty archetype");
        let entity = self.entities.spawn();
        self.entity_tags.clear_slot(entity.index);
        let row = self.archetypes[archetype]
            .push_default_row(entity)
            .expect("empty archetype row");
        self.locations.insert(entity, archetype, row);
        self.entity_order.insert(entity);
        self.change_journal.record(entity, ChangeKind::Spawned);
        self.note_structural_revision();
        entity
    }

    /// Spawn complete component rows in one all-or-nothing structural transaction.
    ///
    /// Every schema, field, value, and tag is validated before the first archetype,
    /// allocator, journal, or revision mutation. Once validation succeeds, insertion
    /// uses only the prevalidated physical values and cannot produce a data error.
    pub fn spawn_batch(&mut self, rows: Vec<SpawnEntity>) -> Result<Vec<Entity>> {
        let prepared = rows
            .into_iter()
            .map(|row| self.prepare_spawn(row))
            .collect::<Result<Vec<_>>>()?;

        let archetypes = prepared
            .iter()
            .map(|row| {
                self.ensure_archetype(row.key.clone())
                    .expect("prevalidated spawn key must build an archetype")
            })
            .collect::<Vec<_>>();
        let mut entities = Vec::with_capacity(prepared.len());

        for (row, archetype) in prepared.into_iter().zip(archetypes) {
            let entity = self.entities.spawn();
            self.entity_tags.clear_slot(entity.index);
            let entity_row = self.archetypes[archetype]
                .push_row(entity, Some(&row.components))
                .expect("prevalidated spawn row must match its archetype");
            self.locations.insert(entity, archetype, entity_row);
            self.entity_order.insert(entity);
            for tag in &row.tags {
                let tag_id = self.tag_registry.intern(tag);
                self.entity_tags.add(entity.index, tag_id);
            }
            self.change_journal.record(entity, ChangeKind::Spawned);
            for component in row.component_names {
                self.change_journal.record(
                    entity,
                    ChangeKind::ComponentAdded {
                        component: component.into(),
                    },
                );
            }
            for tag in row.tags {
                self.change_journal
                    .record(entity, ChangeKind::TagAdded { tag: tag.into() });
            }
            self.diagnostics.structural_commands_applied += 1;
            self.note_structural_revision();
            entities.push(entity);
        }

        self.diagnostics.bulk_spawn_calls += 1;
        self.diagnostics.bulk_spawn_entities += entities.len();
        Ok(entities)
    }

    fn prepare_spawn(&self, row: SpawnEntity) -> Result<PreparedSpawn> {
        let mut component_names = row.components.keys().cloned().collect::<Vec<_>>();
        component_names.sort();
        let key = self.component_key_for_names(component_names.iter().map(String::as_str))?;
        let mut components = EntityRowData::with_capacity(row.components.len());

        for component_name in &component_names {
            let schema = self
                .schemas
                .get(component_name)
                .ok_or_else(|| EcsError::UnknownSchema(component_name.clone()))?;
            let mut input = row
                .components
                .get(component_name)
                .cloned()
                .expect("component name came from the spawn row");
            let mut normalized = crate::archetype::ComponentRow::with_capacity(schema.fields.len());
            for field in &schema.fields {
                let value = input.remove(&field.name).ok_or_else(|| {
                    EcsError::InvalidPlan(format!(
                        "transactional spawn row is missing {}.{}",
                        component_name, field.name
                    ))
                })?;
                normalized.insert(
                    field.name.clone(),
                    coerce_value_for_storage(field.storage_type, value)?,
                );
            }
            if let Some(field) = input.keys().min() {
                return Err(EcsError::UnknownField {
                    component: component_name.clone(),
                    field: field.clone(),
                });
            }
            components.insert(component_name.clone(), normalized);
        }

        let mut tags = row.tags;
        if tags.iter().any(String::is_empty) {
            return Err(EcsError::InvalidPlan(
                "ECS tag name cannot be empty".to_string(),
            ));
        }
        tags.sort();
        tags.dedup();
        Ok(PreparedSpawn {
            key,
            component_names,
            components,
            tags,
        })
    }

    pub fn spawn_with_defaults(
        &mut self,
        components: impl IntoIterator<Item = String>,
    ) -> Result<Entity> {
        let mut component_names = Vec::new();
        let mut tag_names = Vec::new();
        for name in components {
            if let Some(tag) = name.strip_prefix(TAG_PREFIX) {
                if tag.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "ECS tag name cannot be empty".to_string(),
                    ));
                }
                tag_names.push(tag.to_string());
            } else {
                component_names.push(name);
            }
        }
        component_names.sort();
        component_names.dedup();
        tag_names.sort();
        tag_names.dedup();
        let key = self.component_key_for_names(component_names.iter().map(String::as_str))?;
        let archetype = self.ensure_archetype(key)?;
        let tag_ids = tag_names
            .iter()
            .map(|tag| self.tag_registry.intern(tag))
            .collect::<Vec<_>>();

        let entity = self.entities.spawn();
        self.entity_tags.clear_slot(entity.index);
        let row = self.archetypes[archetype].push_default_row(entity)?;
        self.locations.insert(entity, archetype, row);
        self.entity_order.insert(entity);
        for tag in tag_ids {
            self.entity_tags.add(entity.index, tag);
        }
        self.change_journal.record(entity, ChangeKind::Spawned);
        for component in component_names {
            self.change_journal.record(
                entity,
                ChangeKind::ComponentAdded {
                    component: component.into(),
                },
            );
        }
        for tag in tag_names {
            self.change_journal
                .record(entity, ChangeKind::TagAdded { tag: tag.into() });
        }
        self.note_structural_revision();
        Ok(entity)
    }

    pub fn despawn(&mut self, entity: Entity) -> Result<()> {
        let location = self.location(entity)?;
        let component_ids = self.archetypes[location.archetype]
            .key()
            .components()
            .to_vec();
        let tags = self.entity_tags(entity)?;
        self.remove_entity_row(entity)?;
        self.entities.despawn(entity)?;
        self.entity_order.remove(&entity);
        self.entity_tags.clear_slot(entity.index);
        for component_id in component_ids {
            let component = self
                .schemas
                .component_name(component_id)
                .expect("archetype component id is registered")
                .to_string();
            self.change_journal.record(
                entity,
                ChangeKind::ComponentRemoved {
                    component: component.into(),
                },
            );
        }
        for tag in tags {
            self.change_journal
                .record(entity, ChangeKind::TagRemoved { tag: tag.into() });
        }
        self.change_journal.record(entity, ChangeKind::Despawned);
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn validate_entity(&self, entity: Entity) -> Result<()> {
        self.entities.validate(entity)?;
        self.locations.get(entity).map(|_| ())
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
        let mut names = self.archetypes[location.archetype]
            .key()
            .components()
            .iter()
            .map(|id| {
                self.schemas
                    .component_name(*id)
                    .expect("archetype component id is registered")
                    .to_string()
            })
            .collect::<Vec<_>>();
        names.sort();
        Ok(names)
    }

    pub fn entity_tags(&self, entity: Entity) -> Result<Vec<String>> {
        self.location(entity)?;
        let mut names = self
            .entity_tags
            .tags(entity.index)
            .iter()
            .map(|id| {
                self.tag_registry
                    .name(*id)
                    .expect("entity tag id is registered")
                    .to_string()
            })
            .collect::<Vec<_>>();
        names.sort();
        Ok(names)
    }

    pub fn add_component_default(
        &mut self,
        entity: Entity,
        component: impl Into<String>,
    ) -> Result<()> {
        let component: String = component.into();
        let component_id = self
            .schemas
            .component_id(&component)
            .ok_or_else(|| EcsError::UnknownSchema(component.clone()))?;
        let location = self.location(entity)?;
        if self.archetypes[location.archetype]
            .key()
            .contains(component_id)
        {
            return Err(EcsError::DuplicateComponent(component));
        }
        let new_archetype = self.add_transition(location.archetype, component_id)?;
        self.move_entity_to_archetype(entity, new_archetype)?;
        self.change_journal.record(
            entity,
            ChangeKind::ComponentAdded {
                component: component.into(),
            },
        );
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn remove_component(&mut self, entity: Entity, component: &str) -> Result<()> {
        let component_id = self
            .schemas
            .component_id(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        let location = self.location(entity)?;
        if !self.archetypes[location.archetype]
            .key()
            .contains(component_id)
        {
            return Err(EcsError::MissingComponent(component.to_string()));
        }
        let new_archetype = self.remove_transition(location.archetype, component_id)?;
        self.move_entity_to_archetype(entity, new_archetype)?;
        self.change_journal.record(
            entity,
            ChangeKind::ComponentRemoved {
                component: component.into(),
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
        self.location(entity)?;
        let tag_id = self.tag_registry.intern(tag);
        if !self.entity_tags.add(entity.index, tag_id) {
            return Ok(());
        }
        self.change_journal
            .record(entity, ChangeKind::TagAdded { tag: tag.into() });
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub fn remove_tag(&mut self, entity: Entity, tag: &str) -> Result<()> {
        self.location(entity)?;
        let Some(tag_id) = self.tag_registry.get(tag) else {
            return Ok(());
        };
        if !self.entity_tags.remove(entity.index, tag_id) {
            return Ok(());
        }
        self.change_journal
            .record(entity, ChangeKind::TagRemoved { tag: tag.into() });
        self.diagnostics.structural_commands_applied += 1;
        self.note_structural_revision();
        Ok(())
    }

    pub(super) fn component_key_for_names<'a>(
        &self,
        names: impl IntoIterator<Item = &'a str>,
    ) -> Result<ComponentSetKey> {
        names
            .into_iter()
            .map(|name| {
                self.schemas
                    .component_id(name)
                    .ok_or_else(|| EcsError::UnknownSchema(name.to_string()))
            })
            .collect::<Result<Vec<_>>>()
            .map(ComponentSetKey::new)
    }

    fn ensure_archetype(&mut self, key: ComponentSetKey) -> Result<usize> {
        if let Some(index) = self.archetype_by_key.get(&key) {
            return Ok(*index);
        }
        let index = self.archetypes.len();
        let archetype = Archetype::new(key.clone(), &self.schemas)?;
        self.archetypes.push(archetype);
        self.archetype_by_key.insert(key, index);
        self.archetype_generation = self.archetype_generation.wrapping_add(1);
        self.diagnostics.archetypes_total = self.archetypes.len();
        self.update_query_caches_for_new_archetype(index);
        Ok(index)
    }

    fn add_transition(&mut self, source: usize, component: ComponentId) -> Result<usize> {
        if let Some(target) = self.archetypes[source].transition_add(component) {
            return Ok(target);
        }
        let target_key = self.archetypes[source].key().with(component);
        let target = self.ensure_archetype(target_key)?;
        self.archetypes[source].cache_add_transition(component, target);
        self.archetypes[target].cache_remove_transition(component, source);
        Ok(target)
    }

    fn remove_transition(&mut self, source: usize, component: ComponentId) -> Result<usize> {
        if let Some(target) = self.archetypes[source].transition_remove(component) {
            return Ok(target);
        }
        let target_key = self.archetypes[source].key().without(component);
        let target = self.ensure_archetype(target_key)?;
        self.archetypes[source].cache_remove_transition(component, target);
        self.archetypes[target].cache_add_transition(component, source);
        Ok(target)
    }

    pub(super) fn location(&self, entity: Entity) -> Result<EntityLocation> {
        self.entities.validate(entity)?;
        self.locations.get(entity)
    }

    fn remove_entity_row(&mut self, entity: Entity) -> Result<()> {
        let location = self.location(entity)?;
        let removed = self.archetypes[location.archetype].remove_row_swap_remove(location.row)?;
        debug_assert_eq!(removed.entity, entity);
        self.locations.remove(entity)?;
        if let Some(swapped) = removed.swapped_entity {
            self.locations
                .insert(swapped, location.archetype, location.row);
        }
        Ok(())
    }

    fn move_entity_to_archetype(&mut self, entity: Entity, new_archetype: usize) -> Result<()> {
        let location = self.location(entity)?;
        if location.archetype == new_archetype {
            return Ok(());
        }
        let new_row = self.archetypes[new_archetype].len();
        let removed = if location.archetype < new_archetype {
            let (left, right) = self.archetypes.split_at_mut(new_archetype);
            left[location.archetype].move_row_to(location.row, &mut right[0], entity)?
        } else {
            let (left, right) = self.archetypes.split_at_mut(location.archetype);
            right[0].move_row_to(location.row, &mut left[new_archetype], entity)?
        };
        if let Some(swapped) = removed.swapped_entity {
            self.locations
                .insert(swapped, location.archetype, location.row);
        }
        self.locations.insert(entity, new_archetype, new_row);
        self.diagnostics.archetype_moves += 1;
        Ok(())
    }
}
