use std::collections::HashMap;
use std::hash::{Hash, Hasher};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum SpatialAlgorithmKind {
    HashGrid,
    Quadtree,
    Octree,
    HilbertCurve,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SpatialIndexDescriptor {
    pub name: Option<String>,
    pub target_query: Vec<String>,
    pub dimensions: u8,
    pub algorithm: SpatialAlgorithmKind,
    pub update_policy: String,
}

impl SpatialIndexDescriptor {
    pub fn fingerprint(&self) -> u64 {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        self.target_query.hash(&mut hasher);
        self.dimensions.hash(&mut hasher);
        self.algorithm.hash(&mut hasher);
        self.update_policy.hash(&mut hasher);
        hasher.finish()
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SpatialIndexStats {
    pub builds: u64,
    pub queries: u64,
    pub candidate_rows: u64,
    pub exact_rows: u64,
    pub stale: bool,
    pub stale_reason: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpatialIndexSlot {
    pub descriptor: SpatialIndexDescriptor,
    pub stats: SpatialIndexStats,
    pub ref_count: usize,
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct SpatialIndexRegistry {
    slots: HashMap<u64, SpatialIndexSlot>,
}

impl SpatialIndexRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn intern(&mut self, descriptor: SpatialIndexDescriptor) -> u64 {
        let id = descriptor.fingerprint();
        self.slots
            .entry(id)
            .and_modify(|slot| slot.ref_count += 1)
            .or_insert(SpatialIndexSlot {
                descriptor,
                stats: SpatialIndexStats::default(),
                ref_count: 1,
            });
        id
    }

    pub fn mark_stale(&mut self, reason: impl Into<String>) {
        let reason = reason.into();
        for slot in self.slots.values_mut() {
            slot.stats.stale = true;
            slot.stats.stale_reason = Some(reason.clone());
        }
    }

    pub fn release(&mut self, id: u64) {
        let remove = if let Some(slot) = self.slots.get_mut(&id) {
            slot.ref_count = slot.ref_count.saturating_sub(1);
            slot.ref_count == 0
        } else {
            false
        };
        if remove {
            self.slots.remove(&id);
        }
    }

    pub fn len(&self) -> usize {
        self.slots.len()
    }

    pub fn get(&self, id: u64) -> Option<&SpatialIndexSlot> {
        self.slots.get(&id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_interns_equivalent_descriptors_without_name() {
        let mut registry = SpatialIndexRegistry::new();
        let first = SpatialIndexDescriptor {
            name: Some("a".to_string()),
            target_query: vec!["Position".to_string()],
            dimensions: 2,
            algorithm: SpatialAlgorithmKind::HashGrid,
            update_policy: "auto".to_string(),
        };
        let second = SpatialIndexDescriptor {
            name: Some("b".to_string()),
            ..first.clone()
        };
        let a = registry.intern(first);
        let b = registry.intern(second);
        assert_eq!(a, b);
        assert_eq!(registry.len(), 1);
        assert_eq!(registry.get(a).unwrap().ref_count, 2);
        registry.mark_stale("position write");
        assert!(registry.get(a).unwrap().stats.stale);
    }
}
