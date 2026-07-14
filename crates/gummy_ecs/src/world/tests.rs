use super::{ChangeEpoch, ChangeKind, World};
use crate::archetype::ComponentRow;
use crate::column::EcsValue;
use crate::entity::Entity;
use crate::query::{QueryCardinality, QueryFilter, QueryTerm};
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
fn change_journal_records_structural_field_and_tag_mutations_by_epoch() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    world.set_frame(11);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world
        .set_field(entity, "Position", "x", EcsValue::F64(12.0))
        .unwrap();
    world.add_component_default(entity, "Velocity").unwrap();
    world.add_tag(entity, "Mover").unwrap();
    world.remove_tag(entity, "Mover").unwrap();
    world.remove_component(entity, "Velocity").unwrap();
    world.despawn(entity).unwrap();

    let epoch = ChangeEpoch::new(11);
    let journal = world.change_journal();
    assert_eq!(journal.current_epoch(), epoch);
    assert_eq!(journal.latest_revision().get(), 9);
    assert_eq!(journal.records_for_epoch(epoch).count(), 9);
    assert_eq!(
        journal
            .records()
            .iter()
            .map(|record| &record.kind)
            .collect::<Vec<_>>(),
        vec![
            &ChangeKind::Spawned,
            &ChangeKind::ComponentAdded {
                component: "Position".to_string(),
            },
            &ChangeKind::FieldChanged {
                component: "Position".to_string(),
                field: "x".to_string(),
            },
            &ChangeKind::ComponentAdded {
                component: "Velocity".to_string(),
            },
            &ChangeKind::TagAdded {
                tag: "Mover".to_string(),
            },
            &ChangeKind::TagRemoved {
                tag: "Mover".to_string(),
            },
            &ChangeKind::ComponentRemoved {
                component: "Velocity".to_string(),
            },
            &ChangeKind::ComponentRemoved {
                component: "Position".to_string(),
            },
            &ChangeKind::Despawned,
        ]
    );
    let change = journal.entity_change(epoch, entity).unwrap();
    assert_eq!(change.spawned.unwrap().get(), 1);
    assert_eq!(change.despawned.unwrap().get(), 9);
    assert_eq!(change.components["Position"].added.unwrap().get(), 2);
    assert_eq!(change.components["Position"].removed.unwrap().get(), 8);
    assert_eq!(change.components["Position"].changed_fields["x"].get(), 3);
    assert_eq!(change.components["Velocity"].added.unwrap().get(), 4);
    assert_eq!(change.components["Velocity"].removed.unwrap().get(), 7);
    assert_eq!(change.tags["Mover"].added.unwrap().get(), 5);
    assert_eq!(change.tags["Mover"].removed.unwrap().get(), 6);
}

