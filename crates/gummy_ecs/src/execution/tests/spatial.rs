use super::*;

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
            },
            BridgeQueryPayload {
                name: "item".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
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
fn spatial_aggregate_precomputes_pairwise_origin_item_expression() {
    let (mut world, first) = world_with_motion();
    world
        .set_field(first, "Position", "y", EcsValue::F64(0.0))
        .unwrap();
    add_motion_entity(&mut world, 3.0, 0.0, 2.0);
    add_motion_entity(&mut world, 5.0, 0.0, 4.0);
    add_motion_entity(&mut world, 20.0, 0.0, 8.0);
    let relation = SpatialRelationNode {
        id: "pressure_weighted_repel_x".to_string(),
        index_id: "position_neighbors_for_repel".to_string(),
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
    };
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
            },
            BridgeQueryPayload {
                name: "item".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
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
                query: "item".to_string(),
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
            ExprNode::Binary {
                op: "sub".to_string(),
                left: 0,
                right: 2,
            },
            ExprNode::Binary {
                op: "mul".to_string(),
                left: 6,
                right: 5,
            },
            ExprNode::SpatialAggregate {
                kind: "sum".to_string(),
                relation,
                value: Some(7),
                default: None,
            },
            ExprNode::Field {
                query: "origin".to_string(),
                component: "Velocity".to_string(),
                field: "dx".to_string(),
            },
        ],
        actions: vec![ActionNode::SetField {
            target: 9,
            value: 8,
        }],
        root_action: 0,
    };

    let handle = world.compile_bridge_plan_handle(payload).unwrap();
    let report = world
        .execute_compiled_plan_with_options(handle, false)
        .unwrap();

    assert_eq!(
        world.get_field(first, "Velocity", "dx").unwrap(),
        EcsValue::F64(-14.0)
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
                },
                BridgeQueryPayload {
                    name: "item".to_string(),
                    terms: vec![
                        QueryTerm::WithComponent("Position".to_string()),
                        QueryTerm::WithTag(tag.to_string()),
                    ],
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
fn releasing_compiled_plan_evicts_only_unowned_spatial_cache_entries() {
    let (mut world, _) = world_with_motion();
    add_motion_entity(&mut world, 1.0, 0.0, 0.0);
    add_motion_entity(&mut world, 20.0, 0.0, 0.0);
    let first_handle = world
        .compile_bridge_plan_handle(spatial_count_payload(&world))
        .unwrap();
    let second_handle = world
        .compile_bridge_plan_handle(spatial_count_payload(&world))
        .unwrap();

    world
        .execute_compiled_plan_with_options(first_handle, false)
        .unwrap();
    assert_eq!(world.spatial_index_cache_len(), 1);

    assert!(world.release_compiled_plan(first_handle));
    assert_eq!(world.spatial_index_cache_len(), 1);

    let report = world
        .execute_compiled_plan_with_options(second_handle, false)
        .unwrap();
    assert!(report.spatial_index_reuses >= 1);

    assert!(world.release_compiled_plan(second_handle));
    assert_eq!(world.spatial_index_cache_len(), 0);
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
