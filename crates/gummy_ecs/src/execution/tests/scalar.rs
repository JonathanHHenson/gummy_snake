use super::*;
use crate::plan::CanvasCommandNode;

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
fn row_local_canvas_compacts_fill_records_with_stable_order_and_conversions() {
    let (mut world, first) = world_with_motion();
    let second = add_motion_entity(&mut world, 10.0, 20.0, 0.0);
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
            ExprNode::LiteralF64(12.4),
            ExprNode::LiteralF64(100.6),
            ExprNode::LiteralF64(260.0),
            ExprNode::LiteralF64(-3.0),
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
            ExprNode::LiteralF64(4.0),
            ExprNode::LiteralF64(5.0),
            ExprNode::LiteralF64(6.0),
        ],
        actions: vec![
            ActionNode::CanvasCommand(CanvasCommandNode {
                command: "fill".to_string(),
                args: vec![0, 1, 2, 3],
            }),
            ActionNode::CanvasCommand(CanvasCommandNode {
                command: "no_stroke".to_string(),
                args: Vec::new(),
            }),
            ActionNode::CanvasCommand(CanvasCommandNode {
                command: "rect".to_string(),
                args: vec![4, 5, 6, 7],
            }),
            ActionNode::CanvasCommand(CanvasCommandNode {
                command: "circle".to_string(),
                args: vec![4, 5, 8],
            }),
            ActionNode::Sequence(vec![0, 1, 2, 3]),
        ],
        root_action: 4,
    };

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(report.rows_scanned, 4);
    assert_eq!(
        report.canvas_commands,
        vec![
            ExecutionCanvasCommand {
                command: "fill".to_string(),
                args: vec![
                    EcsValue::F64(12.4),
                    EcsValue::F64(100.6),
                    EcsValue::F64(260.0),
                    EcsValue::F64(-3.0),
                ],
            },
            ExecutionCanvasCommand {
                command: "no_stroke".to_string(),
                args: Vec::new(),
            },
        ]
    );
    assert_eq!(
        report.canvas_fill_batches,
        vec![ExecutionCanvasFillBatch {
            records: vec![
                ExecutionCanvasFillRecord {
                    kind: 1,
                    a: 2.0,
                    b: 0.0,
                    c: 4.0,
                    d: 5.0,
                    e: 0.0,
                    f: 0.0,
                    r: 12,
                    g: 101,
                    blue: 255,
                    alpha: 0,
                },
                ExecutionCanvasFillRecord {
                    kind: 1,
                    a: 10.0,
                    b: 20.0,
                    c: 4.0,
                    d: 5.0,
                    e: 0.0,
                    f: 0.0,
                    r: 12,
                    g: 101,
                    blue: 255,
                    alpha: 0,
                },
                ExecutionCanvasFillRecord {
                    kind: 3,
                    a: -1.0,
                    b: -3.0,
                    c: 6.0,
                    d: 6.0,
                    e: 0.0,
                    f: 0.0,
                    r: 12,
                    g: 101,
                    blue: 255,
                    alpha: 0,
                },
                ExecutionCanvasFillRecord {
                    kind: 3,
                    a: 7.0,
                    b: 17.0,
                    c: 6.0,
                    d: 6.0,
                    e: 0.0,
                    f: 0.0,
                    r: 12,
                    g: 101,
                    blue: 255,
                    alpha: 0,
                },
            ],
        }]
    );

    assert_eq!(
        world.get_field(first, "Position", "x").unwrap(),
        EcsValue::F64(2.0)
    );
    assert_eq!(
        world.get_field(second, "Position", "x").unwrap(),
        EcsValue::F64(10.0)
    );
}

#[test]
fn physical_integer_arithmetic_is_exact_and_target_overflow_is_checked() {
    let mut world = World::new();
    world
        .register_schema(ComponentSchema::new(
            "Exact",
            vec![FieldSchema::new("value", StorageType::Int64)],
        ))
        .unwrap();
    world
        .register_schema(ComponentSchema::new(
            "Narrow",
            vec![FieldSchema::new("value", StorageType::Int8)],
        ))
        .unwrap();
    let entity = world
        .spawn_with_defaults(["Exact".to_string(), "Narrow".to_string()])
        .unwrap();
    world
        .set_field(
            entity,
            "Exact",
            "value",
            EcsValue::I64(9_007_199_254_740_993),
        )
        .unwrap();
    world
        .set_field(entity, "Narrow", "value", EcsValue::I64(127))
        .unwrap();
    let query = BridgeQueryPayload {
        name: "entity".to_string(),
        terms: vec![
            QueryTerm::WithComponent("Exact".to_string()),
            QueryTerm::WithComponent("Narrow".to_string()),
        ],
        allowed_entities: None,
    };
    let exact_payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![query.clone()],
        expressions: vec![
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Exact".to_string(),
                field: "value".to_string(),
            },
            ExprNode::LiteralI64(2),
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
    world.execute_bridge_plan(exact_payload).unwrap();
    assert_eq!(
        world.get_field(entity, "Exact", "value").unwrap(),
        EcsValue::I64(9_007_199_254_740_995)
    );

    let overflow_payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![query],
        expressions: vec![
            ExprNode::Field {
                query: "entity".to_string(),
                component: "Narrow".to_string(),
                field: "value".to_string(),
            },
            ExprNode::LiteralI64(2),
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
    assert!(world.execute_bridge_plan(overflow_payload).is_err());
    assert_eq!(
        world.get_field(entity, "Narrow", "value").unwrap(),
        EcsValue::I64(127)
    );
}
