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

#[test]
fn physical_plan_executes_scalar_set_over_query_rows() {
    let (mut world, entity) = world_with_motion();
    let payload = BridgePlanPayload {
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
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
            ExprNode::Binary {
                op: "add".to_string(),
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

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(
        world.get_field(entity, "Position", "x").unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(report.fields_written, 1);
    assert_eq!(report.writes.len(), 1);
}

#[test]
fn physical_parallel_uses_snapshot_reads_and_stable_merge() {
    let (mut world, entity) = world_with_motion();
    let payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![BridgeQueryPayload {
            name: "entity".to_string(),
            terms: vec![QueryTerm::WithComponent("Position".to_string())],
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
            ExprNode::LiteralF64(5.0),
        ],
        actions: vec![
            ActionNode::SetField {
                target: 0,
                value: 2,
            },
            ActionNode::SetField {
                target: 1,
                value: 0,
            },
            ActionNode::Parallel(vec![0, 1]),
        ],
        root_action: 2,
    };

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(
        world.get_field(entity, "Position", "x").unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(
        world.get_field(entity, "Position", "y").unwrap(),
        EcsValue::F64(2.0)
    );
    assert_eq!(report.fields_written, 2);
    assert_eq!(report.duplicate_writes, 0);
}

#[test]
fn optimized_f64_executor_reads_resources_and_input_state() {
    let (mut world, entity) = world_with_motion();
    world
        .register_schema(ComponentSchema::new(
            "Wind",
            vec![FieldSchema::new("x", StorageType::Float64)],
        ))
        .unwrap();
    world.set_input_state("dt", None, EcsValue::F64(16.0));
    let mut wind = HashMap::new();
    wind.insert("x".to_string(), EcsValue::F64(2.0));
    world.insert_resource("Wind", wind).unwrap();
    let payload = BridgePlanPayload {
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
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
            ExprNode::ResourceField {
                resource: "Wind".to_string(),
                field: "x".to_string(),
            },
            ExprNode::Binary {
                op: "add".to_string(),
                left: 1,
                right: 2,
            },
            ExprNode::InputState {
                name: "dt".to_string(),
                code: None,
            },
            ExprNode::LiteralF64(1000.0),
            ExprNode::Binary {
                op: "truediv".to_string(),
                left: 4,
                right: 5,
            },
            ExprNode::Binary {
                op: "mul".to_string(),
                left: 3,
                right: 6,
            },
            ExprNode::Binary {
                op: "add".to_string(),
                left: 0,
                right: 7,
            },
        ],
        actions: vec![ActionNode::SetField {
            target: 0,
            value: 8,
        }],
        root_action: 0,
    };
    let handle = world.compile_bridge_plan_handle(payload).unwrap();

    let report = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();

    assert_eq!(
        world.get_field(entity, "Position", "x").unwrap(),
        EcsValue::F64(2.08)
    );
    assert_eq!(report.fields_written, 1);
    assert!(report.writes.is_empty());
}

#[test]
fn spatial_aggregate_precomputes_generic_exact_filter() {
    let (mut world, first) = world_with_motion();
    world
        .set_field(first, "Position", "y", EcsValue::F64(0.0))
        .unwrap();
    add_motion_entity(&mut world, 3.0, 0.0, 3.0);
    add_motion_entity(&mut world, 4.0, 0.0, 7.0);
    add_motion_entity(&mut world, 20.0, 0.0, 3.0);
    let payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![
            BridgeQueryPayload {
                name: "origin".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            },
            BridgeQueryPayload {
                name: "item".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            },
        ],
        expressions: vec![
            ExprNode::Field {
                query: "origin".to_string(),
                component: "Position".to_string(),
                field: "x".to_string(),
            },
            ExprNode::Field {
                query: "origin".to_string(),
                component: "Position".to_string(),
                field: "y".to_string(),
            },
            ExprNode::Field {
                query: "item".to_string(),
                component: "Position".to_string(),
                field: "x".to_string(),
            },
            ExprNode::Field {
                query: "item".to_string(),
                component: "Position".to_string(),
                field: "y".to_string(),
            },
            ExprNode::LiteralF64(5.0),
            ExprNode::Field {
                query: "origin".to_string(),
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
            ExprNode::Field {
                query: "item".to_string(),
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
            ExprNode::Binary {
                op: "eq".to_string(),
                left: 6,
                right: 5,
            },
            ExprNode::SpatialAggregate {
                kind: "count".to_string(),
                relation: SpatialRelationNode {
                    id: "same_velocity_neighbors".to_string(),
                    index_id: "same_velocity_position_neighbors".to_string(),
                    origin_query: "origin".to_string(),
                    item_query: "item".to_string(),
                    origin_position: vec![0, 1],
                    target_position: vec![2, 3],
                    radius: Some(4),
                    origin_bounds: None,
                    target_bounds: None,
                    algorithm: crate::plan::SpatialAlgorithmNode {
                        kind: "hash_grid".to_string(),
                        dimensions: 2,
                        cell_size: Some(8.0),
                        bounds: None,
                        capacity: None,
                        bits: None,
                    },
                    include_self: false,
                    pair_policy: "all".to_string(),
                    exact_filter: Some(7),
                },
                value: None,
                default: None,
            },
        ],
        actions: vec![ActionNode::SetField {
            target: 1,
            value: 8,
        }],
        root_action: 0,
    };

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(
        world.get_field(first, "Position", "y").unwrap(),
        EcsValue::F64(1.0)
    );
    assert!(report.spatial_exact_rows > 0);
}

#[test]
fn spatial_index_cache_distinguishes_same_named_relations_with_different_item_filters() {
    let (mut world, marker) = world_with_motion();
    world.add_tag(marker, "Marker").unwrap();
    world
        .set_field(marker, "Position", "x", EcsValue::F64(0.0))
        .unwrap();
    world
        .set_field(marker, "Position", "y", EcsValue::F64(0.0))
        .unwrap();
    let red_near = add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    let red_far = add_motion_entity(&mut world, 100.0, 0.0, 0.0);
    let blue_near_a = add_motion_entity(&mut world, 2.0, 0.0, 0.0);
    let blue_near_b = add_motion_entity(&mut world, 3.0, 0.0, 0.0);
    world.add_tag(red_near, "Red").unwrap();
    world.add_tag(red_far, "Red").unwrap();
    world.add_tag(blue_near_a, "Blue").unwrap();
    world.add_tag(blue_near_b, "Blue").unwrap();

    fn tagged_count_payload(world: &World, tag: &str) -> BridgePlanPayload {
        BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![
                BridgeQueryPayload {
                    name: "origin".to_string(),
                    terms: vec![
                        QueryTerm::WithComponent("Position".to_string()),
                        QueryTerm::WithComponent("Velocity".to_string()),
                        QueryTerm::WithTag("Marker".to_string()),
                    ],
                    allowed_entities: None,
                },
                BridgeQueryPayload {
                    name: "item".to_string(),
                    terms: vec![
                        QueryTerm::WithComponent("Position".to_string()),
                        QueryTerm::WithTag(tag.to_string()),
                    ],
                    allowed_entities: None,
                },
            ],
            expressions: vec![
                ExprNode::Field {
                    query: "origin".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "origin".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::Field {
                    query: "item".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "item".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::LiteralF64(5.0),
                ExprNode::SpatialAggregate {
                    kind: "count".to_string(),
                    relation: SpatialRelationNode {
                        id: "shared_named_neighbors".to_string(),
                        index_id: "shared_named_index".to_string(),
                        origin_query: "origin".to_string(),
                        item_query: "item".to_string(),
                        origin_position: vec![0, 1],
                        target_position: vec![2, 3],
                        radius: Some(4),
                        origin_bounds: None,
                        target_bounds: None,
                        algorithm: crate::plan::SpatialAlgorithmNode {
                            kind: "hash_grid".to_string(),
                            dimensions: 2,
                            cell_size: Some(8.0),
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
                    query: "origin".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 6,
                value: 5,
            }],
            root_action: 0,
        }
    }

    world
        .execute_bridge_plan(tagged_count_payload(&world, "Red"))
        .unwrap();
    assert_eq!(
        world.get_field(marker, "Velocity", "dx").unwrap(),
        EcsValue::F64(1.0)
    );

    world
        .execute_bridge_plan(tagged_count_payload(&world, "Blue"))
        .unwrap();
    assert_eq!(
        world.get_field(marker, "Velocity", "dx").unwrap(),
        EcsValue::F64(2.0)
    );
}

#[test]
fn spatial_index_cache_reuses_valid_snapshot_across_executions() {
    let (mut world, _) = world_with_motion();
    add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    add_motion_entity(&mut world, 20.0, 0.0, 0.0);
    let handle = world
        .compile_bridge_plan_handle(spatial_count_payload(&world))
        .unwrap();

    let first = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();
    assert_eq!(first.spatial_index_full_rebuilds, 1);
    assert_eq!(first.spatial_index_incremental_updates, 0);
    assert_eq!(world.spatial_index_cache_len(), 1);

    let second = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();
    assert_eq!(second.spatial_indexes_built, 0);
    assert_eq!(second.spatial_index_full_rebuilds, 0);
    assert_eq!(second.spatial_index_incremental_updates, 0);
    assert!(second.spatial_index_reuses >= 1);
    assert_eq!(world.spatial_index_cache_len(), 1);
}

#[test]
fn spatial_index_cache_persists_from_fused_parallel_collector() {
    let (mut world, _) = world_with_motion();
    add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    add_motion_entity(&mut world, 20.0, 0.0, 0.0);
    let handle = world
        .compile_bridge_plan_handle(spatial_parallel_count_payload(&world))
        .unwrap();

    let report = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();
    assert_eq!(report.spatial_index_full_rebuilds, 1);
    assert_eq!(world.spatial_index_cache_len(), 1);
}

#[test]
fn spatial_hash_grid_incrementally_updates_after_indexed_field_change() {
    let (mut world, entity) = world_with_motion();
    add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    add_motion_entity(&mut world, 20.0, 0.0, 0.0);
    let handle = world
        .compile_bridge_plan_handle(spatial_count_payload(&world))
        .unwrap();
    world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();

    world
        .set_field(entity, "Position", "x", EcsValue::F64(30.0))
        .unwrap();
    let report = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();
    assert_eq!(report.spatial_index_incremental_updates, 1);
    assert_eq!(report.spatial_index_full_rebuilds, 0);
    assert_eq!(world.spatial_index_cache_len(), 1);
}

#[test]
fn spatial_hash_grid_incrementally_updates_after_structural_churn() {
    let (mut world, _) = world_with_motion();
    add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    let removed = add_motion_entity(&mut world, 20.0, 0.0, 0.0);
    let handle = world
        .compile_bridge_plan_handle(spatial_count_payload(&world))
        .unwrap();
    world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();

    world.despawn(removed).unwrap();
    add_motion_entity(&mut world, 2.0, 0.0, 0.0);
    let report = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();
    assert_eq!(report.spatial_index_incremental_updates, 1);
    assert_eq!(report.spatial_index_full_rebuilds, 0);
    assert_eq!(world.spatial_index_cache_len(), 1);
}

#[test]
fn physical_plan_executes_conditionals_and_resources() {
    let (mut world, entity) = world_with_motion();
    let mut clock = HashMap::new();
    clock.insert("tick".to_string(), EcsValue::I64(1));
    world.insert_resource("Clock", clock).unwrap();
    let payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![BridgeQueryPayload {
            name: "entity".to_string(),
            terms: vec![QueryTerm::WithComponent("Position".to_string())],
            allowed_entities: None,
        }],
        expressions: vec![
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Position".to_string(),
                field: "x".to_string(),
            },
            ExprNode::LiteralF64(1.0),
            ExprNode::Binary {
                op: "gt".to_string(),
                left: 0,
                right: 1,
            },
            ExprNode::ResourceField {
                resource: "Clock".to_string(),
                field: "tick".to_string(),
            },
            ExprNode::LiteralI64(2),
            ExprNode::Binary {
                op: "add".to_string(),
                left: 3,
                right: 4,
            },
        ],
        actions: vec![
            ActionNode::SetField {
                target: 3,
                value: 5,
            },
            ActionNode::When {
                condition: 2,
                then_action: 0,
                otherwise_action: None,
            },
        ],
        root_action: 1,
    };

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(
        world.resource_field("Clock", "tick").unwrap(),
        EcsValue::I64(3)
    );
    assert_eq!(
        world.get_field(entity, "Position", "x").unwrap(),
        EcsValue::F64(2.0)
    );
    assert_eq!(report.resource_fields_written, 1);
}
