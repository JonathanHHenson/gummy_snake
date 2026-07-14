use std::collections::{hash_map::Entry, HashMap, HashSet};

use crate::command::Command;
use crate::entity::Entity;
use crate::error::{EcsError, Result};

use super::World;

impl World {
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
        self.validate_staged_barrier()?;
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

    fn validate_staged_barrier(&self) -> Result<()> {
        let mut component_states: HashMap<Entity, Option<HashSet<String>>> = HashMap::new();
        for command in self.staged.as_slice() {
            match command {
                Command::Spawn { components } => self.validate_staged_spawn(components)?,
                Command::Despawn { entity } => {
                    let state = self.staged_component_state(&mut component_states, *entity)?;
                    if state.take().is_none() {
                        return Err(EcsError::StaleEntity {
                            index: entity.index,
                            generation: entity.generation,
                        });
                    }
                }
                Command::AddComponent { entity, component } => {
                    if self.schemas.get(component).is_none() {
                        return Err(EcsError::UnknownSchema(component.clone()));
                    }
                    let state = self.staged_component_state(&mut component_states, *entity)?;
                    let components = state.as_mut().ok_or(EcsError::StaleEntity {
                        index: entity.index,
                        generation: entity.generation,
                    })?;
                    if !components.insert(component.clone()) {
                        return Err(EcsError::DuplicateComponent(component.clone()));
                    }
                }
                Command::RemoveComponent { entity, component } => {
                    if self.schemas.get(component).is_none() {
                        return Err(EcsError::UnknownSchema(component.clone()));
                    }
                    let state = self.staged_component_state(&mut component_states, *entity)?;
                    let components = state.as_mut().ok_or(EcsError::StaleEntity {
                        index: entity.index,
                        generation: entity.generation,
                    })?;
                    if !components.remove(component) {
                        return Err(EcsError::MissingComponent(component.clone()));
                    }
                }
            }
        }
        Ok(())
    }

    fn staged_component_state<'a>(
        &self,
        states: &'a mut HashMap<Entity, Option<HashSet<String>>>,
        entity: Entity,
    ) -> Result<&'a mut Option<HashSet<String>>> {
        if let Entry::Vacant(entry) = states.entry(entity) {
            let components = self.entity_components(entity)?.into_iter().collect();
            entry.insert(Some(components));
        }
        Ok(states
            .get_mut(&entity)
            .expect("staged component state was inserted"))
    }

    fn validate_staged_spawn(&self, components: &[String]) -> Result<()> {
        let mut component_names = Vec::new();
        for name in components {
            if let Some(tag) = name.strip_prefix("#tag:") {
                if tag.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "ECS tag name cannot be empty".to_string(),
                    ));
                }
            } else {
                component_names.push(name.as_str());
            }
        }
        self.component_key_for_names(component_names)?;
        Ok(())
    }
}