#[test]
fn change_journal_tracks_staged_and_f64_mutations_without_recording_noop_f64_writes() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    world.set_frame(3);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let before_f64_writes = world.change_journal().len();

    assert_eq!(
        world
            .set_field_f64_many("Position", "x", &[(entity, 0.0)])
            .unwrap(),
        0
    );
    assert_eq!(world.change_journal().len(), before_f64_writes);
    assert_eq!(
        world
            .set_field_f64_many("Position", "x", &[(entity, 3.0)])
            .unwrap(),
        1
    );
    assert!(matches!(
        world.change_journal().records().last().unwrap().kind,
        ChangeKind::FieldChanged { ref component, ref field }
            if component == "Position" && field == "x"
    ));

    world.stage_add_component(entity, "Velocity");
    world.stage_remove_component(entity, "Velocity");
    world.apply_staged().unwrap();
    let epoch = ChangeEpoch::new(3);
    let change = world.change_journal().entity_change(epoch, entity).unwrap();
    assert_eq!(change.components["Velocity"].added.unwrap().get(), 4);
    assert_eq!(change.components["Velocity"].removed.unwrap().get(), 5);

    world.despawn(entity).unwrap();
    let reused = world.spawn_empty();
    assert_eq!(reused.index, entity.index);
    assert_ne!(reused.generation, entity.generation);
    assert!(world
        .change_journal()
        .entity_change(epoch, reused)
        .is_some());
    assert_eq!(
        world
            .change_journal()
            .entity_change(epoch, entity)
            .unwrap()
            .despawned
            .unwrap()
            .get(),
        7
    );
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
fn cached_queries_are_updated_incrementally_when_archetypes_appear() {
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
    assert!(diagnostics.query_cache_hits >= 2);
    assert_eq!(diagnostics.query_cache_invalidations, 0);
    assert!(diagnostics.query_cache_refreshes >= 1);
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
fn tags_do_not_create_component_archetypes_and_cached_filters_track_membership() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let archetypes_before_tags = world.archetype_count();
    let heroes = QueryFilter::new([QueryTerm::WithTag("Hero".to_string())]);
    assert!(world.query_filter(heroes.clone()).unwrap().is_empty());

    for index in 0..128 {
        world.add_tag(entity, &format!("tag-{index}")).unwrap();
    }
    world.add_tag(entity, "Hero").unwrap();
    assert_eq!(world.archetype_count(), archetypes_before_tags);
    assert_eq!(world.query_filter(heroes.clone()).unwrap(), vec![entity]);
    world.remove_tag(entity, "Hero").unwrap();
    assert!(world.query_filter(heroes).unwrap().is_empty());
}

#[test]
fn stale_world_handles_are_rejected_after_dense_slot_reuse() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let stale = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.despawn(stale).unwrap();
    let current = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    assert_eq!(stale.index, current.index);
    assert_ne!(stale.generation, current.generation);

    assert!(world.get_field(stale, "Position", "x").is_err());
    assert!(world.add_component_default(stale, "Velocity").is_err());
    assert!(world.add_tag(stale, "stale").is_err());
    assert_eq!(
        world.query(["Position".to_string()]).unwrap(),
        vec![current]
    );
}

#[test]
fn structural_moves_and_generation_reuse_preserve_raw_entity_order() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let first = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let reused_slot = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let third = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.add_component_default(third, "Velocity").unwrap();
    world.add_component_default(first, "Velocity").unwrap();
    assert_eq!(
        world.query(["Position".to_string()]).unwrap(),
        vec![first, reused_slot, third]
    );

    world.despawn(reused_slot).unwrap();
    let reused = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    assert_eq!(reused.index, reused_slot.index);
    assert_eq!(
        world.query(["Position".to_string()]).unwrap(),
        vec![first, third, reused]
    );
}

#[test]
fn failed_structural_validation_leaves_the_world_unchanged() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let alive_before = world.alive_count();
    let archetypes_before = world.archetype_count();
    let components_before = world.entity_components(entity).unwrap();

    assert!(world
        .spawn_with_defaults(["Position".to_string(), "Missing".to_string()])
        .is_err());
    assert!(world.add_component_default(entity, "Missing").is_err());
    assert_eq!(world.alive_count(), alive_before);
    assert_eq!(world.archetype_count(), archetypes_before);
    assert_eq!(world.entity_components(entity).unwrap(), components_before);
}

#[test]
fn transition_edges_reuse_a_bounded_archetype_pair_under_churn() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    for _ in 0..64 {
        world.add_component_default(entity, "Velocity").unwrap();
        world.remove_component(entity, "Velocity").unwrap();
    }
    assert_eq!(world.archetype_count(), 2);
    assert_eq!(
        world.entity_components(entity).unwrap(),
        vec!["Position".to_string()]
    );
}

