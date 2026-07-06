use crate::error::{EcsError, Result};
use crate::scheduler::{AccessKey, AccessSummary};

use super::validation::validate_plan_shape;
use super::{ActionNode, ExprNode, PhysicalPlan, SpatialRelationNode};

pub fn infer_access_summary(plan: &PhysicalPlan) -> Result<AccessSummary> {
    validate_plan_shape(plan)?;
    let mut access = AccessSummary::default();
    collect_action_access(plan, plan.root_action, &mut access)?;
    Ok(access)
}

fn collect_action_access(
    plan: &PhysicalPlan,
    action_index: usize,
    access: &mut AccessSummary,
) -> Result<()> {
    match &plan.actions[action_index] {
        ActionNode::Noop => {}
        ActionNode::SetField { target, value } => {
            collect_expr_reads(plan, *value, access)?;
            collect_write_target(plan, *target, access)?;
        }
        ActionNode::Sequence(children) | ActionNode::Parallel(children) => {
            for child in children {
                collect_action_access(plan, *child, access)?;
            }
        }
        ActionNode::When {
            condition,
            then_action,
            otherwise_action,
        } => {
            collect_expr_reads(plan, *condition, access)?;
            collect_action_access(plan, *then_action, access)?;
            if let Some(otherwise_action) = otherwise_action {
                collect_action_access(plan, *otherwise_action, access)?;
            }
        }
        ActionNode::ForEach { source, action, .. } => {
            collect_expr_reads(plan, *source, access)?;
            collect_action_access(plan, *action, access)?;
        }
        ActionNode::EmitEvent { event_type, value } => {
            collect_expr_reads(plan, *value, access)?;
            access.writes.insert(AccessKey::Event(event_type.clone()));
        }
        ActionNode::AddComponent {
            component, value, ..
        } => {
            if let Some(value) = value {
                collect_expr_reads(plan, *value, access)?;
            }
            access
                .writes
                .insert(AccessKey::Component(component.clone()));
            access.structural = true;
        }
        ActionNode::RemoveComponent { component, .. } => {
            access
                .writes
                .insert(AccessKey::Component(component.clone()));
            access.structural = true;
        }
        ActionNode::AddTag { tag, .. } | ActionNode::RemoveTag { tag, .. } => {
            access
                .writes
                .insert(AccessKey::Hidden(format!("tag:{tag}")));
            access.structural = true;
        }
        ActionNode::Despawn { .. } => {
            access.structural = true;
        }
        ActionNode::Udf {
            args,
            side_effects,
            descriptor,
        } => {
            for arg in args {
                collect_expr_reads(plan, *arg, access)?;
            }
            access
                .reads
                .insert(AccessKey::Hidden(format!("udf:{descriptor}")));
            if *side_effects {
                access.structural = true;
            }
        }
    }
    Ok(())
}

fn collect_write_target(
    plan: &PhysicalPlan,
    expr_index: usize,
    access: &mut AccessSummary,
) -> Result<()> {
    match &plan.expressions[expr_index] {
        ExprNode::Field { component, .. } => {
            access
                .writes
                .insert(AccessKey::Component(component.clone()));
            Ok(())
        }
        ExprNode::ResourceField { resource, .. } => {
            access.writes.insert(AccessKey::Resource(resource.clone()));
            Ok(())
        }
        other => Err(EcsError::InvalidPlan(format!(
            "set target must be a field or resource field, got {other:?}"
        ))),
    }
}

fn collect_spatial_relation_reads(
    plan: &PhysicalPlan,
    relation: &SpatialRelationNode,
    access: &mut AccessSummary,
) -> Result<()> {
    access
        .reads
        .insert(AccessKey::Hidden(format!("spatial:{}", relation.index_id)));
    for index in relation
        .origin_position
        .iter()
        .chain(relation.target_position.iter())
    {
        collect_expr_reads(plan, *index, access)?;
    }
    if let Some(radius) = relation.radius {
        collect_expr_reads(plan, radius, access)?;
    }
    for bounds in relation
        .origin_bounds
        .iter()
        .chain(relation.target_bounds.iter())
    {
        for index in bounds.minimum.iter().chain(bounds.maximum.iter()) {
            collect_expr_reads(plan, *index, access)?;
        }
    }
    if let Some(exact_filter) = relation.exact_filter {
        collect_expr_reads(plan, exact_filter, access)?;
    }
    Ok(())
}

fn collect_expr_reads(
    plan: &PhysicalPlan,
    expr_index: usize,
    access: &mut AccessSummary,
) -> Result<()> {
    match &plan.expressions[expr_index] {
        ExprNode::Field { component, .. } => {
            access.reads.insert(AccessKey::Component(component.clone()));
        }
        ExprNode::ResourceField { resource, .. } => {
            access.reads.insert(AccessKey::Resource(resource.clone()));
        }
        ExprNode::Unary { input, .. } => collect_expr_reads(plan, *input, access)?,
        ExprNode::Attribute { input, .. } => collect_expr_reads(plan, *input, access)?,
        ExprNode::Binary { left, right, .. } => {
            collect_expr_reads(plan, *left, access)?;
            collect_expr_reads(plan, *right, access)?;
        }
        ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
            collect_expr_reads(plan, *predicate, access)?;
        }
        ExprNode::Aggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_expr_reads(plan, *relation, access)?;
            if let Some(value) = value {
                collect_expr_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_reads(plan, *default, access)?;
            }
        }
        ExprNode::InputState { name, .. } => {
            access
                .reads
                .insert(AccessKey::Hidden(format!("input:{name}")));
        }
        ExprNode::EventStream { event_type } => {
            access.reads.insert(AccessKey::Event(event_type.clone()));
        }
        ExprNode::SpatialMetadata { relation, .. } => {
            collect_spatial_relation_reads(plan, relation, access)?;
        }
        ExprNode::SpatialAggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_spatial_relation_reads(plan, relation, access)?;
            if let Some(value) = value {
                collect_expr_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_reads(plan, *default, access)?;
            }
        }
        ExprNode::LiteralF64(_)
        | ExprNode::LiteralI64(_)
        | ExprNode::LiteralBool(_)
        | ExprNode::LiteralString(_)
        | ExprNode::LiteralValue(_)
        | ExprNode::ForEachItem { .. } => {}
    }
    Ok(())
}
