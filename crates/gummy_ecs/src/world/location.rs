use crate::entity::Entity;
use crate::error::{EcsError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) struct EntityLocation {
    pub archetype: usize,
    pub row: usize,
    generation: u32,
}

#[derive(Debug, Clone, Default)]
pub(super) struct DenseEntityLocations {
    slots: Vec<Option<EntityLocation>>,
}

impl DenseEntityLocations {
    pub fn insert(&mut self, entity: Entity, archetype: usize, row: usize) {
        let index = entity.index as usize;
        if self.slots.len() <= index {
            self.slots.resize(index + 1, None);
        }
        self.slots[index] = Some(EntityLocation {
            archetype,
            row,
            generation: entity.generation,
        });
    }

    pub fn get(&self, entity: Entity) -> Result<EntityLocation> {
        self.slots
            .get(entity.index as usize)
            .and_then(|slot| *slot)
            .filter(|location| location.generation == entity.generation)
            .ok_or(EcsError::StaleEntity {
                index: entity.index,
                generation: entity.generation,
            })
    }

    pub fn remove(&mut self, entity: Entity) -> Result<EntityLocation> {
        let location = self.get(entity)?;
        self.slots[entity.index as usize] = None;
        Ok(location)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sparse_indices_and_generations_are_checked() {
        let mut locations = DenseEntityLocations::default();
        let current = Entity {
            index: 10_000,
            generation: 7,
        };
        locations.insert(current, 3, 9);
        assert_eq!(locations.get(current).unwrap().row, 9);
        assert!(locations
            .get(Entity {
                index: 10_000,
                generation: 6,
            })
            .is_err());
        assert!(locations
            .get(Entity {
                index: 9_999,
                generation: 7,
            })
            .is_err());
    }
}
