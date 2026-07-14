use std::sync::Arc;

use crate::archetype::ComponentSetKey;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::query::{
    ArchetypeFilterKey, CachedQuery, CompiledQueryFilter, QueryCardinality, QueryFilter,
    QuerySnapshot, QueryTerm,
};

use super::{CachedExecutionQuery, ComponentChange, World};

impl World {
    pub fn query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<Vec<Entity>> {
        self.query_limit(required_components, None)
    }

    pub fn query_limit(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
        limit: Option<usize>,
    ) -> Result<Vec<Entity>> {
        let required = required_components
            .into_iter()
            .map(|component| {
                self.schemas
                    .component_id(&component)
                    .ok_or(EcsError::UnknownSchema(component))
            })
            .collect::<Result<Vec<_>>>()?;
        let required = ComponentSetKey::new(required);
        let archetypes = self.matching_archetypes(required);
        let entities = self.collect_ordered_matches(&archetypes, limit, |_, _| true)?;
        self.diagnostics.query_matched_rows += entities.len();
        Ok(entities)
    }

    pub fn snapshot_query(
        &mut self,
        required_components: impl IntoIterator<Item = String>,
    ) -> Result<QuerySnapshot> {
        self.query(required_components)
            .map(QuerySnapshot::from_ordered)
    }

    pub fn query_filter(&mut self, filter: QueryFilter) -> Result<Vec<Entity>> {
        self.query_filter_limit(filter, None)
    }

    pub fn query_filter_limit(
        &mut self,
        filter: QueryFilter,
        limit: Option<usize>,
    ) -> Result<Vec<Entity>> {
        let compiled = self.compile_query_filter(&filter)?;
        let has_change_terms = filter.terms.iter().any(|term| {
            matches!(
                term,
                QueryTerm::Added(_) | QueryTerm::Changed(_) | QueryTerm::Removed(_)
            )
        });
        let archetypes = self.matching_archetypes_for_filter(compiled.archetypes.clone());
        let required_tags = compiled.required_tags;
        let excluded_tags = compiled.excluded_tags;
        let entities = self.collect_ordered_matches(&archetypes, limit, |world, entity| {
            required_tags
                .iter()
                .all(|tag| world.entity_tags.contains(entity.index, *tag))
                && excluded_tags
                    .iter()
                    .all(|tag| !world.entity_tags.contains(entity.index, *tag))
                && world.matches_current_change_terms(&filter, entity)
        })?;
        self.diagnostics.query_matched_rows += entities.len();
        if has_change_terms {
            self.diagnostics.change_filter_matched_rows += entities.len();
        }
        Ok(entities)
    }

    pub(crate) fn execution_query(
        &mut self,
        filter: &QueryFilter,
    ) -> Result<(Arc<Vec<Entity>>, Arc<Vec<(usize, usize)>>)> {
        let cacheable = !filter.terms.iter().any(|term| {
            matches!(
                term,
                QueryTerm::Added(_) | QueryTerm::Changed(_) | QueryTerm::Removed(_)
            )
        });
        if cacheable {
            if let Some(cached) = self.execution_query_cache.get(filter) {
                if cached.structural_revision == self.structural_revision {
                    self.diagnostics.query_matched_rows += cached.rows.len();
                    return Ok((Arc::clone(&cached.rows), Arc::clone(&cached.locations)));
                }
            }
        }

        let rows = Arc::new(self.query_filter(filter.clone())?);
        let locations = Arc::new(self.locations_for_entities(rows.iter().copied())?);
        if cacheable {
            self.execution_query_cache.insert(
                filter.clone(),
                CachedExecutionQuery {
                    structural_revision: self.structural_revision,
                    rows: Arc::clone(&rows),
                    locations: Arc::clone(&locations),
                },
            );
        }
        Ok((rows, locations))
    }

    pub fn query_cardinality(&mut self, filter: QueryFilter) -> Result<QueryCardinality> {
        let rows = self.query_filter_limit(filter, Some(2))?;
        Ok(match rows.as_slice() {
            [] => QueryCardinality::Zero,
            [entity] => QueryCardinality::One(*entity),
            _ => QueryCardinality::Multiple,
        })
    }

