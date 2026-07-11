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
    assert_eq!(world.diagnostics().event_queues_total, 1);
}