#[test]
fn component_moves_preserve_exact_wide_integer_values() {
    let mut world = World::new();
    world
        .register_schema(ComponentSchema::new(
            "Counter",
            vec![FieldSchema::new("value", StorageType::Int64)],
        ))
        .unwrap();
    world
        .register_schema(ComponentSchema::new(
            "Marker",
            vec![FieldSchema::new("value", StorageType::Bool)],
        ))
        .unwrap();
    let entity = world.spawn_with_defaults(["Counter".to_string()]).unwrap();
    let exact = 9_007_199_254_740_993_i64;
    world
        .set_field(entity, "Counter", "value", EcsValue::I64(exact))
        .unwrap();
    world.add_component_default(entity, "Marker").unwrap();
    world.remove_component(entity, "Marker").unwrap();
    assert_eq!(
        world.get_field(entity, "Counter", "value").unwrap(),
        EcsValue::I64(exact)
    );
}

#[test]
fn limit_aware_cardinality_stops_after_distinguishing_multiple_rows() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let filter = QueryFilter::new([QueryTerm::WithComponent("Position".to_string())]);
    assert_eq!(
        world.query_cardinality(filter.clone()).unwrap(),
        QueryCardinality::Zero
    );
    let only = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    assert_eq!(
        world.query_cardinality(filter.clone()).unwrap(),
        QueryCardinality::One(only)
    );
    world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let before = world.diagnostics().query_matched_rows;
    assert_eq!(
        world.query_cardinality(filter).unwrap(),
        QueryCardinality::Multiple
    );
    assert_eq!(world.diagnostics().query_matched_rows - before, 2);
}

#[test]
fn component_change_terms_filter_current_epoch_rows() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let unchanged = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    let added = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    let changed = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    let removed = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();

    world.set_frame(1);
    world.add_component_default(added, "Velocity").unwrap();
    world
        .set_field(changed, "Position", "x", EcsValue::F64(1.0))
        .unwrap();
    world.remove_component(removed, "Velocity").unwrap();

    let mut rows_for = |term| {
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                term,
            ]))
            .unwrap()
    };
    assert_eq!(
        rows_for(QueryTerm::Added("Velocity".to_string())),
        vec![added]
    );
    assert_eq!(
        rows_for(QueryTerm::Changed("Position".to_string())),
        vec![changed]
    );
    assert_eq!(
        rows_for(QueryTerm::Removed("Velocity".to_string())),
        vec![removed]
    );
    assert!(!rows_for(QueryTerm::Added("Velocity".to_string())).contains(&unchanged));
    assert_eq!(world.diagnostics().change_filter_matched_rows, 4);
}

#[test]
fn change_filters_include_first_epoch_mutations() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();

    assert_eq!(world.change_journal().current_epoch(), ChangeEpoch::new(0));
    assert_eq!(
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::Added("Velocity".to_string()),
            ]))
            .unwrap(),
        vec![entity]
    );
    assert_eq!(
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::Changed("Velocity".to_string()),
            ]))
            .unwrap(),
        vec![entity]
    );
}

#[test]
fn change_filters_coalesce_multiple_field_writes_into_one_live_row() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.set_frame(1);
    world
        .set_field(entity, "Position", "x", EcsValue::F64(1.0))
        .unwrap();
    world
        .set_field(entity, "Position", "x", EcsValue::F64(2.0))
        .unwrap();

    assert_eq!(
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::Changed("Position".to_string()),
            ]))
            .unwrap(),
        vec![entity]
    );
    assert_eq!(
        world
            .change_journal()
            .records_for_epoch(ChangeEpoch::new(1))
            .count(),
        2
    );
}

#[test]
fn change_filters_prefer_a_same_epoch_removal_over_an_earlier_addition() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.set_frame(1);
    world.add_component_default(entity, "Velocity").unwrap();
    world.remove_component(entity, "Velocity").unwrap();

    let rows_for = |world: &mut World, term| {
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                term,
            ]))
            .unwrap()
    };
    assert_eq!(
        rows_for(&mut world, QueryTerm::Added("Velocity".to_string())),
        vec![]
    );
    assert_eq!(
        rows_for(&mut world, QueryTerm::Changed("Velocity".to_string())),
        vec![]
    );
    assert_eq!(
        rows_for(&mut world, QueryTerm::Removed("Velocity".to_string())),
        vec![entity]
    );
}

