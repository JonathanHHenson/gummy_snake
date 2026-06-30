use crate::entity::Entity;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Command {
    Spawn { components: Vec<String> },
    Despawn { entity: Entity },
    AddComponent { entity: Entity, component: String },
    RemoveComponent { entity: Entity, component: String },
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct CommandBuffer {
    commands: Vec<Command>,
}

impl CommandBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, command: Command) {
        self.commands.push(command);
    }

    pub fn drain(&mut self) -> impl Iterator<Item = Command> + '_ {
        self.commands.drain(..)
    }

    pub fn len(&self) -> usize {
        self.commands.len()
    }

    pub fn is_empty(&self) -> bool {
        self.commands.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_buffer_drains_in_stable_order() {
        let mut buffer = CommandBuffer::new();
        buffer.push(Command::Spawn {
            components: vec!["Position".to_string()],
        });
        buffer.push(Command::Spawn {
            components: vec!["Velocity".to_string()],
        });
        let commands: Vec<_> = buffer.drain().collect();
        assert_eq!(commands.len(), 2);
        assert!(buffer.is_empty());
    }
}
