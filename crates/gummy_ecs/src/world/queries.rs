use crate::archetype::ComponentSetKey;
use crate::entity::Entity;
use crate::error::Result;
use crate::query::{CachedQuery, QueryFilter, QuerySnapshot};

use super::{ComponentChange, World};

impl World {
    pub fn query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<Vec<Entity>> {
        let required = ComponentSetKey::new(required_components);
        self.validate_component_set(&required)?;
        let archetypes = self.matching_archetypes(required);
        let mut entities = Vec::new();
        for archetype_index in archetypes {
            entities.extend_from_slice(self.archetypes[archetype_index].entities());
        }
        entities.sort_by_key(|entity| entity.raw());
        self.diagnostics.query_matched_rows += entities.len();
        Ok(entities)
    }

    pub fn snapshot_query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<QuerySnapshot> {
        self.query(required_components).map(QuerySnapshot::new)
    }

    pub fn query_filter(&mut self, filter: QueryFilter) -> Result<Vec<Entity>> {
        let required = filter.required_components();
        self.validate_component_set(&required)?;
        self.validate_change_terms(&filter)?;
        let has_change_terms = filter.terms.iter().any(|term| {
            matches!(
                term,
                crate::query::QueryTerm::Added(_)
                    | crate::query::QueryTerm::Changed(_)
                    | crate::query::QueryTerm::Removed(_)
            )
        });
        let archetypes = self.matching_archetypes_for_filter(filter.clone());
        let mut entities = Vec::new();
        for archetype_index in archetypes {
            entities.extend_from_slice(self.archetypes[archetype_index].entities());
        }
        entities.retain(|entity| self.matches_current_change_terms(&filter, *entity));
        entities.sort_by_key(|entity| entity.raw());
        self.diagnostics.query_matched_rows += entities.len();
        if has_change_terms {
            self.diagnostics.change_filter_matched_rows += entities.len();
        }
        Ok(entities)
    }

    pub fn snapshot_query_filter(&mut self, filter: QueryFilter) -> Result<QuerySnapshot> {
        self.query_filter(filter).map(QuerySnapshot::new)
    }

    fn validate_change_terms(&self, filter: &QueryFilter) -> Result<()> {
        for term in &filter.terms {
            let component = match term {
                crate::query::QueryTerm::Added(component)
                | crate::query::QueryTerm::Changed(component)
                | crate::query::QueryTerm::Removed(component) => component,
                _ => continue,
            };
            if !self.schemas.contains(component) {
                return Err(crate::error::EcsError::UnknownSchema(component.clone()));
            }
        }
        Ok(())
    }

    fn matches_current_change_terms(&self, filter: &QueryFilter, entity: Entity) -> bool {
        let epoch = self.change_journal.current_epoch();
        let change = self.change_journal.entity_change(epoch, entity);
        filter.terms.iter().all(|term| match term {
            crate::query::QueryTerm::Added(component) => change
                .and_then(|change| change.components.get(component))
                .is_some_and(ComponentChange::is_currently_added),
            crate::query::QueryTerm::Changed(component) => change
                .and_then(|change| change.components.get(component))
                .is_some_and(ComponentChange::is_currently_changed),
            crate::query::QueryTerm::Removed(component) => change
                .and_then(|change| change.components.get(component))
                .is_some_and(ComponentChange::is_currently_removed),
            _ => true,
        })
    }

    fn matching_archetypes(&mut self, required: ComponentSetKey) -> Vec<usize> {
        if let Some(cached) = self.query_cache.get(&required) {
            if cached.generation_seen == self.archetype_generation {
                self.diagnostics.query_cache_hits += 1;
                self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
                return cached.matched_archetypes.clone();
            }
            self.diagnostics.query_cache_refreshes += 1;
        } else {
            self.diagnostics.query_cache_misses += 1;
        }
        let matches = self
            .archetypes
            .iter()
            .enumerate()
            .filter_map(|(index, archetype)| {
                archetype.key().is_superset_of(&required).then_some(index)
            })
            .collect::<Vec<_>>();
        self.diagnostics.query_matched_archetypes += matches.len();
        self.query_cache.insert(
            required,
            CachedQuery::new(self.archetype_generation, matches.clone()),
        );
        matches
    }

    fn matching_archetypes_for_filter(&mut self, filter: QueryFilter) -> Vec<usize> {
        if let Some(cached) = self.filtered_query_cache.get(&filter) {
            if cached.generation_seen == self.archetype_generation {
                self.diagnostics.query_cache_hits += 1;
                self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
                return cached.matched_archetypes.clone();
            }
            self.diagnostics.query_cache_refreshes += 1;
        } else {
            self.diagnostics.query_cache_misses += 1;
        }
        let matches = self
            .archetypes
            .iter()
            .enumerate()
            .filter_map(|(index, archetype)| filter.matches_key(archetype.key()).then_some(index))
            .collect::<Vec<_>>();
        self.diagnostics.query_matched_archetypes += matches.len();
        self.filtered_query_cache.insert(
            filter,
            CachedQuery::new(self.archetype_generation, matches.clone()),
        );
        matches
    }

    pub(super) fn invalidate_query_cache(&mut self) {
        if !self.query_cache.is_empty() || !self.filtered_query_cache.is_empty() {
            self.diagnostics.query_cache_invalidations += 1;
        }
        self.query_cache.clear();
        self.filtered_query_cache.clear();
    }
}
