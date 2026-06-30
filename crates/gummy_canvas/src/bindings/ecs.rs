use gummy_ecs::{
    health_check as ecs_core_health_check, AccessKey, ActionNode, BridgePlanPayload,
    BridgeQueryPayload, ComponentRow, ComponentSchema, EcsValue, Entity, ExprNode, FieldSchema,
    QueryFilter, QueryTerm, SpatialAlgorithmKind, SpatialIndexDescriptor, SpatialIndexRegistry,
    StorageType, World, ECS_ABI_VERSION,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyTuple};

fn py_to_ecs_value(value: &Bound<'_, PyAny>) -> PyResult<EcsValue> {
    if let Ok(value) = value.extract::<bool>() {
        return Ok(EcsValue::Bool(value));
    }
    if let Ok(value) = value.extract::<i64>() {
        return Ok(EcsValue::I64(value));
    }
    if let Ok(value) = value.extract::<u64>() {
        return Ok(EcsValue::U64(value));
    }
    if let Ok(value) = value.extract::<f64>() {
        return Ok(EcsValue::F64(value));
    }
    if let Ok(value) = value.extract::<String>() {
        return Ok(EcsValue::String(value));
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        return match tuple.len() {
            2 => Ok(EcsValue::Vec2F64([
                tuple.get_item(0)?.extract::<f64>()?,
                tuple.get_item(1)?.extract::<f64>()?,
            ])),
            3 => Ok(EcsValue::Vec3F64([
                tuple.get_item(0)?.extract::<f64>()?,
                tuple.get_item(1)?.extract::<f64>()?,
                tuple.get_item(2)?.extract::<f64>()?,
            ])),
            _ => Err(PyValueError::new_err(
                "ECS tuple values must have length 2 or 3",
            )),
        };
    }
    if let Ok(list) = value.downcast::<PyList>() {
        let mut values = Vec::with_capacity(list.len());
        for item in list.iter() {
            values.push(py_to_ecs_value(&item)?);
        }
        return Ok(EcsValue::List(values));
    }
    Err(PyValueError::new_err(
        "unsupported ECS value; expected bool, int, float, str, tuple[float, ...], or list",
    ))
}

fn ecs_value_to_py(py: Python<'_>, value: &EcsValue) -> PyResult<PyObject> {
    match value {
        EcsValue::Bool(value) => Ok(value.into_py(py)),
        EcsValue::I64(value) => Ok(value.into_py(py)),
        EcsValue::U64(value) => Ok(value.into_py(py)),
        EcsValue::F64(value) => Ok(value.into_py(py)),
        EcsValue::String(value) => Ok(value.into_py(py)),
        EcsValue::Vec2F32(value) => Ok((value[0], value[1]).into_py(py)),
        EcsValue::Vec2F64(value) => Ok((value[0], value[1]).into_py(py)),
        EcsValue::Vec3F32(value) => Ok((value[0], value[1], value[2]).into_py(py)),
        EcsValue::Vec3F64(value) => Ok((value[0], value[1], value[2]).into_py(py)),
        EcsValue::List(values) => {
            let items = values
                .iter()
                .map(|value| ecs_value_to_py(py, value))
                .collect::<PyResult<Vec<_>>>()?;
            Ok(PyList::new_bound(py, items).into_py(py))
        }
    }
}

fn component_row_from_dict(fields: &Bound<'_, PyDict>) -> PyResult<ComponentRow> {
    let mut row = ComponentRow::new();
    for (key, value) in fields.iter() {
        row.insert(key.extract::<String>()?, py_to_ecs_value(&value)?);
    }
    Ok(row)
}

fn component_row_to_dict<'py>(py: Python<'py>, row: ComponentRow) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    for (key, value) in row {
        dict.set_item(key, ecs_value_to_py(py, &value)?)?;
    }
    Ok(dict)
}

fn parse_spatial_algorithm(name: &str) -> PyResult<SpatialAlgorithmKind> {
    match name {
        "HashGrid" | "hash_grid" => Ok(SpatialAlgorithmKind::HashGrid),
        "Quadtree" | "quadtree" => Ok(SpatialAlgorithmKind::Quadtree),
        "Octree" | "octree" => Ok(SpatialAlgorithmKind::Octree),
        "HilbertCurve" | "hilbert_curve" | "Hilbert" | "hilbert" => {
            Ok(SpatialAlgorithmKind::HilbertCurve)
        }
        other => Err(PyValueError::new_err(format!(
            "unknown ECS spatial algorithm {other}"
        ))),
    }
}

