use super::*;

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
