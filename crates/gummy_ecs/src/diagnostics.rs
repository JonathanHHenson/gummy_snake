pub const DIAGNOSTIC_MESSAGE_LIMIT: usize = 64;

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
    pub event_records_total: usize,
    pub events_emitted: usize,
    pub event_read_calls: usize,
    pub event_records_read: usize,
    pub event_clear_calls: usize,
    pub event_records_cleared: usize,
    pub event_records_pruned: usize,
    pub diagnostic_messages_deduplicated: usize,
    pub diagnostic_messages_dropped: usize,
    pub messages: Vec<String>,
}

impl Diagnostics {
    pub fn record_message(&mut self, message: impl Into<String>) {
        let message = message.into();
        if self.messages.contains(&message) {
            self.diagnostic_messages_deduplicated += 1;
            return;
        }
        if self.messages.len() == DIAGNOSTIC_MESSAGE_LIMIT {
            self.messages.remove(0);
            self.diagnostic_messages_dropped += 1;
        }
        self.messages.push(message);
    }
}