    pub fn snapshot_query_filter(&mut self, filter: QueryFilter) -> Result<QuerySnapshot> {
        self.query_filter(filter).map(QuerySnapshot::from_ordered)
    }

    fn compile_query_filter(&mut self, filter: &QueryFilter) -> Result<CompiledQueryFilter> {
        if let Some(compiled) = self.compiled_query_cache.get(filter) {
            return Ok(compiled.clone());
        }
        let compiled = CompiledQueryFilter::compile(filter, &self.schemas, &mut self.tag_registry)?;
        self.compiled_query_cache
            .insert(filter.clone(), compiled.clone());
        Ok(compiled)
    }

    fn matches_current_change_terms(&self, filter: &QueryFilter, entity: Entity) -> bool {
        let epoch = self.change_journal.current_epoch();
        let change = self.change_journal.entity_change(epoch, entity);
        filter.terms.iter().all(|term| match term {
            QueryTerm::Added(component) => change
                .and_then(|change| change.components.get(component.as_str()))
                .is_some_and(ComponentChange::is_currently_added),
            QueryTerm::Changed(component) => change
                .and_then(|change| change.components.get(component.as_str()))
                .is_some_and(ComponentChange::is_currently_changed),
            QueryTerm::Removed(component) => change
                .and_then(|change| change.components.get(component.as_str()))
                .is_some_and(ComponentChange::is_currently_removed),
            _ => true,
        })
    }

    fn collect_ordered_matches(
        &self,
        archetypes: &[usize],
        limit: Option<usize>,
        mut row_matches: impl FnMut(&Self, Entity) -> bool,
    ) -> Result<Vec<Entity>> {
        if limit == Some(0) {
            return Ok(Vec::new());
        }
        let mut matched_archetypes = vec![false; self.archetypes.len()];
        for archetype in archetypes {
            matched_archetypes[*archetype] = true;
        }
        let mut entities = Vec::new();
        for entity in &self.entity_order {
            let location = self.locations.get(*entity)?;
            if matched_archetypes[location.archetype] && row_matches(self, *entity) {
                entities.push(*entity);
                if limit.is_some_and(|limit| entities.len() == limit) {
                    break;
                }
            }
        }
        Ok(entities)
    }

    fn matching_archetypes(&mut self, required: ComponentSetKey) -> Vec<usize> {
        if let Some(cached) = self.query_cache.get(&required) {
            self.diagnostics.query_cache_hits += 1;
            self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
            return cached.matched_archetypes.clone();
        }
        self.diagnostics.query_cache_misses += 1;
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

    fn matching_archetypes_for_filter(&mut self, filter: ArchetypeFilterKey) -> Vec<usize> {
        if let Some(cached) = self.filtered_query_cache.get(&filter) {
            self.diagnostics.query_cache_hits += 1;
            self.diagnostics.query_matched_archetypes += cached.matched_archetypes.len();
            return cached.matched_archetypes.clone();
        }
        self.diagnostics.query_cache_misses += 1;
        let matches = self
            .archetypes
            .iter()
            .enumerate()
            .filter_map(|(index, archetype)| filter.matches(archetype.key()).then_some(index))
            .collect::<Vec<_>>();
        self.diagnostics.query_matched_archetypes += matches.len();
        self.filtered_query_cache.insert(
            filter,
            CachedQuery::new(self.archetype_generation, matches.clone()),
        );
        matches
    }

    pub(super) fn update_query_caches_for_new_archetype(&mut self, index: usize) {
        let key = self.archetypes[index].key();
        for (required, cached) in &mut self.query_cache {
            cached.consider_archetype(
                self.archetype_generation,
                index,
                key.is_superset_of(required),
            );
        }
        for (filter, cached) in &mut self.filtered_query_cache {
            cached.consider_archetype(self.archetype_generation, index, filter.matches(key));
        }
        if !self.query_cache.is_empty() || !self.filtered_query_cache.is_empty() {
            self.diagnostics.query_cache_refreshes += 1;
        }
    }
}
