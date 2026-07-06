use crate::command::Command;
use crate::entity::Entity;
use crate::error::Result;

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
}
