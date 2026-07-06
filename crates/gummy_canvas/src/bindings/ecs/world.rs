use std::fmt::Display;

use gummy_ecs::{ComponentSchema, Entity, FieldSchema, QueryFilter, QueryTerm, StorageType, World};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyTuple};

use super::parse::parse_bridge_plan_payload;
use super::summaries::{execution_report_to_dict, physical_plan_summary_to_dict};
use super::values::{
    component_row_from_dict, component_row_to_dict, ecs_value_to_py, py_to_ecs_value,
};

fn py_value_error(err: impl Display) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn entity(index: u32, generation: u32) -> Entity {
    Entity { index, generation }
}

#[pyclass(name = "EcsWorld")]
pub(crate) struct PyEcsWorld {
    world: World,
}

#[pymethods]
impl PyEcsWorld {
    #[new]
    fn new() -> Self {
        Self {
            world: World::new(),
        }
    }

    fn allocate_entity(&mut self) -> (u32, u32) {
        let entity = self.world.spawn_empty();
        (entity.index, entity.generation)
    }

    fn spawn_with_defaults(&mut self, components: Vec<String>) -> PyResult<(u32, u32)> {
        let entity = self
            .world
            .spawn_with_defaults(components)
            .map_err(py_value_error)?;
        Ok((entity.index, entity.generation))
    }

    fn despawn_entity(&mut self, index: u32, generation: u32) -> PyResult<()> {
        self.world
            .despawn(entity(index, generation))
            .map_err(py_value_error)
    }

    fn validate_entity(&self, index: u32, generation: u32) -> PyResult<()> {
        self.world
            .validate_entity(entity(index, generation))
            .map_err(py_value_error)
    }

    fn register_schema(&mut self, name: String, fields: Vec<(String, String)>) -> PyResult<()> {
        let fields = fields
            .into_iter()
            .map(|(field_name, storage_name)| {
                StorageType::parse(&storage_name)
                    .map(|storage_type| FieldSchema::new(field_name, storage_type))
            })
            .collect::<gummy_ecs::Result<Vec<_>>>()
            .map_err(py_value_error)?;
        self.world
            .register_schema(ComponentSchema::new(name, fields))
            .map_err(py_value_error)
    }

    fn alive_count(&self) -> usize {
        self.world.alive_count()
    }

    fn schema_count(&self) -> usize {
        self.world.schema_count()
    }

    fn schema_fingerprint(&self) -> u64 {
        self.world.schema_fingerprint()
    }

