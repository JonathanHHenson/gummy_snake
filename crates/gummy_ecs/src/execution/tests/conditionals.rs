use super::*;

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

#[test]
fn parallel_event_actions_copy_back_to_the_canonical_world_queue() {
    let (mut world, _) = world_with_motion();
    let payload = BridgePlanPayload {
        version: BRIDGE_PLAN_VERSION,
        schema_fingerprint: Some(world.schema_fingerprint()),
        queries: vec![],
        expressions: vec![ExprNode::LiteralI64(1), ExprNode::LiteralI64(2)],
        actions: vec![
            ActionNode::EmitEvent {
                event_type: "Ping".to_string(),
                value: 0,
            },
            ActionNode::EmitEvent {
                event_type: "Pong".to_string(),
                value: 1,
            },
            ActionNode::Parallel(vec![0, 1]),
        ],
        root_action: 2,
    };

    let report = world.execute_bridge_plan(payload).unwrap();

    assert_eq!(report.events_emitted, 2);
    assert_eq!(report.events.len(), 2);
    assert_eq!(world.diagnostics().events_emitted, 2);
    assert_eq!(
        world.read_events("Ping").unwrap()[0].payload,
        EcsValue::I64(1)
    );
    assert_eq!(
        world.read_events("Pong").unwrap()[0].payload,
        EcsValue::I64(2)
    );
}

#[test]
fn row_local_conditional_writes_match_report_writes_fallback_in_sequence_order() {
    fn payload(world: &World) -> BridgePlanPayload {
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
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::LiteralF64(0.0),
                ExprNode::Binary {
                    op: "gt".to_string(),
                    left: 0,
                    right: 2,
                },
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 0,
                    right: 1,
                },
            ],
            actions: vec![
                ActionNode::SetField {
                    target: 0,
                    value: 4,
                },
                ActionNode::SetField {
                    target: 1,
                    value: 0,
                },
                ActionNode::Sequence(vec![0, 1]),
                ActionNode::When {
                    condition: 3,
                    then_action: 2,
                    otherwise_action: None,
                },
            ],
            root_action: 3,
        }
    }

    let (mut fast_world, fast_entity) = world_with_motion();
    let fast_handle = fast_world
        .compile_bridge_plan_handle(payload(&fast_world))
        .unwrap();
    let fast_report = fast_world
        .execute_compiled_plan_with_options(fast_handle, false)
        .unwrap();

    assert_eq!(
        fast_world.get_field(fast_entity, "Position", "x").unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(
        fast_world.get_field(fast_entity, "Velocity", "dx").unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(fast_report.fields_written, 2);
    assert!(fast_report.writes.is_empty());

    let (mut fallback_world, fallback_entity) = world_with_motion();
    let fallback_handle = fallback_world
        .compile_bridge_plan_handle(payload(&fallback_world))
        .unwrap();
    let fallback_report = fallback_world
        .execute_compiled_plan_with_options(fallback_handle, true)
        .unwrap();

    assert_eq!(
        fallback_world
            .get_field(fallback_entity, "Position", "x")
            .unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(
        fallback_world
            .get_field(fallback_entity, "Velocity", "dx")
            .unwrap(),
        EcsValue::F64(5.0)
    );
    assert_eq!(fallback_report.fields_written, 2);
    assert_eq!(
        fallback_report.writes,
        vec![
            ExecutionWrite::ComponentField {
                entity: fallback_entity,
                component: "Position".to_string(),
                field: "x".to_string(),
                value: EcsValue::F64(5.0),
            },
            ExecutionWrite::ComponentField {
                entity: fallback_entity,
                component: "Velocity".to_string(),
                field: "dx".to_string(),
                value: EcsValue::F64(5.0),
            },
        ]
    );
}