#[test]
fn change_filters_prefer_a_same_epoch_addition_over_an_earlier_removal() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    world.set_frame(1);
    world.remove_component(entity, "Velocity").unwrap();
    world.add_component_default(entity, "Velocity").unwrap();

    let rows_for = |world: &mut World, term| {
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                term,
            ]))
            .unwrap()
    };
    assert_eq!(
        rows_for(&mut world, QueryTerm::Added("Velocity".to_string())),
        vec![entity]
    );
    assert_eq!(
        rows_for(&mut world, QueryTerm::Changed("Velocity".to_string())),
        vec![entity]
    );
    assert_eq!(
        rows_for(&mut world, QueryTerm::Removed("Velocity".to_string())),
        vec![]
    );
}

#[test]
fn change_filters_never_return_despawned_entities() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world
        .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
        .unwrap();
    world.set_frame(1);
    world.despawn(entity).unwrap();

    assert_eq!(
        world
            .query_filter(QueryFilter::new([QueryTerm::Removed(
                "Position".to_string()
            )]))
            .unwrap(),
        Vec::<Entity>::new()
    );
}

#[test]
fn change_filters_are_isolated_to_the_active_epoch_and_compact_history() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();
    world.set_frame(1);
    world.add_component_default(entity, "Velocity").unwrap();
    assert_eq!(
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::Added("Velocity".to_string()),
            ]))
            .unwrap(),
        vec![entity]
    );

    world.set_frame(2);
    assert!(world.change_journal().is_empty());
    assert!(world
        .change_journal()
        .entity_change(ChangeEpoch::new(1), entity)
        .is_none());
    assert_eq!(
        world
            .query_filter(QueryFilter::new([
                QueryTerm::WithComponent("Position".to_string()),
                QueryTerm::Added("Velocity".to_string()),
            ]))
            .unwrap(),
        Vec::<Entity>::new()
    );
}

#[test]
fn change_journal_diagnostics_track_updates_retention_and_reset() {
    let mut world = World::new();
    register_position_velocity(&mut world);
    let entity = world.spawn_with_defaults(["Position".to_string()]).unwrap();

    let initial = world.diagnostics();
    assert_eq!(initial.change_journal_updates, 2);
    assert_eq!(initial.change_journal_retained_records, 2);

    world.set_frame(1);
    let compacted = world.diagnostics();
    assert_eq!(compacted.change_journal_updates, 2);
    assert_eq!(compacted.change_journal_retained_records, 0);

    world.add_component_default(entity, "Velocity").unwrap();
    let updated = world.diagnostics();
    assert_eq!(updated.change_journal_updates, 3);
    assert_eq!(updated.change_journal_retained_records, 1);

    world.reset_diagnostics();
    let reset = world.diagnostics();
    assert_eq!(reset.change_journal_updates, 0);
    assert_eq!(reset.change_journal_retained_records, 1);
}

#[test]
fn component_change_terms_reject_unknown_schemas() {
    let mut world = World::new();
    register_position_velocity(&mut world);

    for term in [
        QueryTerm::Added("Unknown".to_string()),
        QueryTerm::Changed("Unknown".to_string()),
        QueryTerm::Removed("Unknown".to_string()),
    ] {
        assert!(matches!(
            world.query_filter(QueryFilter::new([term])),
            Err(crate::error::EcsError::UnknownSchema(component)) if component == "Unknown"
        ));
    }
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
fn clone_preserves_exact_incremental_query_caches() {
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
        before_clone.query_cache_misses
    );
    assert_eq!(
        clone_diagnostics.query_cache_hits,
        before_clone.query_cache_hits + 1
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
