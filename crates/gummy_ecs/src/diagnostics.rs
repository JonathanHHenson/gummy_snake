#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Diagnostics {
    pub entities_alive: usize,
    pub entity_generation_reuses: usize,
    pub component_schemas_total: usize,
    pub archetypes_total: usize,
    pub archetype_moves: usize,
    pub structural_commands_applied: usize,
    pub staged_commands_applied: usize,
    pub query_cache_hits: usize,
    pub query_cache_misses: usize,
    pub query_cache_refreshes: usize,
    pub query_cache_invalidations: usize,
    pub query_matched_archetypes: usize,
    pub query_matched_rows: usize,
    pub resources_total: usize,
    pub event_queues_total: usize,
}