    fn compile_bridge_plan<'py>(
        &mut self,
        py: Python<'py>,
        payload: &Bound<'_, PyDict>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let payload = parse_bridge_plan_payload(payload)?;
        let plan = self
            .world
            .compile_bridge_plan(payload)
            .map_err(py_value_error)?;
        let dict = physical_plan_summary_to_dict(py, &plan)?;
        let handle = self
            .world
            .store_compiled_plan(plan)
            .map_err(py_value_error)?;
        dict.set_item("handle", handle)?;
        Ok(dict)
    }

    #[pyo3(signature = (handle, include_writes=true))]
    fn execute_compiled_plan<'py>(
        &mut self,
        py: Python<'py>,
        handle: u64,
        include_writes: bool,
    ) -> PyResult<Bound<'py, PyDict>> {
        let report = py
            .allow_threads(|| {
                self.world
                    .execute_compiled_plan_with_options(handle, include_writes)
            })
            .map_err(py_value_error)?;
        execution_report_to_dict(py, &report, include_writes)
    }

    #[pyo3(signature = (handles, include_writes=true))]
    fn execute_compiled_plans<'py>(
        &mut self,
        py: Python<'py>,
        handles: Vec<u64>,
        include_writes: bool,
    ) -> PyResult<Bound<'py, PyList>> {
        let reports = py
            .allow_threads(|| {
                self.world
                    .execute_compiled_plans_with_options(&handles, include_writes)
            })
            .map_err(py_value_error)?;
        let out = PyList::empty_bound(py);
        for report in reports {
            out.append(execution_report_to_dict(py, &report, include_writes)?)?;
        }
        Ok(out)
    }

    fn warm_compiled_plan_spatial_indexes<'py>(
        &mut self,
        py: Python<'py>,
        handle: u64,
    ) -> PyResult<Bound<'py, PyDict>> {
        let report = py
            .allow_threads(|| self.world.warm_compiled_plan_spatial_indexes(handle))
            .map_err(py_value_error)?;
        execution_report_to_dict(py, &report, false)
    }

    fn release_compiled_plan(&mut self, handle: u64) -> bool {
        self.world.release_compiled_plan(handle)
    }

    fn compiled_plan_count(&self) -> usize {
        self.world.compiled_plan_count()
    }

    fn spatial_index_cache_len(&self) -> usize {
        self.world.spatial_index_cache_len()
    }

    fn structural_revision(&self) -> u64 {
        self.world.structural_revision()
    }

    fn field_revision(&self) -> u64 {
        self.world.field_revision()
    }

    #[pyo3(signature = (name, value, code=None))]
    fn set_input_state(
        &mut self,
        name: String,
        value: &Bound<'_, PyAny>,
        code: Option<i64>,
    ) -> PyResult<()> {
        self.world
            .set_input_state(name, code, py_to_ecs_value(value)?);
        Ok(())
    }

    fn execute_bridge_plan<'py>(
        &mut self,
        py: Python<'py>,
        payload: &Bound<'_, PyDict>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let payload = parse_bridge_plan_payload(payload)?;
        let report = py
            .allow_threads(|| self.world.execute_bridge_plan(payload))
            .map_err(py_value_error)?;
        execution_report_to_dict(py, &report, true)
    }

    fn archetype_count(&self) -> usize {
        self.world.archetype_count()
    }

    fn add_component_default(
        &mut self,
        index: u32,
        generation: u32,
        component: String,
    ) -> PyResult<()> {
        self.world
            .add_component_default(entity(index, generation), component)
            .map_err(py_value_error)
    }

    fn remove_component(&mut self, index: u32, generation: u32, component: String) -> PyResult<()> {
        self.world
            .remove_component(entity(index, generation), &component)
            .map_err(py_value_error)
    }

    fn add_tag(&mut self, index: u32, generation: u32, tag: String) -> PyResult<()> {
        self.world
            .add_tag(entity(index, generation), &tag)
            .map_err(py_value_error)
    }

    fn remove_tag(&mut self, index: u32, generation: u32, tag: String) -> PyResult<()> {
        self.world
            .remove_tag(entity(index, generation), &tag)
            .map_err(py_value_error)
    }

    fn entity_components(&self, index: u32, generation: u32) -> PyResult<Vec<String>> {
        self.world
            .entity_components(entity(index, generation))
            .map_err(py_value_error)
    }

    fn entity_tags(&self, index: u32, generation: u32) -> PyResult<Vec<String>> {
        self.world
            .entity_tags(entity(index, generation))
            .map_err(py_value_error)
    }

    fn set_field(
        &mut self,
        index: u32,
        generation: u32,
        component: String,
        field: String,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let value = py_to_ecs_value(value)?;
        self.world
            .set_field(entity(index, generation), &component, &field, value)
            .map_err(py_value_error)
    }

    fn get_field(
        &self,
        py: Python<'_>,
        index: u32,
        generation: u32,
        component: String,
        field: String,
    ) -> PyResult<PyObject> {
        let value = self
            .world
            .get_field(entity(index, generation), &component, &field)
            .map_err(py_value_error)?;
        ecs_value_to_py(py, &value)
    }

    fn query_entities(&mut self, components: Vec<String>) -> PyResult<Vec<(u32, u32)>> {
        let entities = self.world.query(components).map_err(py_value_error)?;
        Ok(entities
            .into_iter()
            .map(|entity| (entity.index, entity.generation))
            .collect())
    }

    fn query_filtered(
        &mut self,
        required_components: Vec<String>,
        required_tags: Vec<String>,
        excluded_components: Vec<String>,
        excluded_tags: Vec<String>,
    ) -> PyResult<Vec<(u32, u32)>> {
        let terms = required_components
            .into_iter()
            .map(QueryTerm::WithComponent)
            .chain(required_tags.into_iter().map(QueryTerm::WithTag))
            .chain(
                excluded_components
                    .into_iter()
                    .map(QueryTerm::WithoutComponent),
            )
            .chain(excluded_tags.into_iter().map(QueryTerm::WithoutTag));
        let entities = self
            .world
            .query_filter(QueryFilter::new(terms))
            .map_err(py_value_error)?;
        Ok(entities
            .into_iter()
            .map(|entity| (entity.index, entity.generation))
            .collect())
    }

    fn query_component_fields(
        &mut self,
        py: Python<'_>,
        required_components: Vec<String>,
        required_tags: Vec<String>,
        component: String,
        fields: Vec<String>,
    ) -> PyResult<Vec<PyObject>> {
        let terms = required_components
            .into_iter()
            .map(QueryTerm::WithComponent)
            .chain(required_tags.into_iter().map(QueryTerm::WithTag));
        let entities = self
            .world
            .query_filter(QueryFilter::new(terms))
            .map_err(py_value_error)?;
        let mut rows = Vec::with_capacity(entities.len());
        for entity in entities {
            let mut values = Vec::with_capacity(fields.len());
            for field in &fields {
                let value = self
                    .world
                    .get_field(entity, &component, field)
                    .map_err(py_value_error)?;
                values.push(ecs_value_to_py(py, &value)?);
            }
            rows.push(PyTuple::new_bound(py, values).into_py(py));
        }
        Ok(rows)
    }

    fn insert_resource(&mut self, name: String, fields: &Bound<'_, PyDict>) -> PyResult<()> {
        self.world
            .insert_resource(name, component_row_from_dict(fields)?)
            .map_err(py_value_error)
    }

    fn remove_resource<'py>(
        &mut self,
        py: Python<'py>,
        name: String,
    ) -> PyResult<Bound<'py, PyDict>> {
        let row = self.world.remove_resource(&name).map_err(py_value_error)?;
        component_row_to_dict(py, row)
    }

    fn resource_field(&self, py: Python<'_>, name: String, field: String) -> PyResult<PyObject> {
        let value = self
            .world
            .resource_field(&name, &field)
            .map_err(py_value_error)?;
        ecs_value_to_py(py, &value)
    }

    fn set_resource_field(
        &mut self,
        name: String,
        field: String,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.world
            .set_resource_field(&name, &field, py_to_ecs_value(value)?)
            .map_err(py_value_error)
    }

    fn has_resource(&self, name: String) -> bool {
        self.world.has_resource(&name)
    }

    fn resource_count(&self) -> usize {
        self.world.resource_count()
    }

    fn resource_revision(&self, name: String) -> u64 {
        self.world.resource_revision(&name)
    }

    fn set_frame(&mut self, frame: u64) {
        self.world.set_frame(frame);
    }

    fn emit_event(&mut self, event_type: String, payload: &Bound<'_, PyAny>) -> PyResult<()> {
        self.world
            .emit_event(&event_type, py_to_ecs_value(payload)?)
            .map_err(py_value_error)
    }

    fn read_events<'py>(
        &self,
        py: Python<'py>,
        event_type: String,
    ) -> PyResult<Bound<'py, PyList>> {
        let events = self
            .world
            .read_events(&event_type)
            .map_err(py_value_error)?;
        let out = PyList::empty_bound(py);
        for event in events {
            let item = PyDict::new_bound(py);
            item.set_item("frame", event.frame)?;
            item.set_item("sequence", event.sequence)?;
            item.set_item("payload", ecs_value_to_py(py, &event.payload)?)?;
            out.append(item)?;
        }
        Ok(out)
    }

    #[pyo3(signature = (event_type=None))]
    fn clear_events(&mut self, event_type: Option<String>) {
        self.world.clear_events(event_type.as_deref());
    }

    fn event_queue_len(&self, event_type: String) -> usize {
        self.world.event_queue_len(&event_type)
    }

    fn stage_spawn(&mut self, components: Vec<String>) {
        self.world.stage_spawn(components);
    }

    fn stage_add_component(&mut self, index: u32, generation: u32, component: String) {
        self.world
            .stage_add_component(entity(index, generation), component);
    }

    fn stage_remove_component(&mut self, index: u32, generation: u32, component: String) {
        self.world
            .stage_remove_component(entity(index, generation), component);
    }

    fn stage_despawn(&mut self, index: u32, generation: u32) {
        self.world.stage_despawn(entity(index, generation));
    }

    fn apply_staged(&mut self) -> PyResult<()> {
        self.world.apply_staged().map_err(py_value_error)
    }

    fn staged_command_count(&self) -> usize {
        self.world.staged_command_count()
    }

    fn reset_diagnostics(&mut self) {
        self.world.reset_diagnostics();
    }

    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let diagnostics = self.world.diagnostics();
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
        dict.set_item("resources_total", diagnostics.resources_total)?;
        dict.set_item("event_queues_total", diagnostics.event_queues_total)?;
        Ok(dict)
    }
}