fn spatial_algorithm_name(algorithm: &SpatialAlgorithmKind) -> &'static str {
    match algorithm {
        SpatialAlgorithmKind::HashGrid => "HashGrid",
        SpatialAlgorithmKind::Quadtree => "Quadtree",
        SpatialAlgorithmKind::Octree => "Octree",
        SpatialAlgorithmKind::HilbertCurve => "HilbertCurve",
    }
}

fn get_required<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("ECS bridge plan payload is missing '{key}'")))
}

fn get_optional<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(value) = dict.get_item(key)? else {
        return Ok(None);
    };
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(value))
    }
}

fn parse_usize_list(value: &Bound<'_, PyAny>, field: &str) -> PyResult<Vec<usize>> {
    let list = value.downcast::<PyList>().map_err(|_| {
        PyValueError::new_err(format!("ECS bridge plan field '{field}' must be a list"))
    })?;
    list.iter()
        .map(|item| item.extract::<usize>())
        .collect::<PyResult<Vec<_>>>()
}

fn parse_query_term(value: Bound<'_, PyAny>) -> PyResult<QueryTerm> {
    let (kind, name) = if let Ok(tuple) = value.downcast::<PyTuple>() {
        if tuple.len() != 2 {
            return Err(PyValueError::new_err(
                "ECS bridge query term tuples must have two items",
            ));
        }
        (
            tuple.get_item(0)?.extract::<String>()?,
            tuple.get_item(1)?.extract::<String>()?,
        )
    } else {
        let dict = value.downcast::<PyDict>().map_err(|_| {
            PyValueError::new_err("ECS bridge query terms must be dicts or (kind, name) tuples")
        })?;
        let kind = get_required(dict, "kind")?.extract::<String>()?;
        let name = if let Some(name) = get_optional(dict, "name")? {
            name.extract::<String>()?
        } else {
            get_required(dict, "value")?.extract::<String>()?
        };
        (kind, name)
    };
    match kind.as_str() {
        "with_component" | "component" => Ok(QueryTerm::WithComponent(name)),
        "without_component" | "not_component" => Ok(QueryTerm::WithoutComponent(name)),
        "with_tag" | "tag" => Ok(QueryTerm::WithTag(name)),
        "without_tag" | "not_tag" => Ok(QueryTerm::WithoutTag(name)),
        other => Err(PyValueError::new_err(format!(
            "unknown ECS bridge query term kind '{other}'"
        ))),
    }
}

fn parse_query_payload(value: Bound<'_, PyAny>) -> PyResult<BridgeQueryPayload> {
    let dict = value
        .downcast::<PyDict>()
        .map_err(|_| PyValueError::new_err("ECS bridge query payloads must be dicts"))?;
    let name = get_required(dict, "name")?.extract::<String>()?;
    let terms_any = get_required(dict, "terms")?;
    let terms_list = terms_any
        .downcast::<PyList>()
        .map_err(|_| PyValueError::new_err("ECS bridge query terms must be a list"))?;
    let mut terms = Vec::with_capacity(terms_list.len());
    for item in terms_list.iter() {
        terms.push(parse_query_term(item)?);
    }
    Ok(BridgeQueryPayload { name, terms })
}

