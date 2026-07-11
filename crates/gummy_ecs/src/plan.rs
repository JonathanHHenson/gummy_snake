use std::collections::HashMap;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::query::{QueryFilter, QueryTerm};
use crate::scheduler::AccessSummary;
use crate::schema::SchemaRegistry;

pub const BRIDGE_PLAN_VERSION: u32 = 2;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhysicalQuery {
    pub name: String,
    pub filter: QueryFilter,
    pub allowed_entities: Option<Vec<Entity>>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialBoundsExprNode {
    pub minimum: Vec<usize>,
    pub maximum: Vec<usize>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialAlgorithmNode {
    pub kind: String,
    pub dimensions: u8,
    pub cell_size: Option<f64>,
    pub bounds: Option<Vec<f64>>,
    pub capacity: Option<usize>,
    pub bits: Option<u8>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialRelationNode {
    pub id: String,
    pub index_id: String,
    pub origin_query: String,
    pub item_query: String,
    pub origin_position: Vec<usize>,
    pub target_position: Vec<usize>,
    pub radius: Option<usize>,
    pub origin_bounds: Option<SpatialBoundsExprNode>,
    pub target_bounds: Option<SpatialBoundsExprNode>,
    pub algorithm: SpatialAlgorithmNode,
    pub include_self: bool,
    pub pair_policy: String,
    pub exact_filter: Option<usize>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ExprNode {
    LiteralF64(f64),
    LiteralI64(i64),
    LiteralBool(bool),
    LiteralString(String),
    LiteralValue(EcsValue),
    Field {
        query: String,
        component: String,
        field: String,
    },
    ResourceField {
        resource: String,
        field: String,
    },
    Attribute {
        input: usize,
        attribute: String,
    },
    EventStream {
        event_type: String,
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
        default: Option<usize>,
    },
    SpatialMetadata {
        relation: SpatialRelationNode,
        kind: String,
        axis: Option<usize>,
    },
    SpatialAggregate {
        kind: String,
        relation: SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanvasCommandNode {
    pub command: String,
    pub args: Vec<usize>,
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
    AddComponent {
        query: String,
        component: String,
        value: Option<usize>,
    },
    RemoveComponent {
        query: String,
        component: String,
    },
    AddTag {
        query: String,
        tag: String,
    },
    RemoveTag {
        query: String,
        tag: String,
    },
    Despawn {
        query: String,
    },
    CanvasCommand(CanvasCommandNode),
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
    pub allowed_entities: Option<Vec<Entity>>,
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

pub type PhysicalPlanHandle = u64;

mod access;
mod cache;
mod optimizer;
pub(crate) mod typed_ir;
mod validation;

pub use access::infer_access_summary;
pub use cache::PlanCache;
use optimizer::{optimize_bridge_payload, optimize_physical_plan};
use validation::validate_query_terms;
pub use validation::{validate_plan, validate_plan_with_schemas};

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
    let payload = optimize_bridge_payload(payload);
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
            allowed_entities: query.allowed_entities,
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
    let mut plan = optimize_physical_plan(plan)?;
    validate_plan_with_schemas(&plan, schemas)?;
    plan.access = infer_access_summary(&plan)?;
    Ok(plan)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::AccessKey;
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
        let handle = cache.insert(plan).unwrap();
        assert_eq!(handle, 1);
        assert_eq!(cache.len(), 1);
        assert!(cache.get(handle).is_some());
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
                allowed_entities: None,
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
