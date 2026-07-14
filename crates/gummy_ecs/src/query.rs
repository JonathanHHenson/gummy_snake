use crate::archetype::ComponentSetKey;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::schema::SchemaRegistry;
use crate::tag::{TagId, TagRegistry};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum QueryTerm {
    WithComponent(String),
    WithoutComponent(String),
    WithTag(String),
    WithoutTag(String),
    /// Matches rows whose component was added during the current change epoch.
    Added(String),
    /// Matches rows whose component had at least one field changed during the current change epoch.
    Changed(String),
    /// Matches rows whose component was removed during the current change epoch.
    Removed(String),
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash)]
pub struct QueryFilter {
    pub terms: Vec<QueryTerm>,
}

impl QueryFilter {
    pub fn new(terms: impl IntoIterator<Item = QueryTerm>) -> Self {
        let mut terms = terms.into_iter().collect::<Vec<_>>();
        terms.sort();
        terms.dedup();
        Self { terms }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash)]
pub(crate) struct ArchetypeFilterKey {
    pub required: ComponentSetKey,
    pub excluded: ComponentSetKey,
}

impl ArchetypeFilterKey {
    pub fn matches(&self, key: &ComponentSetKey) -> bool {
        key.is_superset_of(&self.required) && key.is_disjoint_from(&self.excluded)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CompiledQueryFilter {
    pub archetypes: ArchetypeFilterKey,
    pub required_tags: Vec<TagId>,
    pub excluded_tags: Vec<TagId>,
}

impl CompiledQueryFilter {
    pub fn compile(
        filter: &QueryFilter,
        schemas: &SchemaRegistry,
        tags: &mut TagRegistry,
    ) -> Result<Self> {
        let mut required = Vec::new();
        let mut excluded = Vec::new();
        let mut required_tags = Vec::new();
        let mut excluded_tags = Vec::new();
        for term in &filter.terms {
            match term {
                QueryTerm::WithComponent(component) => required.push(
                    schemas
                        .component_id(component)
                        .ok_or_else(|| EcsError::UnknownSchema(component.clone()))?,
                ),
                QueryTerm::WithoutComponent(component) => excluded.push(
                    schemas
                        .component_id(component)
                        .ok_or_else(|| EcsError::UnknownSchema(component.clone()))?,
                ),
                QueryTerm::WithTag(tag) => required_tags.push(tags.intern(tag)),
                QueryTerm::WithoutTag(tag) => excluded_tags.push(tags.intern(tag)),
                QueryTerm::Added(component)
                | QueryTerm::Changed(component)
                | QueryTerm::Removed(component) => {
                    if !schemas.contains(component) {
                        return Err(EcsError::UnknownSchema(component.clone()));
                    }
                }
            }
        }
        required_tags.sort_unstable();
        required_tags.dedup();
        excluded_tags.sort_unstable();
        excluded_tags.dedup();
        Ok(Self {
            archetypes: ArchetypeFilterKey {
                required: ComponentSetKey::new(required),
                excluded: ComponentSetKey::new(excluded),
            },
            required_tags,
            excluded_tags,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CachedQuery {
    pub generation_seen: u64,
    pub matched_archetypes: Vec<usize>,
}

impl CachedQuery {
    pub fn new(generation_seen: u64, mut matched_archetypes: Vec<usize>) -> Self {
        matched_archetypes.sort_unstable();
        matched_archetypes.dedup();
        Self {
            generation_seen,
            matched_archetypes,
        }
    }

    pub(crate) fn consider_archetype(&mut self, generation: u64, index: usize, matches: bool) {
        self.generation_seen = generation;
        if matches && self.matched_archetypes.last().copied() != Some(index) {
            self.matched_archetypes.push(index);
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueryCardinality {
    Zero,
    One(Entity),
    Multiple,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuerySnapshot {
    pub entities: Vec<Entity>,
}

impl QuerySnapshot {
    pub fn new(mut entities: Vec<Entity>) -> Self {
        entities.sort_by_key(|entity| entity.raw());
        entities.dedup_by_key(|entity| entity.raw());
        Self { entities }
    }

    pub(crate) fn from_ordered(entities: Vec<Entity>) -> Self {
        debug_assert!(entities
            .windows(2)
            .all(|pair| pair[0].raw() < pair[1].raw()));
        Self { entities }
    }

    pub fn len(&self) -> usize {
        self.entities.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entities.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn query_snapshot_sorts_and_deduplicates_external_entities() {
        let snapshot = QuerySnapshot::new(vec![
            Entity {
                index: 2,
                generation: 0,
            },
            Entity {
                index: 1,
                generation: 0,
            },
            Entity {
                index: 2,
                generation: 0,
            },
        ]);
        assert_eq!(
            snapshot
                .entities
                .iter()
                .map(|entity| entity.index)
                .collect::<Vec<_>>(),
            vec![1, 2]
        );
    }
}