fn parse_expr_node(value: Bound<'_, PyAny>) -> PyResult<ExprNode> {
    let dict = value
        .downcast::<PyDict>()
        .map_err(|_| PyValueError::new_err("ECS bridge expression nodes must be dicts"))?;
    let kind = get_required(dict, "kind")?.extract::<String>()?;
    match kind.as_str() {
        "literal_f64" | "f64" => Ok(ExprNode::LiteralF64(
            get_required(dict, "value")?.extract::<f64>()?,
        )),
        "literal_i64" | "i64" => Ok(ExprNode::LiteralI64(
            get_required(dict, "value")?.extract::<i64>()?,
        )),
        "literal_bool" | "bool" => Ok(ExprNode::LiteralBool(
            get_required(dict, "value")?.extract::<bool>()?,
        )),
        "literal_string" | "string" => Ok(ExprNode::LiteralString(
            get_required(dict, "value")?.extract::<String>()?,
        )),
        "field" => Ok(ExprNode::Field {
            query: get_required(dict, "query")?.extract::<String>()?,
            component: get_required(dict, "component")?.extract::<String>()?,
            field: get_required(dict, "field")?.extract::<String>()?,
        }),
        "resource_field" => Ok(ExprNode::ResourceField {
            resource: get_required(dict, "resource")?.extract::<String>()?,
            field: get_required(dict, "field")?.extract::<String>()?,
        }),
        "input_state" => Ok(ExprNode::InputState {
            name: get_required(dict, "name")?.extract::<String>()?,
            code: get_optional(dict, "code")?
                .map(|value| value.extract::<i64>())
                .transpose()?,
        }),
        "for_each_item" => Ok(ExprNode::ForEachItem {
            slot: get_required(dict, "slot")?.extract::<usize>()?,
        }),
        "unary" => Ok(ExprNode::Unary {
            op: get_required(dict, "op")?.extract::<String>()?,
            input: get_required(dict, "input")?.extract::<usize>()?,
        }),
        "binary" => Ok(ExprNode::Binary {
            op: get_required(dict, "op")?.extract::<String>()?,
            left: get_required(dict, "left")?.extract::<usize>()?,
            right: get_required(dict, "right")?.extract::<usize>()?,
        }),
        "context_join" => Ok(ExprNode::ContextJoin {
            left_query: get_required(dict, "left_query")?.extract::<String>()?,
            right_query: get_required(dict, "right_query")?.extract::<String>()?,
            predicate: get_required(dict, "predicate")?.extract::<usize>()?,
        }),
        "exists" => Ok(ExprNode::Exists {
            query: get_required(dict, "query")?.extract::<String>()?,
            predicate: get_required(dict, "predicate")?.extract::<usize>()?,
        }),
        "aggregate" => Ok(ExprNode::Aggregate {
            kind: get_required(dict, "aggregate")?.extract::<String>()?,
            relation: get_required(dict, "relation")?.extract::<usize>()?,
            group_query: get_optional(dict, "group_query")?
                .map(|value| value.extract::<String>())
                .transpose()?,
            value: get_optional(dict, "value")?
                .map(|value| value.extract::<usize>())
                .transpose()?,
        }),
        other => Err(PyValueError::new_err(format!(
            "unknown ECS bridge expression kind '{other}'"
        ))),
    }
}

fn parse_action_node(value: Bound<'_, PyAny>) -> PyResult<ActionNode> {
    let dict = value
        .downcast::<PyDict>()
        .map_err(|_| PyValueError::new_err("ECS bridge action nodes must be dicts"))?;
    let kind = get_required(dict, "kind")?.extract::<String>()?;
    match kind.as_str() {
        "noop" => Ok(ActionNode::Noop),
        "set_field" | "set" => Ok(ActionNode::SetField {
            target: get_required(dict, "target")?.extract::<usize>()?,
            value: get_required(dict, "value")?.extract::<usize>()?,
        }),
        "sequence" | "do_in_order" => Ok(ActionNode::Sequence(parse_usize_list(
            &get_required(dict, "children")?,
            "children",
        )?)),
        "parallel" | "do_in_parallel" => Ok(ActionNode::Parallel(parse_usize_list(
            &get_required(dict, "children")?,
            "children",
        )?)),
        "when" => Ok(ActionNode::When {
            condition: get_required(dict, "condition")?.extract::<usize>()?,
            then_action: get_required(dict, "then_action")?.extract::<usize>()?,
            otherwise_action: get_optional(dict, "otherwise_action")?
                .map(|value| value.extract::<usize>())
                .transpose()?,
        }),
        "for_each" => Ok(ActionNode::ForEach {
            source: get_required(dict, "source")?.extract::<usize>()?,
            item_slot: get_required(dict, "item_slot")?.extract::<usize>()?,
            action: get_required(dict, "action")?.extract::<usize>()?,
        }),
        "emit_event" => Ok(ActionNode::EmitEvent {
            event_type: get_required(dict, "event_type")?.extract::<String>()?,
            value: get_required(dict, "value")?.extract::<usize>()?,
        }),
        "udf" => Ok(ActionNode::Udf {
            descriptor: get_required(dict, "descriptor")?.extract::<String>()?,
            args: parse_usize_list(&get_required(dict, "args")?, "args")?,
            side_effects: get_optional(dict, "side_effects")?
                .map(|value| value.extract::<bool>())
                .transpose()?
                .unwrap_or(false),
        }),
        other => Err(PyValueError::new_err(format!(
            "unknown ECS bridge action kind '{other}'"
        ))),
    }
}

