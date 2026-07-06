use gummy_ecs::{
    ActionNode, BridgePlanPayload, BridgeQueryPayload, Entity, ExprNode, QueryTerm,
    SpatialAlgorithmKind, SpatialAlgorithmNode, SpatialBoundsExprNode, SpatialRelationNode,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyTuple};

use super::values::py_to_ecs_value;

pub(super) fn parse_spatial_algorithm(name: &str) -> PyResult<SpatialAlgorithmKind> {
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

pub(super) fn spatial_algorithm_name(algorithm: &SpatialAlgorithmKind) -> &'static str {
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

fn get_optional_parsed<T>(
    dict: &Bound<'_, PyDict>,
    key: &str,
    parse: impl FnOnce(Bound<'_, PyAny>) -> PyResult<T>,
) -> PyResult<Option<T>> {
    get_optional(dict, key)?.map(parse).transpose()
}

fn require_dict<'a, 'py>(
    value: &'a Bound<'py, PyAny>,
    message: &'static str,
) -> PyResult<&'a Bound<'py, PyDict>> {
    value
        .downcast::<PyDict>()
        .map_err(|_| PyValueError::new_err(message))
}

fn parse_list<T>(
    value: &Bound<'_, PyAny>,
    field: &str,
    mut parse_item: impl FnMut(Bound<'_, PyAny>) -> PyResult<T>,
) -> PyResult<Vec<T>> {
    let list = value.downcast::<PyList>().map_err(|_| {
        PyValueError::new_err(format!("ECS bridge plan field '{field}' must be a list"))
    })?;
    list.iter().map(|item| parse_item(item)).collect()
}

fn parse_usize_list(value: &Bound<'_, PyAny>, field: &str) -> PyResult<Vec<usize>> {
    parse_list(value, field, |item| item.extract::<usize>())
}

fn parse_f64_list(value: &Bound<'_, PyAny>, field: &str) -> PyResult<Vec<f64>> {
    parse_list(value, field, |item| item.extract::<f64>())
}

fn entity_from_parts(index: Bound<'_, PyAny>, generation: Bound<'_, PyAny>) -> PyResult<Entity> {
    Ok(Entity {
        index: index.extract::<u32>()?,
        generation: generation.extract::<u32>()?,
    })
}

fn parse_entity_payload(value: Bound<'_, PyAny>) -> PyResult<Entity> {
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        if tuple.len() != 2 {
            return Err(PyValueError::new_err(
                "ECS entity handle tuples must contain (index, generation)",
            ));
        }
        return entity_from_parts(tuple.get_item(0)?, tuple.get_item(1)?);
    }
    if let Ok(list) = value.downcast::<PyList>() {
        if list.len() != 2 {
            return Err(PyValueError::new_err(
                "ECS entity handle lists must contain [index, generation]",
            ));
        }
        return entity_from_parts(list.get_item(0)?, list.get_item(1)?);
    }
    let dict = require_dict(&value, "ECS entity handles must be tuples, lists, or dicts")?;
    Ok(Entity {
        index: get_required(dict, "index")?.extract::<u32>()?,
        generation: get_required(dict, "generation")?.extract::<u32>()?,
    })
}

fn parse_entity_list(value: &Bound<'_, PyAny>, field: &str) -> PyResult<Vec<Entity>> {
    parse_list(value, field, parse_entity_payload)
}

fn parse_spatial_bounds_expr(value: Bound<'_, PyAny>) -> PyResult<SpatialBoundsExprNode> {
    let dict = require_dict(&value, "ECS spatial bounds nodes must be dicts")?;
    Ok(SpatialBoundsExprNode {
        minimum: parse_usize_list(&get_required(dict, "minimum")?, "minimum")?,
        maximum: parse_usize_list(&get_required(dict, "maximum")?, "maximum")?,
    })
}

pub(super) fn parse_spatial_algorithm_node(
    value: Bound<'_, PyAny>,
) -> PyResult<SpatialAlgorithmNode> {
    let dict = require_dict(&value, "ECS spatial algorithm nodes must be dicts")?;
    Ok(SpatialAlgorithmNode {
        kind: get_required(dict, "kind")?.extract::<String>()?,
        dimensions: get_required(dict, "dimensions")?.extract::<u8>()?,
        cell_size: get_optional_parsed(dict, "cell_size", |value| value.extract::<f64>())?,
        bounds: get_optional_parsed(dict, "bounds", |value| parse_f64_list(&value, "bounds"))?,
        capacity: get_optional_parsed(dict, "capacity", |value| value.extract::<usize>())?,
        bits: get_optional_parsed(dict, "bits", |value| value.extract::<u8>())?,
    })
}

fn parse_spatial_relation_node(value: Bound<'_, PyAny>) -> PyResult<SpatialRelationNode> {
    let dict = require_dict(&value, "ECS spatial relation nodes must be dicts")?;
    Ok(SpatialRelationNode {
        id: get_required(dict, "id")?.extract::<String>()?,
        index_id: get_required(dict, "index_id")?.extract::<String>()?,
        origin_query: get_required(dict, "origin_query")?.extract::<String>()?,
        item_query: get_required(dict, "item_query")?.extract::<String>()?,
        origin_position: parse_usize_list(
            &get_required(dict, "origin_position")?,
            "origin_position",
        )?,
        target_position: parse_usize_list(
            &get_required(dict, "target_position")?,
            "target_position",
        )?,
        radius: get_optional_parsed(dict, "radius", |value| value.extract::<usize>())?,
        origin_bounds: get_optional_parsed(dict, "origin_bounds", parse_spatial_bounds_expr)?,
        target_bounds: get_optional_parsed(dict, "target_bounds", parse_spatial_bounds_expr)?,
        algorithm: parse_spatial_algorithm_node(get_required(dict, "algorithm")?)?,
        include_self: get_optional_parsed(dict, "include_self", |value| value.extract::<bool>())?
            .unwrap_or(false),
        pair_policy: get_optional_parsed(dict, "pair_policy", |value| value.extract::<String>())?
            .unwrap_or_else(|| "all".to_string()),
        exact_filter: get_optional_parsed(dict, "exact_filter", |value| value.extract::<usize>())?,
    })
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
    let dict = require_dict(&value, "ECS bridge query payloads must be dicts")?;
    let name = get_required(dict, "name")?.extract::<String>()?;
    let terms = parse_list(&get_required(dict, "terms")?, "terms", parse_query_term)?;
    let allowed_entities = get_optional_parsed(dict, "allowed_entities", |value| {
        parse_entity_list(&value, "allowed_entities")
    })?;
    Ok(BridgeQueryPayload {
        name,
        terms,
        allowed_entities,
    })
}

fn parse_expr_node(value: Bound<'_, PyAny>) -> PyResult<ExprNode> {
    let dict = require_dict(&value, "ECS bridge expression nodes must be dicts")?;
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
        "literal_value" | "value" => Ok(ExprNode::LiteralValue(py_to_ecs_value(&get_required(
            dict, "value",
        )?)?)),
        "field" => Ok(ExprNode::Field {
            query: get_required(dict, "query")?.extract::<String>()?,
            component: get_required(dict, "component")?.extract::<String>()?,
            field: get_required(dict, "field")?.extract::<String>()?,
        }),
        "resource_field" => Ok(ExprNode::ResourceField {
            resource: get_required(dict, "resource")?.extract::<String>()?,
            field: get_required(dict, "field")?.extract::<String>()?,
        }),
        "attribute" => Ok(ExprNode::Attribute {
            input: get_required(dict, "input")?.extract::<usize>()?,
            attribute: get_required(dict, "attribute")?.extract::<String>()?,
        }),
        "event_stream" => Ok(ExprNode::EventStream {
            event_type: get_required(dict, "event_type")?.extract::<String>()?,
        }),
        "input_state" => Ok(ExprNode::InputState {
            name: get_required(dict, "name")?.extract::<String>()?,
            code: get_optional_parsed(dict, "code", |value| value.extract::<i64>())?,
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
            group_query: get_optional_parsed(dict, "group_query", |value| {
                value.extract::<String>()
            })?,
            value: get_optional_parsed(dict, "value", |value| value.extract::<usize>())?,
            default: get_optional_parsed(dict, "default", |value| value.extract::<usize>())?,
        }),
        "spatial_metadata" => Ok(ExprNode::SpatialMetadata {
            relation: parse_spatial_relation_node(get_required(dict, "relation")?)?,
            kind: get_required(dict, "metadata")?.extract::<String>()?,
            axis: get_optional_parsed(dict, "axis", |value| value.extract::<usize>())?,
        }),
        "spatial_aggregate" => Ok(ExprNode::SpatialAggregate {
            kind: get_required(dict, "aggregate")?.extract::<String>()?,
            relation: parse_spatial_relation_node(get_required(dict, "relation")?)?,
            value: get_optional_parsed(dict, "value", |value| value.extract::<usize>())?,
            default: get_optional_parsed(dict, "default", |value| value.extract::<usize>())?,
        }),
        other => Err(PyValueError::new_err(format!(
            "unknown ECS bridge expression kind '{other}'"
        ))),
    }
}

fn parse_action_node(value: Bound<'_, PyAny>) -> PyResult<ActionNode> {
    let dict = require_dict(&value, "ECS bridge action nodes must be dicts")?;
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
            otherwise_action: get_optional_parsed(dict, "otherwise_action", |value| {
                value.extract::<usize>()
            })?,
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
        "add_component" => Ok(ActionNode::AddComponent {
            query: get_required(dict, "query")?.extract::<String>()?,
            component: get_required(dict, "component")?.extract::<String>()?,
            value: get_optional_parsed(dict, "value", |value| value.extract::<usize>())?,
        }),
        "remove_component" => Ok(ActionNode::RemoveComponent {
            query: get_required(dict, "query")?.extract::<String>()?,
            component: get_required(dict, "component")?.extract::<String>()?,
        }),
        "add_tag" => Ok(ActionNode::AddTag {
            query: get_required(dict, "query")?.extract::<String>()?,
            tag: get_required(dict, "tag")?.extract::<String>()?,
        }),
        "remove_tag" => Ok(ActionNode::RemoveTag {
            query: get_required(dict, "query")?.extract::<String>()?,
            tag: get_required(dict, "tag")?.extract::<String>()?,
        }),
        "despawn" => Ok(ActionNode::Despawn {
            query: get_required(dict, "query")?.extract::<String>()?,
        }),
        "udf" => Ok(ActionNode::Udf {
            descriptor: get_required(dict, "descriptor")?.extract::<String>()?,
            args: parse_usize_list(&get_required(dict, "args")?, "args")?,
            side_effects: get_optional_parsed(dict, "side_effects", |value| {
                value.extract::<bool>()
            })?
            .unwrap_or(false),
        }),
        other => Err(PyValueError::new_err(format!(
            "unknown ECS bridge action kind '{other}'"
        ))),
    }
}

pub(super) fn parse_bridge_plan_payload(
    payload: &Bound<'_, PyDict>,
) -> PyResult<BridgePlanPayload> {
    let queries = parse_list(
        &get_required(payload, "queries")?,
        "queries",
        parse_query_payload,
    )?;
    let expressions = parse_list(
        &get_required(payload, "expressions")?,
        "expressions",
        parse_expr_node,
    )?;
    let actions = parse_list(
        &get_required(payload, "actions")?,
        "actions",
        parse_action_node,
    )?;

    Ok(BridgePlanPayload {
        version: get_required(payload, "version")?.extract::<u32>()?,
        schema_fingerprint: get_optional_parsed(payload, "schema_fingerprint", |value| {
            value.extract::<u64>()
        })?,
        queries,
        expressions,
        actions,
        root_action: get_required(payload, "root_action")?.extract::<usize>()?,
    })
}
