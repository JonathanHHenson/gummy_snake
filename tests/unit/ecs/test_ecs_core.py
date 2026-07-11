from __future__ import annotations

from typing import Any, cast

from tests.helpers.ecs_fixtures import (
    HERO,
    PLATFORM,
    Box,
    ComponentSchemaError,
    Counter,
    EcsWorld,
    Iterable,
    Position,
    StaleEntityError,
    SystemPlanError,
    Trail,
    VecPosition,
    Velocity,
    dataclass,
    ecs,
    inspect,
    pytest,
)


def test_dataclass_scalar_schema_and_annotated_ranges() -> None:
    world = EcsWorld()

    world.add_entity(Position(1, 2), Box(3, 4), tags=["ok"])

    with pytest.raises(ValueError, match="overflows UInt16"):
        world.add_entity(Box(70_000, 1))

    @dataclass
    class UnsupportedComponent:
        values: list[int]

    with pytest.raises(ComponentSchemaError, match="ECS supports bool, int, float, str"):
        world.add_entity(UnsupportedComponent([1, 2, 3]))

    world.add_entity(VecPosition((1.0, 2.0)), Trail([1.0, 2.0, 3.0]))


def test_entity_query_mutation_components_tags_and_stale_handles() -> None:
    world = EcsWorld()
    entity = world.add_entity(Position(1, 2), tags=["Hero"])
    view = world.get_entity(Position, tags=["Hero"])

    view[Position].x = 5
    view.add_component(Velocity(1, 0))
    view.add_tag("Alive")

    mutated = world.get_entity(Position, Velocity, tags=["Hero", "Alive"])
    assert mutated[Position].x == 5
    assert mutated[Velocity].dx == 1

    mutated.remove_component(Velocity)
    mutated.remove_tag("Alive")
    assert list(world.iter_entities(Position, Velocity)) == []

    world.despawn_entity(entity)
    with pytest.raises(StaleEntityError):
        world.add_tag(entity, "stale")


def test_decorators_do_not_expose_removed_or_invalid_parameters() -> None:
    assert "python" not in inspect.signature(ecs.system).parameters
    assert "python" not in inspect.signature(ecs.udf).parameters
    assert "python" not in inspect.signature(ecs.system_plan).parameters
    assert "python" not in inspect.signature(ecs.udf_plan).parameters
    assert "parallel" not in inspect.signature(ecs.system).parameters
    assert "queries" not in inspect.signature(ecs.system_plan).parameters
    assert "mutations" not in inspect.signature(ecs.system_plan).parameters
    assert "side_effects" not in inspect.signature(ecs.udf).parameters
    assert "side_effects" not in inspect.signature(ecs.udf_plan).parameters
    assert "reads" not in inspect.signature(ecs.udf).parameters
    assert "writes" not in inspect.signature(ecs.udf).parameters
    assert "structural" not in inspect.signature(ecs.udf).parameters
    assert "mutations" not in inspect.signature(ecs.udf_plan).parameters
    assert "reads" not in inspect.signature(ecs.udf_plan).parameters
    assert "writes" not in inspect.signature(ecs.udf_plan).parameters
    assert "structural" not in inspect.signature(ecs.udf_plan).parameters


def test_resources_and_system_resource_mutation() -> None:
    world = EcsWorld()
    world.set_resource(Counter(1))

    @ecs.system_plan
    def increment(counter: ecs.ResMut[Counter]) -> None:
        counter[Counter].value.increase_by(2)

    world.add_system(increment)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 3
    world.remove_resource(Counter)
    with pytest.raises(KeyError):
        world.get_resource(Counter)


def test_supported_system_executes_in_rust_and_reads_rust_backed_views() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0), Velocity(3, 0))

    @ecs.system_plan
    def move(entity: ecs.Query[Position, Velocity]) -> None:
        entity[Position].x.increase_by(entity[Velocity].dx)

    world.add_system(move)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position, Velocity)
    assert entity[Position].x == 4
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_physical_system_runs"] == 1
    assert diagnostics.get("ecs_python_fallback_system_runs", 0) == 0
    assert diagnostics["ecs_physical_fields_written"] == 1


def test_supported_when_and_resource_system_execute_in_rust() -> None:
    world = EcsWorld()
    world.add_entity(Position(2, 0))
    world.set_resource(Counter(1))

    @ecs.system_plan
    def branch(entity: ecs.Query[Position], counter: ecs.ResMut[Counter]) -> None:
        with ecs.conditional():
            with ecs.when(entity[Position].x > 1):
                counter[Counter].value.increase_by(2)
            with ecs.otherwise():
                counter[Counter].value.set_to(0)

    world.add_system(branch)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 3
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_physical_system_runs"] == 1
    assert diagnostics["ecs_physical_resource_fields_written"] == 1


