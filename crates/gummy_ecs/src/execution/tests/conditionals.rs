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
