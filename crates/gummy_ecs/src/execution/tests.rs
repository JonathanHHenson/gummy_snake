use super::*;
use crate::plan::{BridgeQueryPayload, BRIDGE_PLAN_VERSION};
use crate::query::QueryTerm;
use crate::schema::{ComponentSchema, FieldSchema};

fn world_with_motion() -> (World, Entity) {
    let mut world = World::new();
    world
        .register_schema(ComponentSchema::new(
            "Position",
            vec![
                FieldSchema::new("x", StorageType::Float64),
                FieldSchema::new("y", StorageType::Float64),
            ],
        ))
        .unwrap();
    world
        .register_schema(ComponentSchema::new(
            "Velocity",
            vec![FieldSchema::new("dx", StorageType::Float64)],
        ))
        .unwrap();
    world
        .register_schema(ComponentSchema::new(
            "Clock",
            vec![FieldSchema::new("tick", StorageType::Int64)],
        ))
        .unwrap();
    let entity = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    world
        .set_field(entity, "Position", "x", EcsValue::F64(2.0))
        .unwrap();
    world
        .set_field(entity, "Velocity", "dx", EcsValue::F64(3.0))
        .unwrap();
    (world, entity)
}

fn add_motion_entity(world: &mut World, x: f64, y: f64, dx: f64) -> Entity {
    let entity = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    world
        .set_field(entity, "Position", "x", EcsValue::F64(x))
        .unwrap();
    world
        .set_field(entity, "Position", "y", EcsValue::F64(y))
        .unwrap();
    world
        .set_field(entity, "Velocity", "dx", EcsValue::F64(dx))
        .unwrap();
    entity
}

fn spatial_count_payload(world: &World) -> BridgePlanPayload {
    BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![BridgeQueryPayload {
            name: "entity".to_string(),
            terms: vec![
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::WithComponent("Velocity".to_string()),
            ],
            allowed_entities: None,
        }],
        expressions: vec![
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Position".to_string(),
                field: "x".to_string(),
            },
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Position".to_string(),
                field: "y".to_string(),
            },
            ExprNode::LiteralF64(2.5),
            ExprNode::SpatialAggregate {
                kind: "count".to_string(),
                relation: SpatialRelationNode {
                    id: "nearby".to_string(),
                    index_id: "position_neighbors".to_string(),
                    origin_query: "entity".to_string(),
                    item_query: "entity".to_string(),
                    origin_position: vec![0, 1],
                    target_position: vec![0, 1],
                    radius: Some(2),
                    origin_bounds: None,
                    target_bounds: None,
                    algorithm: crate::plan::SpatialAlgorithmNode {
                        kind: "hash_grid".to_string(),
                        dimensions: 2,
                        cell_size: Some(4.0),
                        bounds: None,
                        capacity: None,
                        bits: None,
                    },
                    include_self: false,
                    pair_policy: "all".to_string(),
                    exact_filter: None,
                },
                value: None,
                default: None,
            },
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
        ],
        actions: vec![ActionNode::SetField {
            target: 4,
            value: 3,
        }],
        root_action: 0,
    }
}

fn spatial_parallel_count_payload(world: &World) -> BridgePlanPayload {
    let mut payload = spatial_count_payload(world);
    payload.actions = vec![
        ActionNode::SetField {
            target: 4,
            value: 3,
        },
        ActionNode::SetField {
            target: 0,
            value: 3,
        },
        ActionNode::Parallel(vec![0, 1]),
    ];
    payload.root_action = 2;
    payload
}

mod conditionals;
mod scalar;
mod spatial;
