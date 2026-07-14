from __future__ import annotations

from tests.helpers.ecs_fixtures import EcsWorld, Ping, Position, ecs


def test_public_diagnostics_merge_rust_event_counters_and_reset_both_layers() -> None:
    world = EcsWorld()
    entity = world.add_entity(Position(1, 2))
    world.emit_event(Ping(3))
    assert world.read_events(Ping) == (Ping(3),)
    world.configure(warn_on_ambiguity=False)
    world.record_ambiguity("diagnostic boundary")

    diagnostics = world.diagnostics()
    assert not hasattr(world, "_events")
    assert diagnostics["ecs_entities_alive"] == 1
    assert diagnostics["ecs_rust_entities_alive"] == 1
    assert diagnostics["ecs_events_emitted"] == 1
    assert diagnostics["ecs_rust_events_emitted"] == 1
    assert diagnostics["ecs_events_read"] == 1
    assert diagnostics["ecs_event_records_total"] == 1
    assert diagnostics["ecs_python_event_mirror_entries"] == 0
    assert diagnostics["ecs_python_event_payload_materializations"] == 0
    assert diagnostics["ecs_scheduler_world_clones"] == 0
    assert diagnostics["ecs_canvas_python_replays"] == 0
    assert diagnostics["ecs_canvas_python_materialized_commands"] == 0
    assert "ecs_prepared_plan_bytes_current" in diagnostics
    assert "ecs_event_queue_bytes" in diagnostics
    assert "ecs_resource_row_bytes" in diagnostics
    assert diagnostics["messages"] == ["diagnostic boundary"]

    world.reset_diagnostics()
    reset = world.diagnostics()
    assert reset["ecs_entities_alive"] == 1
    assert reset["ecs_events_emitted"] == 0
    assert reset["ecs_events_read"] == 0
    assert reset["ecs_event_records_total"] == 1
    assert reset.get("ecs_ambiguity_warnings", 0) == 0
    assert reset["messages"] == []
    assert world.get_entity(Position).entity == entity
    assert world.read_events(Ping) == (Ping(3),)


def test_public_change_journal_diagnostics_are_dynamic_and_resettable() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 2))

    diagnostics = world.diagnostics()
    updates = diagnostics["ecs_change_journal_updates"]
    retained_records = diagnostics["ecs_change_journal_retained_records"]
    assert updates > 0
    assert retained_records == updates
    assert diagnostics["ecs_change_filter_matched_rows"] == 0

    world.reset_diagnostics()
    reset = world.diagnostics()
    assert reset["ecs_change_journal_updates"] == 0
    assert reset["ecs_change_journal_retained_records"] == retained_records
    assert reset["ecs_change_filter_matched_rows"] == 0


def test_diagnostic_messages_are_bounded_and_deduplicated_in_rust() -> None:
    world = EcsWorld()
    world.configure(warn_on_ambiguity=False)
    for index in range(70):
        world.record_ambiguity(f"message-{index}")
    world.record_ambiguity("message-69")

    diagnostics = world.diagnostics()
    assert diagnostics["ecs_ambiguity_warnings"] == 71
    assert diagnostics["ecs_diagnostic_messages_deduplicated"] == 1
    assert diagnostics["ecs_diagnostic_messages_dropped"] == 6
    assert len(diagnostics["messages"]) == 64
    assert diagnostics["messages"][-1] == "message-69"


def test_diagnostics_reuse_change_filtered_rust_plans_without_recompiling() -> None:
    steady_world = EcsWorld()
    steady_world.add_entity(Position(0, 0))

    @ecs.system_plan
    def steady(entity: ecs.Query[Position]) -> None:
        entity[Position].x.increase_by(1)

    steady_world.add_system(steady)
    steady_world.run_pre_draw_systems()
    steady_world.run_pre_draw_systems()
    steady_diagnostics = steady_world.diagnostics()
    assert steady_diagnostics["ecs_dynamic_change_plan_recompiles"] == 0
    assert steady_diagnostics["ecs_steady_physical_plan_reuses"] == 2

    change_world = EcsWorld()
    change_world.add_entity(Position(0, 0))

    @ecs.system_plan
    def changed(entity: ecs.Query[Position, ecs.Changed[Position]]) -> None:
        entity[Position].y.increase_by(1)

    change_world.add_system(changed)
    change_world.run_pre_draw_systems()
    change_world.run_pre_draw_systems()
    change_diagnostics = change_world.diagnostics()
    assert change_diagnostics["ecs_dynamic_change_plan_recompiles"] == 0
    assert change_diagnostics["ecs_physical_plan_compiles"] == 1
    assert change_diagnostics["ecs_steady_physical_plan_reuses"] == 2
    assert change_diagnostics["ecs_change_filter_matched_rows"] >= 1
    assert change_diagnostics["ecs_python_event_mirror_entries"] == 0
