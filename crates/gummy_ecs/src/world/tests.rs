use super::World;
use crate::archetype::ComponentRow;
use crate::column::EcsValue;
use crate::entity::Entity;
use crate::query::{QueryFilter, QueryTerm};
use crate::schema::{ComponentSchema, FieldSchema, StorageType};

fn register_position_velocity(world: &mut World) {
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
}

#[test]
fn archetype_spawn_query_and_structural_moves_are_deterministic() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let first = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    let second = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world
        .set_field(first, "Position", "x", EcsValue::F64(12.0))
        .unwrap();

    assert_eq!(
        world.query(["Position".to_string()]).unwrap(),
        vec![first, second]
    );
    assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![first]);
    assert_eq!(
        world.get_field(first, "Position", "x").unwrap(),
        EcsValue::F64(12.0)
    );

    world.add_component_default(second, "Velocity").unwrap();
    assert_eq!(
        world.query(["Velocity".to_string()]).unwrap(),
        vec![first, second]
    );
    world.remove_component(first, "Velocity").unwrap();
    assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![second]);
}

#[test]
fn revisions_track_structural_and_field_mutations() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    assert_eq!(world.structural_revision(), 0);
    assert_eq!(world.field_revision(), 0);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    assert_eq!(world.structural_revision(), 1);
    world
        .set_field(entity, "Position", "x", EcsValue::F64(10.0))
        .unwrap();
    assert_eq!(world.field_revision(), 1);
    assert_eq!(world.component_field_revision("Position", "x"), 1);
    assert_eq!(world.component_field_revision("Position", "y"), 0);
    world.add_component_default(entity, "Velocity").unwrap();
    assert_eq!(world.structural_revision(), 2);
    world.remove_tag(entity, "missing").unwrap();
    assert_eq!(world.structural_revision(), 2);
    world.add_tag(entity, "mover").unwrap();
    assert_eq!(world.structural_revision(), 3);
}

#[test]
fn command_buffer_applies_in_submission_order() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.stage_add_component(entity, "Velocity");
    world.stage_remove_component(entity, "Velocity");
    world.apply_staged().unwrap();
    assert_eq!(
        world.entity_components(entity).unwrap(),
        vec!["Position".to_string()]
    );
    assert_eq!(world.diagnostics().staged_commands_applied, 2);
}

#[test]
fn cached_queries_are_invalidated_by_structural_changes() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    assert_eq!(
        world.query(["Velocity".to_string()]).unwrap(),
        Vec::<Entity>::new()
    );
    assert_eq!(
        world.query(["Velocity".to_string()]).unwrap(),
        Vec::<Entity>::new()
    );
    world.add_component_default(entity, "Velocity").unwrap();
    assert_eq!(world.query(["Velocity".to_string()]).unwrap(), vec![entity]);
    let diagnostics = world.diagnostics();
    assert!(diagnostics.query_cache_hits >= 1);
    assert!(diagnostics.query_cache_invalidations >= 1);
    assert!(diagnostics.query_matched_archetypes >= 1);
    assert!(diagnostics.query_matched_rows >= 1);
}

#[test]
fn filtered_queries_support_required_and_excluded_tags() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let hero = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let enemy = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    world.add_tag(hero, "Hero").unwrap();
    world.add_tag(enemy, "Enemy").unwrap();

    let heroes_without_velocity = world
        .query_filter(QueryFilter::new([
            QueryTerm::WithComponent("Position".to_string()),
            QueryTerm::WithTag("Hero".to_string()),
            QueryTerm::WithoutComponent("Velocity".to_string()),
            QueryTerm::WithoutTag("Enemy".to_string()),
        ]))
        .unwrap();
    assert_eq!(heroes_without_velocity, vec![hero]);
    assert_eq!(world.entity_tags(hero).unwrap(), vec!["Hero".to_string()]);
    assert_eq!(
        world
            .snapshot_query_filter(QueryFilter::default())
            .unwrap()
            .len(),
        2
    );
}

#[test]
fn swap_removal_repairs_the_moved_entity_location() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let first = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let removed = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let moved = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world
        .set_field(moved, "Position", "x", EcsValue::F64(3.0))
        .unwrap();

    world.despawn(removed).unwrap();

    assert_eq!(
        world.get_field(moved, "Position", "x").unwrap(),
        EcsValue::F64(3.0)
    );
    world
        .set_field(moved, "Position", "x", EcsValue::F64(30.0))
        .unwrap();
    assert_eq!(
        world.query(["Position".to_string()]).unwrap(),
        vec![first, moved]
    );
}

#[test]
fn clone_resets_derived_query_caches() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.query(["Position".to_string()]).unwrap();
    world.query(["Position".to_string()]).unwrap();
    let before_clone = world.diagnostics();
    assert_eq!(before_clone.query_cache_hits, 1);

    let mut cloned = world.clone();
    cloned.query(["Position".to_string()]).unwrap();
    let clone_diagnostics = cloned.diagnostics();
    assert_eq!(
        clone_diagnostics.query_cache_misses,
        before_clone.query_cache_misses + 1
    );
    assert_eq!(
        clone_diagnostics.query_cache_hits,
        before_clone.query_cache_hits
    );
}

