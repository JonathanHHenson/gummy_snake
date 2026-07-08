use std::collections::{HashMap, HashSet};

use crate::error::Result;
use crate::plan::{ActionNode, ExprNode, PhysicalPlan, SpatialRelationNode};
use crate::schema::StorageType;
use crate::world::World;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub(in crate::execution) struct F64WriteTarget {
    pub(in crate::execution) query: String,
    pub(in crate::execution) component: String,
    pub(in crate::execution) field: String,
}

#[derive(Clone, Debug, Default)]
pub(in crate::execution) struct QueryAccessSummary {
    pub(in crate::execution) component_reads: HashMap<String, Vec<String>>,
    pub(in crate::execution) component_writes: HashMap<String, Vec<String>>,
    pub(in crate::execution) resource_reads: HashSet<String>,
    pub(in crate::execution) resource_writes: HashSet<String>,
    pub(in crate::execution) event_reads: HashSet<String>,
    pub(in crate::execution) event_writes: HashSet<String>,
    pub(in crate::execution) hidden_reads: HashSet<String>,
    pub(in crate::execution) hidden_writes: HashSet<String>,
    pub(in crate::execution) structural: bool,
    pub(in crate::execution) f64_write_targets: Vec<F64WriteTarget>,
    pub(in crate::execution) copyback_eligible: bool,
}

fn add_query_access(map: &mut HashMap<String, Vec<String>>, component: &str, query: &str) {
    let queries = map.entry(component.to_string()).or_default();
    if !queries.iter().any(|candidate| candidate == query) {
        queries.push(query.to_string());
    }
}