fn parse_bridge_plan_payload(payload: &Bound<'_, PyDict>) -> PyResult<BridgePlanPayload> {
    let queries_any = get_required(payload, "queries")?;
    let expressions_any = get_required(payload, "expressions")?;
    let actions_any = get_required(payload, "actions")?;
    let queries_list = queries_any
        .downcast::<PyList>()
        .map_err(|_| PyValueError::new_err("ECS bridge queries must be a list"))?;
    let expressions_list = expressions_any
        .downcast::<PyList>()
        .map_err(|_| PyValueError::new_err("ECS bridge expressions must be a list"))?;
    let actions_list = actions_any
        .downcast::<PyList>()
        .map_err(|_| PyValueError::new_err("ECS bridge actions must be a list"))?;

    let mut queries = Vec::with_capacity(queries_list.len());
    for item in queries_list.iter() {
        queries.push(parse_query_payload(item)?);
    }
    let mut expressions = Vec::with_capacity(expressions_list.len());
    for item in expressions_list.iter() {
        expressions.push(parse_expr_node(item)?);
    }
    let mut actions = Vec::with_capacity(actions_list.len());
    for item in actions_list.iter() {
        actions.push(parse_action_node(item)?);
    }

    Ok(BridgePlanPayload {
        version: get_required(payload, "version")?.extract::<u32>()?,
        schema_fingerprint: get_optional(payload, "schema_fingerprint")?
            .map(|value| value.extract::<u64>())
            .transpose()?,
        queries,
        expressions,
        actions,
        root_action: get_required(payload, "root_action")?.extract::<usize>()?,
    })
}

fn access_key_name(key: &AccessKey) -> String {
    match key {
        AccessKey::Component(name) => format!("component:{name}"),
        AccessKey::Resource(name) => format!("resource:{name}"),
        AccessKey::Event(name) => format!("event:{name}"),
        AccessKey::Hidden(name) => format!("hidden:{name}"),
    }
}

#[pyfunction]
pub(crate) fn ecs_abi_version() -> u32 {
    ECS_ABI_VERSION
}

#[pyfunction]
pub(crate) fn ecs_health_check() -> &'static str {
    ecs_core_health_check()
}

#[pyclass(name = "EcsSpatialIndexRegistry")]
pub(crate) struct PyEcsSpatialIndexRegistry {
    registry: SpatialIndexRegistry,
}

#[pymethods]
impl PyEcsSpatialIndexRegistry {
    #[new]
    fn new() -> Self {
        Self {
            registry: SpatialIndexRegistry::new(),
        }
    }

    #[pyo3(signature = (target_query, dimensions, algorithm, update_policy, name=None))]
    fn intern(
        &mut self,
        target_query: Vec<String>,
        dimensions: u8,
        algorithm: String,
        update_policy: String,
        name: Option<String>,
    ) -> PyResult<u64> {
        if dimensions != 2 && dimensions != 3 {
            return Err(PyValueError::new_err(
                "ECS spatial index dimensions must be 2 or 3",
            ));
        }
        let descriptor = SpatialIndexDescriptor {
            name,
            target_query,
            dimensions,
            algorithm: parse_spatial_algorithm(&algorithm)?,
            update_policy,
        };
        Ok(self.registry.intern(descriptor))
    }

    fn release(&mut self, id: u64) {
        self.registry.release(id);
    }

    fn mark_stale(&mut self, reason: String) {
        self.registry.mark_stale(reason);
    }

    fn len(&self) -> usize {
        self.registry.len()
    }

