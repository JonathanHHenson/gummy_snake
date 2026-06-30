use std::collections::HashMap;

use crate::error::{EcsError, Result};
use crate::query::{QueryFilter, QueryTerm};
use crate::scheduler::{AccessKey, AccessSummary};
use crate::schema::SchemaRegistry;

pub const BRIDGE_PLAN_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhysicalQuery {
    pub name: String,
    pub filter: QueryFilter,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ExprNode {
    LiteralF64(f64),
    LiteralI64(i64),
    LiteralBool(bool),
    LiteralString(String),
    Field {
        query: String,
        component: String,
        field: String,
    },
    ResourceField {
        resource: String,
        field: String,
    },
    InputState {
        name: String,
        code: Option<i64>,
    },
    ForEachItem {
        slot: usize,
    },
    Unary {
        op: String,
        input: usize,
    },
    Binary {
        op: String,
        left: usize,
        right: usize,
    },
    ContextJoin {
        left_query: String,
        right_query: String,
        predicate: usize,
    },
    Exists {
        query: String,
        predicate: usize,
    },
    Aggregate {
        kind: String,
        relation: usize,
        group_query: Option<String>,
        value: Option<usize>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActionNode {
    Noop,
    SetField {
        target: usize,
        value: usize,
    },
    Sequence(Vec<usize>),
    Parallel(Vec<usize>),
    When {
        condition: usize,
        then_action: usize,
        otherwise_action: Option<usize>,
    },
    ForEach {
        source: usize,
        item_slot: usize,
        action: usize,
    },
    EmitEvent {
        event_type: String,
        value: usize,
    },
    Udf {
        descriptor: String,
        args: Vec<usize>,
        side_effects: bool,
    },
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct PhysicalPlan {
    pub version: u32,
    pub schema_fingerprint: u64,
    pub queries: Vec<PhysicalQuery>,
    pub expressions: Vec<ExprNode>,
    pub actions: Vec<ActionNode>,
    pub root_action: usize,
    pub access: AccessSummary,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BridgeQueryPayload {
    pub name: String,
    pub terms: Vec<QueryTerm>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BridgePlanPayload {
    pub version: u32,
    pub schema_fingerprint: Option<u64>,
    pub queries: Vec<BridgeQueryPayload>,
    pub expressions: Vec<ExprNode>,
    pub actions: Vec<ActionNode>,
    pub root_action: usize,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct PlanCache {
    compiled: HashMap<u64, PhysicalPlan>,
}

impl PlanCache {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&mut self, fingerprint: u64, plan: PhysicalPlan) -> Result<()> {
        validate_plan(&plan)?;
        self.compiled.insert(fingerprint, plan);
        Ok(())
    }

    pub fn get(&self, fingerprint: u64) -> Option<&PhysicalPlan> {
        self.compiled.get(&fingerprint)
    }

    pub fn len(&self) -> usize {
        self.compiled.len()
    }

    pub fn is_empty(&self) -> bool {
        self.compiled.is_empty()
    }
}

pub fn compile_bridge_plan(
    payload: BridgePlanPayload,
    schemas: &SchemaRegistry,
) -> Result<PhysicalPlan> {
    if payload.version != BRIDGE_PLAN_VERSION {
        return Err(EcsError::InvalidPlan(format!(
            "unsupported bridge plan version {}",
            payload.version
        )));
    }
    let schema_fingerprint = schemas.fingerprint();
    if let Some(expected) = payload.schema_fingerprint {
        if expected != schema_fingerprint {
            return Err(EcsError::InvalidPlan(
                "bridge plan schema fingerprint does not match world schema".to_string(),
            ));
        }
    }

    let mut query_names = HashMap::new();
    let mut queries = Vec::with_capacity(payload.queries.len());
    for query in payload.queries {
        if query.name.is_empty() {
            return Err(EcsError::InvalidPlan(
                "query name cannot be empty".to_string(),
            ));
        }
        if query_names.insert(query.name.clone(), ()).is_some() {
            return Err(EcsError::InvalidPlan(format!(
                "duplicate query name {}",
                query.name
            )));
        }
        validate_query_terms(&query.terms, schemas)?;
        queries.push(PhysicalQuery {
            name: query.name,
            filter: QueryFilter::new(query.terms),
        });
    }

    let plan = PhysicalPlan {
        version: payload.version,
        schema_fingerprint,
        queries,
        expressions: payload.expressions,
        actions: payload.actions,
        root_action: payload.root_action,
        access: AccessSummary::default(),
    };
    validate_plan_with_schemas(&plan, schemas)?;
    let mut plan = plan;
    plan.access = infer_access_summary(&plan)?;
    Ok(plan)
}

pub fn validate_plan(plan: &PhysicalPlan) -> Result<()> {
    validate_plan_shape(plan)
}

pub fn validate_plan_with_schemas(plan: &PhysicalPlan, schemas: &SchemaRegistry) -> Result<()> {
    validate_plan_shape(plan)?;
    let query_names = plan
        .queries
        .iter()
        .map(|query| query.name.as_str())
        .collect::<std::collections::BTreeSet<_>>();
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
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    if !query_names.contains(query.as_str()) {
                        return Err(EcsError::InvalidPlan(format!(
                            "unknown group query {query} in aggregate"
                        )));
                    }
                }
            }
            _ => {}
        }
    }
    Ok(())
}

pub fn infer_access_summary(plan: &PhysicalPlan) -> Result<AccessSummary> {
    validate_plan_shape(plan)?;
    let mut access = AccessSummary::default();
    collect_action_access(plan, plan.root_action, &mut access)?;
    Ok(access)
}

fn validate_query_terms(terms: &[QueryTerm], schemas: &SchemaRegistry) -> Result<()> {
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

fn validate_plan_shape(plan: &PhysicalPlan) -> Result<()> {
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
            ExprNode::Binary { left, right, .. } => {
                validate_expr_index(plan, *left)?;
                validate_expr_index(plan, *right)?;
            }
            ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
                validate_expr_index(plan, *predicate)?;
            }
            ExprNode::Aggregate {
                relation, value, ..
            } => {
                validate_expr_index(plan, *relation)?;
                if let Some(value) = value {
                    validate_expr_index(plan, *value)?;
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

fn validate_action_index(plan: &PhysicalPlan, index: usize) -> Result<()> {
    if index >= plan.actions.len() {
        Err(EcsError::InvalidPlan(format!(
            "invalid action child {index}"
        )))
    } else {
        Ok(())
    }
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
        ExprNode::Binary { left, right, .. } => {
            collect_expr_reads(plan, *left, access)?;
            collect_expr_reads(plan, *right, access)?;
        }
        ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
            collect_expr_reads(plan, *predicate, access)?;
        }
        ExprNode::Aggregate {
            relation, value, ..
        } => {
            collect_expr_reads(plan, *relation, access)?;
            if let Some(value) = value {
                collect_expr_reads(plan, *value, access)?;
            }
        }
        ExprNode::InputState { name, .. } => {
            access
                .reads
                .insert(AccessKey::Hidden(format!("input:{name}")));
        }
        ExprNode::LiteralF64(_)
        | ExprNode::LiteralI64(_)
        | ExprNode::LiteralBool(_)
        | ExprNode::LiteralString(_)
        | ExprNode::ForEachItem { .. } => {}
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{ComponentSchema, FieldSchema, StorageType};

    fn schemas() -> SchemaRegistry {
        let mut schemas = SchemaRegistry::new();
        schemas
            .register(ComponentSchema::new(
                "Position",
                vec![
                    FieldSchema::new("x", StorageType::Float64),
                    FieldSchema::new("y", StorageType::Float64),
                ],
            ))
            .unwrap();
        schemas
            .register(ComponentSchema::new(
                "Velocity",
                vec![FieldSchema::new("dx", StorageType::Float64)],
            ))
            .unwrap();
        schemas
            .register(ComponentSchema::new(
                "Clock",
                vec![FieldSchema::new("dt", StorageType::Float64)],
            ))
            .unwrap();
        schemas
    }

    #[test]
    fn plan_cache_validates_and_stores_plans() {
        let plan = PhysicalPlan {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: 0,
            queries: Vec::new(),
            expressions: vec![ExprNode::LiteralF64(1.0)],
            actions: vec![ActionNode::Noop],
            root_action: 0,
            access: AccessSummary::default(),
        };
        let mut cache = PlanCache::new();
        cache.insert(1, plan).unwrap();
        assert_eq!(cache.len(), 1);
    }

    #[test]
    fn bridge_plan_compiler_validates_schema_and_infers_access() {
        let schemas = schemas();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(schemas.fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithTag("Hero".to_string()),
                ],
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::ResourceField {
                    resource: "Clock".to_string(),
                    field: "dt".to_string(),
                },
                ExprNode::Binary {
                    op: "+".to_string(),
                    left: 0,
                    right: 1,
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 0,
                value: 2,
            }],
            root_action: 0,
        };
        let plan = compile_bridge_plan(payload, &schemas).unwrap();
        assert_eq!(plan.queries.len(), 1);
        assert!(plan
            .access
            .reads
            .contains(&AccessKey::Resource("Clock".to_string())));
        assert!(plan
            .access
            .writes
            .contains(&AccessKey::Component("Position".to_string())));
    }

    #[test]
    fn bridge_plan_compiler_rejects_invalid_schema_fingerprint() {
        let schemas = schemas();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(123),
            queries: Vec::new(),
            expressions: vec![ExprNode::LiteralBool(true)],
            actions: vec![ActionNode::Noop],
            root_action: 0,
        };
        assert!(matches!(
            compile_bridge_plan(payload, &schemas),
            Err(EcsError::InvalidPlan(_))
        ));
    }

    #[test]
    fn action_tree_supports_conditionals_for_each_udfs_and_events() {
        let plan = PhysicalPlan {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: 0,
            queries: Vec::new(),
            expressions: vec![
                ExprNode::LiteralBool(true),
                ExprNode::LiteralI64(1),
                ExprNode::ForEachItem { slot: 0 },
            ],
            actions: vec![
                ActionNode::EmitEvent {
                    event_type: "Ping".to_string(),
                    value: 1,
                },
                ActionNode::Udf {
                    descriptor: "weather".to_string(),
                    args: vec![2],
                    side_effects: true,
                },
                ActionNode::ForEach {
                    source: 1,
                    item_slot: 0,
                    action: 1,
                },
                ActionNode::When {
                    condition: 0,
                    then_action: 0,
                    otherwise_action: Some(2),
                },
            ],
            root_action: 3,
            access: AccessSummary::default(),
        };
        validate_plan(&plan).unwrap();
        let access = infer_access_summary(&plan).unwrap();
        assert!(access
            .writes
            .contains(&AccessKey::Event("Ping".to_string())));
        assert!(access.structural);
    }
}
