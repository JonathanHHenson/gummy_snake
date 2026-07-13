use crate::archetype::ComponentSetKey;
use crate::entity::Entity;

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

    pub fn required_components(&self) -> ComponentSetKey {
        ComponentSetKey::new(self.terms.iter().filter_map(|term| match term {
            QueryTerm::WithComponent(component) => Some(component.clone()),
            _ => None,
        }))
    }

    pub fn matches_key(&self, key: &ComponentSetKey) -> bool {
        self.terms.iter().all(|term| match term {
            QueryTerm::WithComponent(component) => key.contains_component(component),
            QueryTerm::WithoutComponent(component) => !key.contains_component(component),
            QueryTerm::WithTag(tag) => key.contains_tag(tag),
            QueryTerm::WithoutTag(tag) => !key.contains_tag(tag),
            // Change terms are evaluated per row against the world's current
            // change journal after archetype selection.
            QueryTerm::Added(_) | QueryTerm::Changed(_) | QueryTerm::Removed(_) => true,
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
    fn query_filter_matches_components_and_tags() {
        let key = ComponentSetKey::new(["Position", "#tag:Hero"]);
        let filter = QueryFilter::new([
            QueryTerm::WithComponent("Position".to_string()),
            QueryTerm::WithTag("Hero".to_string()),
            QueryTerm::WithoutComponent("Velocity".to_string()),
            QueryTerm::WithoutTag("Enemy".to_string()),
        ]);
        assert!(filter.matches_key(&key));
        assert!(!QueryFilter::new([QueryTerm::WithoutTag("Hero".to_string())]).matches_key(&key));
    }

    #[test]
    fn query_snapshot_sorts_and_deduplicates_entities() {
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
