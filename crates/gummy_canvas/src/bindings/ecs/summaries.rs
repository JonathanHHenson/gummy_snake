use gummy_ecs::{AccessKey, ExecutionReport, ExecutionWrite, PhysicalPlan};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use super::values::ecs_value_to_py;

fn access_key_name(key: &AccessKey) -> String {
    match key {
        AccessKey::Component(name) => format!("component:{name}"),
        AccessKey::Resource(name) => format!("resource:{name}"),
        AccessKey::Event(name) => format!("event:{name}"),
        AccessKey::Hidden(name) => format!("hidden:{name}"),
    }
}

pub(super) fn physical_plan_summary_to_dict<'py>(
    py: Python<'py>,
    plan: &PhysicalPlan,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("version", plan.version)?;
    dict.set_item("schema_fingerprint", plan.schema_fingerprint)?;
    dict.set_item("query_count", plan.queries.len())?;
    dict.set_item("expression_count", plan.expressions.len())?;
    dict.set_item("action_count", plan.actions.len())?;
    dict.set_item("root_action", plan.root_action)?;
    let access = PyDict::new_bound(py);
    access.set_item(
        "reads",
        plan.access
            .reads
            .iter()
            .map(access_key_name)
            .collect::<Vec<_>>(),
    )?;
    access.set_item(
        "writes",
        plan.access
            .writes
            .iter()
            .map(access_key_name)
            .collect::<Vec<_>>(),
    )?;
    access.set_item("structural", plan.access.structural)?;
    dict.set_item("access", access)?;
    Ok(dict)
}

pub(super) fn execution_report_to_dict<'py>(
    py: Python<'py>,
    report: &ExecutionReport,
    include_writes: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("rows_scanned", report.rows_scanned)?;
    dict.set_item("fields_written", report.fields_written)?;
    dict.set_item("resource_fields_written", report.resource_fields_written)?;
    dict.set_item("events_emitted", report.events_emitted)?;
    dict.set_item("structural_commands", report.structural_commands)?;
    dict.set_item("duplicate_writes", report.duplicate_writes)?;
    dict.set_item("spatial_indexes_built", report.spatial_indexes_built)?;
    dict.set_item("spatial_candidate_rows", report.spatial_candidate_rows)?;
    dict.set_item("spatial_exact_rows", report.spatial_exact_rows)?;
    dict.set_item(
        "spatial_false_positive_rows",
        report.spatial_false_positive_rows,
    )?;
    dict.set_item(
        "spatial_deduplicated_pairs",
        report.spatial_deduplicated_pairs,
    )?;
    dict.set_item(
        "spatial_algorithm_hash_grid",
        report.spatial_algorithm_hash_grid,
    )?;
    dict.set_item(
        "spatial_algorithm_quadtree",
        report.spatial_algorithm_quadtree,
    )?;
    dict.set_item("spatial_algorithm_octree", report.spatial_algorithm_octree)?;
    dict.set_item(
        "spatial_algorithm_hilbert_curve",
        report.spatial_algorithm_hilbert_curve,
    )?;
    dict.set_item("spatial_index_reuses", report.spatial_index_reuses)?;
    dict.set_item(
        "spatial_index_full_rebuilds",
        report.spatial_index_full_rebuilds,
    )?;
    dict.set_item(
        "spatial_index_incremental_updates",
        report.spatial_index_incremental_updates,
    )?;
    dict.set_item("spatial_parallel_chunks", report.spatial_parallel_chunks)?;
    dict.set_item("spatial_parallel_workers", report.spatial_parallel_workers)?;
    dict.set_item(
        "spatial_thread_scratch_reuses",
        report.spatial_thread_scratch_reuses,
    )?;
    dict.set_item(
        "spatial_candidate_buffer_growths",
        report.spatial_candidate_buffer_growths,
    )?;
    let canvas_commands = PyList::empty_bound(py);
    for command in &report.canvas_commands {
        let args = command
            .args
            .iter()
            .map(|value| ecs_value_to_py(py, value))
            .collect::<PyResult<Vec<_>>>()?;
        let args_tuple = PyTuple::new_bound(py, args).into_py(py);
        let item = PyTuple::new_bound(py, [command.command.clone().into_py(py), args_tuple]);
        canvas_commands.append(item)?;
    }
    dict.set_item("canvas_commands", canvas_commands)?;
    let canvas_fill_batches = PyList::empty_bound(py);
    for batch in &report.canvas_fill_batches {
        let records = PyList::empty_bound(py);
        for record in &batch.records {
            records.append(PyTuple::new_bound(
                py,
                [
                    record.kind.into_py(py),
                    record.a.into_py(py),
                    record.b.into_py(py),
                    record.c.into_py(py),
                    record.d.into_py(py),
                    record.e.into_py(py),
                    record.f.into_py(py),
                    record.r.into_py(py),
                    record.g.into_py(py),
                    record.blue.into_py(py),
                    record.alpha.into_py(py),
                ],
            ))?;
        }
        canvas_fill_batches.append(records)?;
    }
    dict.set_item("canvas_fill_batches", canvas_fill_batches)?;
    let component_writes = PyList::empty_bound(py);
    let resource_writes = PyList::empty_bound(py);
    if include_writes {
        for write in &report.writes {
            match write {
                ExecutionWrite::ComponentField {
                    entity,
                    component,
                    field,
                    value,
                } => {
                    let item = PyDict::new_bound(py);
                    item.set_item("index", entity.index)?;
                    item.set_item("generation", entity.generation)?;
                    item.set_item("component", component)?;
                    item.set_item("field", field)?;
                    item.set_item("value", ecs_value_to_py(py, value)?)?;
                    component_writes.append(item)?;
                }
                ExecutionWrite::ResourceField {
                    resource,
                    field,
                    value,
                } => {
                    let item = PyDict::new_bound(py);
                    item.set_item("resource", resource)?;
                    item.set_item("field", field)?;
                    item.set_item("value", ecs_value_to_py(py, value)?)?;
                    resource_writes.append(item)?;
                }
            }
        }
    }
    dict.set_item("component_writes", component_writes)?;
    dict.set_item("resource_writes", resource_writes)?;
    Ok(dict)
}
