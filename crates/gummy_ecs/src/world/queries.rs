use crate::archetype::ComponentSetKey;
use crate::entity::Entity;
use crate::error::Result;
use crate::query::{CachedQuery, QueryFilter, QuerySnapshot};

use super::World;

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
        let archetypes = self.matching_archetypes_for_filter(filter);
        let mut entities = Vec::new();
        for archetype_index in archetypes {
            entities.extend_from_slice(self.archetypes[archetype_index].entities());
        }
        entities.sort_by_key(|entity| entity.raw());
        self.diagnostics.query_matched_rows += entities.len();
        Ok(entities)
    }

    pub fn snapshot_query_filter(&mut self, filter: QueryFilter) -> Result<QuerySnapshot> {
        self.query_filter(filter).map(QuerySnapshot::new)
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
