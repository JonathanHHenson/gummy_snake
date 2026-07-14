from __future__ import annotations

from tests.helpers.ecs_fixtures import (
    Box,
    Counter,
    EcsWorld,
    Ping,
    Position,
    Velocity,
    ecs,
)


def test_spatial_aabb_overlaps_deduplicate_self_pairs() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), Box(4, 4))
    world.add_entity(Position(2, 0), Box(4, 4))
    world.add_entity(Position(20, 0), Box(2, 2))

    @ecs.system_plan
    def overlap_system(entity: ecs.Query[Position, Box]) -> None:
        half_w = entity[Box].width / 2
        half_h = entity[Box].height / 2
        bounds = ecs.spatial.aabb2(
            entity[Position].x - half_w,
            entity[Position].y - half_h,
            entity[Position].x + half_w,
            entity[Position].y + half_h,
        )
        overlaps = ecs.spatial.overlaps(
            entity,
            entity,
            origin_bounds=bounds,
            target_bounds=bounds,
            algorithm=ecs.spatial.HashGrid(cell_size=8.0),
            pair_policy="unique_unordered",
        )
        with ecs.conditional(), ecs.when(overlaps.any()):
            entity.ctx[Position].y.set_to(overlaps.count())

    world.add_system(overlap_system)
    world.run_pre_draw_systems()

    positions = sorted(
        (entity[Position].x, entity[Position].y) for entity in world.iter_entities(Position)
    )
    assert positions == [(0, 1), (2, 0), (20, 0)]
    assert world.diagnostics()["ecs_spatial_deduplicated_pairs"] >= 1


def test_system_dependencies_run_conditions_and_groups() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))
    should_run = False

    @ecs.system_plan
    def first(entity: ecs.Query[Position]) -> None:
        entity[Position].x.increase_by(1)

    @ecs.system_plan
    def second(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(entity[Position].x * 10)

    @ecs.system_plan
    def skipped(entity: ecs.Query[Position]) -> None:
        entity[Position].y.set_to(99)

    world.add_system(first, name="first")
    world.add_system(second, name="second", after=["first"])
    world.add_system(skipped, name="skipped", run_if=lambda: should_run)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 10
    assert entity[Position].y == 0
    assert world.diagnostics()["ecs_system_run_condition_skips"] == 1

    world.group("movement", enabled=False)
    world.add_system(first, name="set-member", group="movement")
    world.run_pre_draw_systems()
    assert world.get_entity(Position)[Position].x == 110


def test_change_detection_added_changed_and_removed_filters() -> None:
    def start_next_change_epoch(world: EcsWorld) -> None:
        world._rust.set_frame(world._ecs_frame + 1)

    added_world = EcsWorld()
    start_next_change_epoch(added_world)
    added_world.add_entity(Position(1, 1), Velocity(0, 0))
    added_world.add_entity(Position(10, 0), Velocity(0, 0))

    @ecs.system_plan
    def mark_added(entity: ecs.Query[Position, ecs.Added[Position]]) -> None:
        entity[Position].y.set_to(5)

    added_world.add_system(mark_added)
    added_world.run_pre_draw_systems()
    assert sorted(entity[Position].y for entity in added_world.iter_entities(Position)) == [5, 5]

    changed_world = EcsWorld()
    changed_entity = changed_world.add_entity(Position(1, 0))
    changed_world.run_pre_draw_systems()
    start_next_change_epoch(changed_world)
    changed_world.set_component(changed_entity, Position(4, 0))

    @ecs.system_plan
    def mark_changed(entity: ecs.Query[Position, ecs.Changed[Position]]) -> None:
        entity[Position].y.set_to(8)

    changed_world.add_system(mark_changed)
    changed_world.run_pre_draw_systems()
    assert changed_world.get_entity(Position)[Position].y == 8

    removed_world = EcsWorld()
    survivor = removed_world.add_entity(Position(0, 0), Velocity(1, 0))
    removed_world.run_pre_draw_systems()
    start_next_change_epoch(removed_world)
    removed_world.remove_component(survivor, Velocity)

    @ecs.system_plan
    def mark_removed(entity: ecs.Query[Position, ecs.Removed[Velocity]]) -> None:
        entity[Position].y.set_to(9)

    removed_world.add_system(mark_removed)
    removed_world.run_pre_draw_systems()
    assert removed_world.get_entity(Position)[Position].y == 9


def test_typed_ecs_events_reader_writer_and_public_queue() -> None:
    world = EcsWorld()
    world.set_resource(Counter(0))
    world.emit_event(Ping(2))
    assert world.read_events(Ping) == (Ping(2),)
    world.clear_events(Ping)
    assert world.read_events(Ping) == ()

    @ecs.system_plan
    def produce(writer: ecs.EventWriter[Ping]) -> None:
        writer.emit(Ping(3))

    @ecs.system_plan
    def consume(reader: ecs.EventReader[Ping], counter: ecs.ResMut[Counter]) -> None:
        with ecs.for_each(reader) as event:
            counter[Counter].value.increase_by(event.amount)

    world.add_system(produce, name="produce")
    world.add_system(consume, name="consume", after=["produce"])
    world.run_pre_draw_systems()
    assert world.get_resource(Counter).value == 3
    assert world.read_events(Ping) == (Ping(3),)

    world.run_pre_draw_systems()
    assert world.get_resource(Counter).value == 9
    world.clear_events()
    assert world.read_events(Ping) == ()
