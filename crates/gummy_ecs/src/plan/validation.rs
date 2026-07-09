use std::collections::BTreeSet;

use crate::error::{EcsError, Result};
use crate::query::QueryTerm;
use crate::schema::SchemaRegistry;

use super::{ActionNode, ExprNode, PhysicalPlan, SpatialRelationNode, BRIDGE_PLAN_VERSION};

pub fn validate_plan(plan: &PhysicalPlan) -> Result<()> {
    validate_plan_shape(plan)
}

pub fn validate_plan_with_schemas(plan: &PhysicalPlan, schemas: &SchemaRegistry) -> Result<()> {
    validate_plan_shape(plan)?;
    let query_names = plan
        .queries
        .iter()
        .map(|query| query.name.as_str())
        .collect::<BTreeSet<_>>();
    for expr in &plan.expressions {
        match expr {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown query {query} in field expression"
                    )));
                }
                validate_component_field(schemas, component, field)?;
            }
            ExprNode::ResourceField { resource, field } => {
                validate_component_field(schemas, resource, field)?;
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                ..
            } => {
                if !query_names.contains(left_query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown left query {left_query} in context join"
                    )));
                }
                if !query_names.contains(right_query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown right query {right_query} in context join"
                    )));
                }
            }
            ExprNode::Exists { query, .. } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown query {query} in exists expression"
                    )));
                }
            }
            ExprNode::Aggregate {
                group_query: Some(query),
                ..
            } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown group query {query} in aggregate"
                    )));
                }
            }
            ExprNode::Aggregate { .. } => {}
            ExprNode::SpatialMetadata { relation, .. }
            | ExprNode::SpatialAggregate { relation, .. } => {
                validate_spatial_relation_queries(relation, &query_names)?;
            }
            ExprNode::EventStream { event_type } => {
                if event_type.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "event stream type cannot be empty".to_string(),
                    ));
                }
            }
            _ => {}
        }
    }
    for action in &plan.actions {
        match action {
            ActionNode::AddComponent {
                query, component, ..
            }
            | ActionNode::RemoveComponent { query, component } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown query {query} in structural component action"
                    )));
                }
                if !schemas.contains(component) {
                    return Err(EcsError::UnknownSchema(component.clone()));
                }
            }
            ActionNode::AddTag { query, tag } | ActionNode::RemoveTag { query, tag } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown query {query} in structural tag action"
                    )));
                }
                if tag.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "tag action cannot use an empty tag".to_string(),
                    ));
                }
            }
            ActionNode::Despawn { query } => {
                if !query_names.contains(query.as_str()) {
                    return Err(EcsError::InvalidPlan(format!(
                        "unknown query {query} in despawn action"
                    )));
                }
            }
            _ => {}
        }
    }
    Ok(())
}

pub(super) fn validate_query_terms(terms: &[QueryTerm], schemas: &SchemaRegistry) -> Result<()> {
    for term in terms {
        match term {
            QueryTerm::WithComponent(component) | QueryTerm::WithoutComponent(component) => {
                if !schemas.contains(component) {
                    return Err(EcsError::UnknownSchema(component.clone()));
                }
            }
            QueryTerm::WithTag(tag) | QueryTerm::WithoutTag(tag) => {
                if tag.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "tag filter cannot be empty".to_string(),
                    ));
                }
            }
        }
    }
    Ok(())
}

fn validate_spatial_relation_queries(
    relation: &SpatialRelationNode,
    query_names: &BTreeSet<&str>,
) -> Result<()> {
    if !query_names.contains(relation.origin_query.as_str()) {
        return Err(EcsError::InvalidPlan(format!(
            "unknown spatial origin query {}",
            relation.origin_query
        )));
    }
    if !query_names.contains(relation.item_query.as_str()) {
        return Err(EcsError::InvalidPlan(format!(
            "unknown spatial item query {}",
            relation.item_query
        )));
    }
    if relation.id.is_empty() || relation.index_id.is_empty() {
        return Err(EcsError::InvalidPlan(
            "spatial relation id and index id cannot be empty".to_string(),
        ));
    }
    if relation.algorithm.dimensions != 2 && relation.algorithm.dimensions != 3 {
        return Err(EcsError::InvalidPlan(
            "spatial algorithm dimensions must be 2 or 3".to_string(),
        ));
    }
    Ok(())
}

fn validate_component_field(schemas: &SchemaRegistry, component: &str, field: &str) -> Result<()> {
    let schema = schemas
        .get(component)
        .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
    if schema
        .fields
        .iter()
        .any(|candidate| candidate.name == field)
    {
        Ok(())
    } else {
        Err(EcsError::UnknownField {
            component: component.to_string(),
            field: field.to_string(),
        })
    }
}