#[test]
fn resources_and_events_are_owned_by_world() {
    let mut world = World::new();
    world
        .register_schema(ComponentSchema::new(
            "Clock",
            vec![FieldSchema::new("tick", StorageType::Int64)],
        ))
        .unwrap();
    let mut row = ComponentRow::new();
    row.insert("tick".to_string(), EcsValue::I64(1));
    world.insert_resource("Clock", row).unwrap();
    world
        .set_resource_field("Clock", "tick", EcsValue::I64(2))
        .unwrap();
    assert_eq!(
        world.resource_field("Clock", "tick").unwrap(),
        EcsValue::I64(2)
    );
    assert_eq!(world.resource_revision("Clock"), 2);

    world.set_frame(3);
    world.emit_event("Ping", EcsValue::I64(7)).unwrap();
    let events = world.read_events("Ping").unwrap();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0].payload, EcsValue::I64(7));
    let diagnostics = world.diagnostics();
    assert_eq!(diagnostics.event_queues_total, 1);
    assert_eq!(diagnostics.event_records_total, 1);
    assert_eq!(diagnostics.events_emitted, 1);
    assert_eq!(diagnostics.event_read_calls, 1);
    assert_eq!(diagnostics.event_records_read, 1);
}

#[test]
fn diagnostic_reset_preserves_events_and_messages_are_bounded_and_deduplicated() {
    let mut world = World::new();
    world.emit_event("Ping", EcsValue::I64(7)).unwrap();
    world.record_diagnostic_message("duplicate");
    world.record_diagnostic_message("duplicate");
    for index in 0..70 {
        world.record_diagnostic_message(format!("message-{index}"));
    }

    let diagnostics = world.diagnostics();
    assert_eq!(diagnostics.messages.len(), 64);
    assert_eq!(diagnostics.diagnostic_messages_deduplicated, 1);
    assert_eq!(diagnostics.diagnostic_messages_dropped, 7);
    assert_eq!(diagnostics.event_records_total, 1);

    world.reset_diagnostics();
    let reset = world.diagnostics();
    assert!(reset.messages.is_empty());
    assert_eq!(reset.events_emitted, 0);
    assert_eq!(reset.event_records_total, 1);
    assert_eq!(world.read_events("Ping").unwrap().len(), 1);

    world.set_frame(2);
    let pruned = world.diagnostics();
    assert_eq!(pruned.event_records_total, 0);
    assert_eq!(pruned.event_records_pruned, 1);
    world.emit_event("Ping", EcsValue::I64(8)).unwrap();
    world.clear_events(Some("Ping"));
    let cleared = world.diagnostics();
    assert_eq!(cleared.event_clear_calls, 1);
    assert_eq!(cleared.event_records_cleared, 1);
}

#[test]
fn checked_conversion_is_shared_by_components_resources_and_typed_events() {
    let mut world = World::new();
    world
        .register_schema(ComponentSchema::new(
            "Narrow",
            vec![
                FieldSchema::new("count", StorageType::UInt8),
                FieldSchema::new("ratio", StorageType::Float32),
            ],
        ))
        .unwrap();
    let entity = world.spawn_with_defaults(["Narrow".to_string()]).unwrap();
    world
        .set_field(entity, "Narrow", "count", EcsValue::I64(255))
        .unwrap();
    assert!(world
        .set_field(entity, "Narrow", "count", EcsValue::I64(256))
        .is_err());
    world
        .set_field(entity, "Narrow", "ratio", EcsValue::F64(1.0 / 3.0))
        .unwrap();
    assert_eq!(
        world.get_field(entity, "Narrow", "ratio").unwrap(),
        EcsValue::F64(f64::from((1.0_f64 / 3.0) as f32))
    );

    let mut resource = ComponentRow::new();
    resource.insert("count".to_string(), EcsValue::I64(7));
    resource.insert("ratio".to_string(), EcsValue::F64(0.1));
    world.insert_resource("Narrow", resource).unwrap();
    assert!(world
        .set_resource_field("Narrow", "count", EcsValue::I64(-1))
        .is_err());

    let mut event_fields = ComponentRow::new();
    event_fields.insert("count".to_string(), EcsValue::I64(9));
    event_fields.insert("ratio".to_string(), EcsValue::F64(0.2));
    world
        .emit_event("Narrow", EcsValue::Struct(event_fields))
        .unwrap();
    let event = world.read_events("Narrow").unwrap().pop().unwrap();
    let EcsValue::Struct(event_fields) = event.payload else {
        panic!("typed event payload must remain a struct");
    };
    assert_eq!(event_fields["count"], EcsValue::U64(9));
    assert_eq!(event_fields["ratio"], EcsValue::F64(f64::from(0.2_f32)));
}
