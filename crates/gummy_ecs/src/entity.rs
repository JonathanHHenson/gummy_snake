use std::cmp::Ordering;

use crate::error::{EcsError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Entity {
    pub index: u32,
    pub generation: u32,
}

impl Entity {
    pub fn raw(self) -> u64 {
        ((self.generation as u64) << 32) | self.index as u64
    }
}

impl PartialOrd for Entity {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Entity {
    fn cmp(&self, other: &Self) -> Ordering {
        self.raw().cmp(&other.raw())
    }
}

#[derive(Debug, Default, Clone)]
pub struct EntityAllocator {
    generations: Vec<u32>,
    alive: Vec<bool>,
    free: Vec<u32>,
    alive_count: usize,
    generation_reuses: usize,
}

impl EntityAllocator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn spawn(&mut self) -> Entity {
        if let Some(index) = self.free.pop() {
            let slot = index as usize;
            self.alive[slot] = true;
            self.alive_count += 1;
            return Entity {
                index,
                generation: self.generations[slot],
            };
        }

        let index = self.generations.len() as u32;
        self.generations.push(0);
        self.alive.push(true);
        self.alive_count += 1;
        Entity {
            index,
            generation: 0,
        }
    }

    pub fn despawn(&mut self, entity: Entity) -> Result<()> {
        self.validate(entity)?;
        let slot = entity.index as usize;
        self.alive[slot] = false;
        self.generations[slot] = self.generations[slot].wrapping_add(1);
        self.free.push(entity.index);
        self.alive_count -= 1;
        self.generation_reuses += 1;
        Ok(())
    }

    pub fn validate(&self, entity: Entity) -> Result<()> {
        let slot = entity.index as usize;
        if slot >= self.generations.len()
            || !self.alive[slot]
            || self.generations[slot] != entity.generation
        {
            return Err(EcsError::StaleEntity {
                index: entity.index,
                generation: entity.generation,
            });
        }
        Ok(())
    }

    pub fn alive_count(&self) -> usize {
        self.alive_count
    }

    pub fn generation_reuses(&self) -> usize {
        self.generation_reuses
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stale_handles_are_rejected_after_reuse() {
        let mut allocator = EntityAllocator::new();
        let old = allocator.spawn();
        allocator.despawn(old).unwrap();
        let new = allocator.spawn();

        assert_eq!(new.index, old.index);
        assert_ne!(new.generation, old.generation);
        assert!(allocator.validate(old).is_err());
        assert!(allocator.validate(new).is_ok());
    }
}