pub(super) fn validate_plan_shape(plan: &PhysicalPlan) -> Result<()> {
    if plan.version != 0 && plan.version != BRIDGE_PLAN_VERSION {
        return Err(EcsError::InvalidPlan(format!(
            "unsupported physical plan version {}",
            plan.version
        )));
    }
    if plan.actions.is_empty() {
        return Err(EcsError::InvalidPlan("plan has no actions".to_string()));
    }
    if plan.root_action >= plan.actions.len() {
        return Err(EcsError::InvalidPlan(
            "root action index is invalid".to_string(),
        ));
    }
    for action in &plan.actions {
        match action {
            ActionNode::Noop => {}
            ActionNode::SetField { target, value } => {
                validate_expr_index(plan, *target)?;
                validate_expr_index(plan, *value)?;
            }
            ActionNode::Sequence(children) | ActionNode::Parallel(children) => {
                for child in children {
                    validate_action_index(plan, *child)?;
                }
            }
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => {
                validate_expr_index(plan, *condition)?;
                validate_action_index(plan, *then_action)?;
                if let Some(action) = otherwise_action {
                    validate_action_index(plan, *action)?;
                }
            }
            ActionNode::ForEach { source, action, .. } => {
                validate_expr_index(plan, *source)?;
                validate_action_index(plan, *action)?;
            }
            ActionNode::EmitEvent { value, .. } => validate_expr_index(plan, *value)?,
            ActionNode::AddComponent { value, .. } => {
                if let Some(value) = value {
                    validate_expr_index(plan, *value)?;
                }
            }
            ActionNode::RemoveComponent { .. }
            | ActionNode::AddTag { .. }
            | ActionNode::RemoveTag { .. }
            | ActionNode::Despawn { .. } => {}
            ActionNode::CanvasCommand(command) => {
                if command.command.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "canvas command name cannot be empty".to_string(),
                    ));
                }
                for arg in &command.args {
                    validate_expr_index(plan, *arg)?;
                }
            }
            ActionNode::Udf {
                descriptor, args, ..
            } => {
                if descriptor.is_empty() {
                    return Err(EcsError::InvalidPlan(
                        "UDF descriptor cannot be empty".to_string(),
                    ));
                }
                for arg in args {
                    validate_expr_index(plan, *arg)?;
                }
            }
        }
    }
    for expr in &plan.expressions {
        match expr {
            ExprNode::Unary { input, .. } => validate_expr_index(plan, *input)?,
            ExprNode::Attribute { input, .. } => validate_expr_index(plan, *input)?,
            ExprNode::Binary { left, right, .. } => {
                validate_expr_index(plan, *left)?;
                validate_expr_index(plan, *right)?;
            }
            ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
                validate_expr_index(plan, *predicate)?;
            }
            ExprNode::Aggregate {
                relation,
                value,
                default,
                ..
            } => {
                validate_expr_index(plan, *relation)?;
                if let Some(value) = value {
                    validate_expr_index(plan, *value)?;
                }
                if let Some(default) = default {
                    validate_expr_index(plan, *default)?;
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                validate_spatial_relation_expr_indexes(plan, relation)?;
            }
            ExprNode::SpatialAggregate {
                relation,
                value,
                default,
                ..
            } => {
                validate_spatial_relation_expr_indexes(plan, relation)?;
                if let Some(value) = value {
                    validate_expr_index(plan, *value)?;
                }
                if let Some(default) = default {
                    validate_expr_index(plan, *default)?;
                }
            }
            _ => {}
        }
    }
    Ok(())
}

fn validate_expr_index(plan: &PhysicalPlan, index: usize) -> Result<()> {
    if index >= plan.expressions.len() {
        Err(EcsError::InvalidPlan(format!(
            "invalid expression index {index}"
        )))
    } else {
        Ok(())
    }
}

fn validate_spatial_relation_expr_indexes(
    plan: &PhysicalPlan,
    relation: &SpatialRelationNode,
) -> Result<()> {
    for index in relation
        .origin_position
        .iter()
        .chain(relation.target_position.iter())
    {
        validate_expr_index(plan, *index)?;
    }
    if let Some(radius) = relation.radius {
        validate_expr_index(plan, radius)?;
    }
    for bounds in relation
        .origin_bounds
        .iter()
        .chain(relation.target_bounds.iter())
    {
        for index in bounds.minimum.iter().chain(bounds.maximum.iter()) {
            validate_expr_index(plan, *index)?;
        }
    }
    if let Some(exact_filter) = relation.exact_filter {
        validate_expr_index(plan, exact_filter)?;
    }
    Ok(())
}

fn validate_action_index(plan: &PhysicalPlan, index: usize) -> Result<()> {
    if index >= plan.actions.len() {
        Err(EcsError::InvalidPlan(format!(
            "invalid action child {index}"
        )))
    } else {
        Ok(())
    }
}