    fn get<'py>(&self, py: Python<'py>, id: u64) -> PyResult<Option<Bound<'py, PyDict>>> {
        let Some(slot) = self.registry.get(id) else {
            return Ok(None);
        };
        let dict = PyDict::new_bound(py);
        dict.set_item("name", slot.descriptor.name.clone())?;
        dict.set_item("target_query", slot.descriptor.target_query.clone())?;
        dict.set_item("dimensions", slot.descriptor.dimensions)?;
        dict.set_item(
            "algorithm",
            spatial_algorithm_name(&slot.descriptor.algorithm),
        )?;
        dict.set_item("update_policy", slot.descriptor.update_policy.clone())?;
        dict.set_item("ref_count", slot.ref_count)?;
        let stats = PyDict::new_bound(py);
        stats.set_item("builds", slot.stats.builds)?;
        stats.set_item("queries", slot.stats.queries)?;
        stats.set_item("candidate_rows", slot.stats.candidate_rows)?;
        stats.set_item("exact_rows", slot.stats.exact_rows)?;
        stats.set_item("stale", slot.stats.stale)?;
        stats.set_item("stale_reason", slot.stats.stale_reason.clone())?;
        dict.set_item("stats", stats)?;
        Ok(Some(dict))
    }
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
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        Ok((entity.index, entity.generation))
    }

    fn despawn_entity(&mut self, index: u32, generation: u32) -> PyResult<()> {
        self.world
            .despawn(Entity { index, generation })
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn validate_entity(&self, index: u32, generation: u32) -> PyResult<()> {
        self.world
            .validate_entity(Entity { index, generation })
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn register_schema(&mut self, name: String, fields: Vec<(String, String)>) -> PyResult<()> {
        let fields = fields
            .into_iter()
            .map(|(field_name, storage_name)| {
                StorageType::parse(&storage_name)
                    .map(|storage_type| FieldSchema::new(field_name, storage_type))
            })
            .collect::<gummy_ecs::Result<Vec<_>>>()
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        self.world
            .register_schema(ComponentSchema::new(name, fields))
            .map_err(|err| PyValueError::new_err(err.to_string()))
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
        &self,
        py: Python<'py>,
        payload: &Bound<'_, PyDict>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let payload = parse_bridge_plan_payload(payload)?;
        let plan = self
            .world
            .compile_bridge_plan(payload)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
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
            .add_component_default(Entity { index, generation }, component)
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn remove_component(&mut self, index: u32, generation: u32, component: String) -> PyResult<()> {
        self.world
            .remove_component(Entity { index, generation }, &component)
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn add_tag(&mut self, index: u32, generation: u32, tag: String) -> PyResult<()> {
        self.world
            .add_tag(Entity { index, generation }, &tag)
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn remove_tag(&mut self, index: u32, generation: u32, tag: String) -> PyResult<()> {
        self.world
            .remove_tag(Entity { index, generation }, &tag)
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn entity_components(&self, index: u32, generation: u32) -> PyResult<Vec<String>> {
        self.world
            .entity_components(Entity { index, generation })
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn entity_tags(&self, index: u32, generation: u32) -> PyResult<Vec<String>> {
        self.world
            .entity_tags(Entity { index, generation })
            .map_err(|err| PyValueError::new_err(err.to_string()))
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
            .set_field(Entity { index, generation }, &component, &field, value)
            .map_err(|err| PyValueError::new_err(err.to_string()))
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
            .get_field(Entity { index, generation }, &component, &field)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        ecs_value_to_py(py, &value)
    }

    fn query_entities(&mut self, components: Vec<String>) -> PyResult<Vec<(u32, u32)>> {
        let entities = self
            .world
            .query(components)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
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
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        Ok(entities
            .into_iter()
            .map(|entity| (entity.index, entity.generation))
            .collect())
    }

    fn insert_resource(&mut self, name: String, fields: &Bound<'_, PyDict>) -> PyResult<()> {
        self.world
            .insert_resource(name, component_row_from_dict(fields)?)
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn remove_resource<'py>(
        &mut self,
        py: Python<'py>,
        name: String,
    ) -> PyResult<Bound<'py, PyDict>> {
        let row = self
            .world
            .remove_resource(&name)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        component_row_to_dict(py, row)
    }

    fn resource_field(&self, py: Python<'_>, name: String, field: String) -> PyResult<PyObject> {
        let value = self
            .world
            .resource_field(&name, &field)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
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
            .map_err(|err| PyValueError::new_err(err.to_string()))
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
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    fn read_events<'py>(
        &self,
        py: Python<'py>,
        event_type: String,
    ) -> PyResult<Bound<'py, PyList>> {
        let events = self
            .world
            .read_events(&event_type)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
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
            .stage_add_component(Entity { index, generation }, component);
    }

    fn stage_remove_component(&mut self, index: u32, generation: u32, component: String) {
        self.world
            .stage_remove_component(Entity { index, generation }, component);
    }

    fn stage_despawn(&mut self, index: u32, generation: u32) {
        self.world.stage_despawn(Entity { index, generation });
    }

    fn apply_staged(&mut self) -> PyResult<()> {
        self.world
            .apply_staged()
            .map_err(|err| PyValueError::new_err(err.to_string()))
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