pub(in crate::execution) fn collect_action_query_access(
    world: &World,
    plan: &PhysicalPlan,
    action_index: usize,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    match &plan.actions[action_index] {
        ActionNode::Noop => {}
        ActionNode::SetField { target, value } => {
            collect_expr_query_reads(plan, *value, access)?;
            match &plan.expressions[*target] {
                ExprNode::Field {
                    query,
                    component,
                    field,
                } => {
                    add_query_access(&mut access.component_writes, component, query);
                    if matches!(
                        world.storage_type_for_field(component, field)?,
                        StorageType::Float32 | StorageType::Float64
                    ) {
                        access.f64_write_targets.push(F64WriteTarget {
                            query: query.clone(),
                            component: component.clone(),
                            field: field.clone(),
                        });
                    } else {
                        access.copyback_eligible = false;
                    }
                }
                ExprNode::ResourceField { resource, .. } => {
                    access.resource_writes.insert(resource.clone());
                    access.copyback_eligible = false;
                }
                _ => access.copyback_eligible = false,
            }
        }
        ActionNode::Sequence(children) | ActionNode::Parallel(children) => {
            for child in children {
                collect_action_query_access(world, plan, *child, access)?;
            }
        }
        ActionNode::When {
            condition,
            then_action,
            otherwise_action,
        } => {
            collect_expr_query_reads(plan, *condition, access)?;
            collect_action_query_access(world, plan, *then_action, access)?;
            if let Some(otherwise_action) = otherwise_action {
                collect_action_query_access(world, plan, *otherwise_action, access)?;
            }
        }
        ActionNode::ForEach { source, action, .. } => {
            collect_expr_query_reads(plan, *source, access)?;
            collect_action_query_access(world, plan, *action, access)?;
        }
        ActionNode::EmitEvent { event_type, value } => {
            collect_expr_query_reads(plan, *value, access)?;
            access.event_writes.insert(event_type.clone());
            access.copyback_eligible = false;
        }
        ActionNode::AddComponent {
            component, value, ..
        } => {
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            access
                .component_writes
                .entry(component.clone())
                .or_default();
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::RemoveComponent { component, .. } => {
            access
                .component_writes
                .entry(component.clone())
                .or_default();
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::AddTag { tag, .. } | ActionNode::RemoveTag { tag, .. } => {
            access.hidden_writes.insert(format!("tag:{tag}"));
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::Despawn { .. } => {
            access.structural = true;
            access.copyback_eligible = false;
        }
        ActionNode::CanvasCommand(command) => {
            for arg in &command.args {
                collect_expr_query_reads(plan, *arg, access)?;
            }
            access.hidden_writes.insert("canvas".to_string());
            access.copyback_eligible = false;
        }
        ActionNode::Udf {
            descriptor,
            args,
            side_effects,
        } => {
            for arg in args {
                collect_expr_query_reads(plan, *arg, access)?;
            }
            access.hidden_reads.insert(format!("udf:{descriptor}"));
            if *side_effects {
                access.structural = true;
            }
            access.copyback_eligible = false;
        }
    }
    Ok(())
}

fn collect_spatial_relation_query_reads(
    plan: &PhysicalPlan,
    relation: &SpatialRelationNode,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    access
        .hidden_reads
        .insert(format!("spatial:{}", relation.index_id));
    for index in relation
        .origin_position
        .iter()
        .chain(relation.target_position.iter())
    {
        collect_expr_query_reads(plan, *index, access)?;
    }
    if let Some(radius) = relation.radius {
        collect_expr_query_reads(plan, radius, access)?;
    }
    for bounds in relation
        .origin_bounds
        .iter()
        .chain(relation.target_bounds.iter())
    {
        for index in bounds.minimum.iter().chain(bounds.maximum.iter()) {
            collect_expr_query_reads(plan, *index, access)?;
        }
    }
    if let Some(exact_filter) = relation.exact_filter {
        collect_expr_query_reads(plan, exact_filter, access)?;
    }
    Ok(())
}

fn collect_expr_query_reads(
    plan: &PhysicalPlan,
    expr_index: usize,
    access: &mut QueryAccessSummary,
) -> Result<()> {
    match &plan.expressions[expr_index] {
        ExprNode::Field {
            query, component, ..
        } => add_query_access(&mut access.component_reads, component, query),
        ExprNode::ResourceField { resource, .. } => {
            access.resource_reads.insert(resource.clone());
        }
        ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
            collect_expr_query_reads(plan, *input, access)?;
        }
        ExprNode::Binary { left, right, .. } => {
            collect_expr_query_reads(plan, *left, access)?;
            collect_expr_query_reads(plan, *right, access)?;
        }
        ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
            collect_expr_query_reads(plan, *predicate, access)?;
        }
        ExprNode::Aggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_expr_query_reads(plan, *relation, access)?;
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_query_reads(plan, *default, access)?;
            }
        }
        ExprNode::InputState { name, .. } => {
            access.hidden_reads.insert(format!("input:{name}"));
        }
        ExprNode::EventStream { event_type } => {
            access.event_reads.insert(event_type.clone());
        }
        ExprNode::SpatialMetadata { relation, .. } => {
            collect_spatial_relation_query_reads(plan, relation, access)?;
        }
        ExprNode::SpatialAggregate {
            relation,
            value,
            default,
            ..
        } => {
            collect_spatial_relation_query_reads(plan, relation, access)?;
            if let Some(value) = value {
                collect_expr_query_reads(plan, *value, access)?;
            }
            if let Some(default) = default {
                collect_expr_query_reads(plan, *default, access)?;
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

fn sets_intersect(left: &HashSet<String>, right: &HashSet<String>) -> bool {
    left.iter().any(|value| right.contains(value))
}

fn query_sets_disjoint(
    left_plan: usize,
    left_queries: &[String],
    right_plan: usize,
    right_queries: &[String],
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    if left_queries.is_empty() || right_queries.is_empty() {
        return false;
    }
    for left_query in left_queries {
        let Some(left_rows) = query_sets.get(&(left_plan, left_query.clone())) else {
            return false;
        };
        for right_query in right_queries {
            let Some(right_rows) = query_sets.get(&(right_plan, right_query.clone())) else {
                return false;
            };
            if left_rows.iter().any(|entity| right_rows.contains(entity)) {
                return false;
            }
        }
    }
    true
}

fn component_query_access_conflicts(
    writer: &HashMap<String, Vec<String>>,
    reader: &HashMap<String, Vec<String>>,
    writer_plan: usize,
    reader_plan: usize,
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    for (component, write_queries) in writer {
        if let Some(read_queries) = reader.get(component) {
            if !query_sets_disjoint(
                writer_plan,
                write_queries,
                reader_plan,
                read_queries,
                query_sets,
            ) {
                return true;
            }
        }
    }
    false
}

pub(in crate::execution) fn query_access_conflicts(
    left: &QueryAccessSummary,
    left_index: usize,
    right: &QueryAccessSummary,
    right_index: usize,
    query_sets: &HashMap<(usize, String), HashSet<u64>>,
) -> bool {
    if left.structural || right.structural {
        return true;
    }
    if sets_intersect(&left.resource_writes, &right.resource_writes)
        || sets_intersect(&left.resource_writes, &right.resource_reads)
        || sets_intersect(&right.resource_writes, &left.resource_reads)
        || sets_intersect(&left.event_writes, &right.event_writes)
        || sets_intersect(&left.event_writes, &right.event_reads)
        || sets_intersect(&right.event_writes, &left.event_reads)
        || sets_intersect(&left.hidden_writes, &right.hidden_writes)
        || sets_intersect(&left.hidden_writes, &right.hidden_reads)
        || sets_intersect(&right.hidden_writes, &left.hidden_reads)
    {
        return true;
    }
    component_query_access_conflicts(
        &left.component_writes,
        &right.component_writes,
        left_index,
        right_index,
        query_sets,
    ) || component_query_access_conflicts(
        &left.component_writes,
        &right.component_reads,
        left_index,
        right_index,
        query_sets,
    ) || component_query_access_conflicts(
        &right.component_writes,
        &left.component_reads,
        right_index,
        left_index,
        query_sets,
    )
}