def test_system_do_in_order_when_otherwise_and_dt_expression() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0), Velocity(3, 0))

    @ecs.system_plan
    def move(entity: ecs.Query[Position, Velocity]) -> None:
        entity[Position].x.set_to(entity[Position].x + entity[Velocity].dx + ecs.dt())
        with ecs.conditional():
            with ecs.when(entity[Position].x > 3):
                entity[Velocity].dy.set_to(10)
            with ecs.otherwise():
                entity[Velocity].dy.set_to(-10)

    world.add_system(move)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position, Velocity)
    assert entity[Position].x == 4
    assert entity[Velocity].dy == 10


def test_do_in_parallel_uses_snapshot_reads_for_independent_actions() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0))

    @ecs.system_plan(parallel=True)
    def snapshot(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(5)
        entity[Position].y.set_to(entity[Position].x)

    world.add_system(snapshot)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 5
    assert entity[Position].y == 1


def test_do_in_parallel_conflicts_warn_and_strict_errors() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))

    @ecs.system_plan(parallel=True)
    def conflict(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(1)
        entity[Position].x.set_to(2)

    world.add_system(conflict)
    with pytest.warns(RuntimeWarning, match="do_in_parallel"):
        world.run_pre_draw_systems()
    assert world.get_entity(Position)[Position].x == 2
    assert world.diagnostics()["ecs_ambiguity_warnings"] == 1

    strict_world = EcsWorld()
    strict_world.configure(strict=True)
    strict_world.add_entity(Position(0, 0))
    strict_world.add_system(conflict)
    with pytest.raises(SystemPlanError, match="do_in_parallel"):
        strict_world.run_pre_draw_systems()


def test_unaggregated_join_duplicate_writes_warn_and_can_be_suppressed() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[HERO])
    world.add_entity(Position(1, 0), tags=[HERO])
    world.add_entity(Position(0, 0), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system_plan
    def ungrouped(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> None:
        near = ((platform[Position].x - 5) <= hero[Position].x) & (
            hero[Position].x <= (platform[Position].x + 5)
        )
        with ecs.conditional(), ecs.when(near):
            platform.ctx[Velocity].dx.set_to(3)

    world.add_system(ungrouped)
    with pytest.warns(RuntimeWarning, match="last-write-wins"):
        world.run_pre_draw_systems()
    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 3

    quiet_world = EcsWorld()
    quiet_world.configure(warn_on_ambiguity=False)
    quiet_world.add_entity(Position(0, 0), tags=[HERO])
    quiet_world.add_entity(Position(1, 0), tags=[HERO])
    quiet_world.add_entity(Position(0, 0), Velocity(0, 0), tags=[PLATFORM])
    quiet_world.add_system(ungrouped)
    quiet_world.run_pre_draw_systems()
    diagnostics = quiet_world.diagnostics()
    assert diagnostics["ecs_ambiguity_warnings"] == 1
    assert diagnostics["ecs_ambiguity_warnings_suppressed"] == 1


def test_group_by_any_reduces_join_to_one_write_per_group() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[HERO])
    world.add_entity(Position(1, 0), tags=[HERO])
    world.add_entity(Position(0, 0), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system_plan
    def grouped(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> None:
        near = ((platform[Position].x - 5) <= hero[Position].x) & (
            hero[Position].x <= (platform[Position].x + 5)
        )
        with ecs.conditional(), ecs.when(near.group_by(platform).any()):
            platform.ctx[Velocity].dx.set_to(3)

    world.add_system(grouped)
    world.run_pre_draw_systems()

    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 3
    assert world.diagnostics().get("ecs_ambiguity_warnings", 0) == 0


def test_exists_where_scans_inner_query_without_cross_join_writes() -> None:
    world = EcsWorld()
    world.add_entity(Position(10, 0), tags=[HERO])
    world.add_entity(Position(0, 0), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system_plan
    def exists_system(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> None:
        has_right_hero = ecs.exists(hero).where(hero[Position].x > platform[Position].x)
        with ecs.conditional(), ecs.when(has_right_hero):
            platform.ctx[Velocity].dx.set_to(7)

    world.add_system(exists_system)
    world.run_pre_draw_systems()

    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 7
    assert world.diagnostics().get("ecs_ambiguity_warnings", 0) == 0


def test_udf_action_and_for_each_iterable_source() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0))
    world.set_resource(Counter(0))

    @ecs.udf(mutations={"items": {ecs.EntityMutation[Position](update=True)}})
    def boost(items: Iterable[ecs.Entity[Position]]) -> None:
        for item in items:
            item[Position].x += 5

    @ecs.udf
    def numbers() -> Iterable[int]:
        return (1, 2, 3)

    @ecs.system_plan
    def udf_system(entity: ecs.Query[Position], counter: ecs.ResMut[Counter]) -> None:
        boost(entity)
        with ecs.for_each(cast(Any, numbers())) as item:
            counter[Counter].value.set_to(item)

    world.add_system(udf_system)
    world.run_pre_draw_systems()

    assert world.get_entity(Position)[Position].x == 6
    assert world.get_resource(Counter).value == 3
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_udf_calls"] == 2
    assert diagnostics.get("ecs_python_fallback_system_runs", 0) == 0
