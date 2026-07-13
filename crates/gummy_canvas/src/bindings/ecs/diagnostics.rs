use gummy_ecs::World;
use pyo3::prelude::*;
use pyo3::types::PyDict;

pub(super) fn diagnostics_to_dict<'py>(
    py: Python<'py>,
    world: &World,
) -> PyResult<Bound<'py, PyDict>> {
    let diagnostics = world.diagnostics();
    let dict = PyDict::new_bound(py);
    dict.set_item("entities_alive", diagnostics.entities_alive)?;
    dict.set_item(
        "entity_generation_reuses",
        diagnostics.entity_generation_reuses,
    )?;
    dict.set_item(
        "component_schemas_total",
        diagnostics.component_schemas_total,
    )?;
    dict.set_item("archetypes_total", diagnostics.archetypes_total)?;
    dict.set_item("archetype_moves", diagnostics.archetype_moves)?;
    dict.set_item(
        "structural_commands_applied",
        diagnostics.structural_commands_applied,
    )?;
    dict.set_item(
        "staged_commands_applied",
        diagnostics.staged_commands_applied,
    )?;
    dict.set_item("query_cache_hits", diagnostics.query_cache_hits)?;
    dict.set_item("query_cache_misses", diagnostics.query_cache_misses)?;
    dict.set_item("query_cache_refreshes", diagnostics.query_cache_refreshes)?;
    dict.set_item(
        "query_cache_invalidations",
        diagnostics.query_cache_invalidations,
    )?;
    dict.set_item(
        "query_matched_archetypes",
        diagnostics.query_matched_archetypes,
    )?;
    dict.set_item("query_matched_rows", diagnostics.query_matched_rows)?;
    dict.set_item("change_journal_updates", diagnostics.change_journal_updates)?;
    dict.set_item(
        "change_journal_retained_records",
        diagnostics.change_journal_retained_records,
    )?;
    dict.set_item(
        "change_filter_matched_rows",
        diagnostics.change_filter_matched_rows,
    )?;
    dict.set_item("resources_total", diagnostics.resources_total)?;
    dict.set_item("event_queues_total", diagnostics.event_queues_total)?;
    dict.set_item("event_records_total", diagnostics.event_records_total)?;
    dict.set_item("events_emitted", diagnostics.events_emitted)?;
    dict.set_item("event_read_calls", diagnostics.event_read_calls)?;
    dict.set_item("event_records_read", diagnostics.event_records_read)?;
    dict.set_item("event_clear_calls", diagnostics.event_clear_calls)?;
    dict.set_item("event_records_cleared", diagnostics.event_records_cleared)?;
    dict.set_item("event_records_pruned", diagnostics.event_records_pruned)?;
    dict.set_item(
        "diagnostic_messages_deduplicated",
        diagnostics.diagnostic_messages_deduplicated,
    )?;
    dict.set_item(
        "diagnostic_messages_dropped",
        diagnostics.diagnostic_messages_dropped,
    )?;
    dict.set_item("messages", diagnostics.messages)?;
    Ok(dict)
}
