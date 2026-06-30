from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated, Any, cast

import pytest

from gummysnake import Sketch, ecs
from gummysnake.ecs import types as ecs_t
from gummysnake.ecs.world import EcsWorld
from gummysnake.exceptions import (
    BackendCapabilityError,
    ComponentSchemaError,
    StaleEntityError,
    SystemPlanError,
)
from gummysnake.plugins import Plugin, clear_plugins, install_plugin
from gummysnake.rust import ecs as rust_ecs

HERO = "Hero"
PLATFORM = "Platform"


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


@dataclass
class Box:
    width: Annotated[int, ecs_t.UInt16]
    height: Annotated[int, ecs_t.UInt16]


@dataclass
class Counter:
    value: int


@dataclass
class Label:
    value: str


@dataclass
class Trail:
    samples: Annotated[list[float], ecs_t.List(ecs_t.Float64)]


@dataclass
class VecPosition:
    xy: Annotated[tuple[float, float], ecs_t.Vec2F32]


@dataclass
class Ping:
    amount: int


def test_rust_ecs_bridge_compiles_plan_payload() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64"), ("y", "Float64")])
    world.register_schema("Clock", [("dt", "Float64")])
    payload = {
        "version": 1,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [("with_component", "Position"), ("with_tag", HERO)],
            }
        ],
        "expressions": [
            {"kind": "field", "query": "entity", "component": "Position", "field": "x"},
            {"kind": "resource_field", "resource": "Clock", "field": "dt"},
            {"kind": "binary", "op": "+", "left": 0, "right": 1},
        ],
        "actions": [{"kind": "set_field", "target": 0, "value": 2}],
        "root_action": 0,
    }

    summary = world.compile_bridge_plan(payload)

    assert isinstance(summary["handle"], int)
    assert summary["handle"] > 0
    assert world.compiled_plan_count() == 1
    assert summary["query_count"] == 1
    assert summary["expression_count"] == 3
    assert summary["action_count"] == 1
    assert summary["access"]["reads"] == ["component:Position", "resource:Clock"]
    assert summary["access"]["writes"] == ["component:Position"]


def test_rust_ecs_bridge_executes_plan_payload() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64"), ("y", "Float64")])
    world.register_schema("Velocity", [("dx", "Float64"), ("dy", "Float64")])
    index, generation = world.allocate_entity()
    world.add_component_default(index, generation, "Position")
    world.add_component_default(index, generation, "Velocity")
    world.set_field(index, generation, "Position", "x", 2.0)
    world.set_field(index, generation, "Velocity", "dx", 3.0)
    payload = {
        "version": 1,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [
                    ("with_component", "Position"),
                    ("with_component", "Velocity"),
                ],
            }
        ],
        "expressions": [
            {"kind": "field", "query": "entity", "component": "Position", "field": "x"},
            {"kind": "field", "query": "entity", "component": "Velocity", "field": "dx"},
            {"kind": "binary", "op": "add", "left": 0, "right": 1},
        ],
        "actions": [{"kind": "set_field", "target": 0, "value": 2}],
        "root_action": 0,
    }

    summary = world.compile_bridge_plan(payload)
    report = world.execute_compiled_plan(summary["handle"])

    assert world.get_field(index, generation, "Position", "x") == 5.0
    assert report["fields_written"] == 1
    assert report["component_writes"] == [
        {
            "index": index,
            "generation": generation,
            "component": "Position",
            "field": "x",
            "value": 5.0,
        }
    ]


def test_rust_ecs_wrapper_validates_abi_and_spatial_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWorld:
        pass

    class FakeRegistry:
        pass

    runtime = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        ecs_health_check=lambda: "ok",
        EcsWorld=FakeWorld,
        EcsSpatialIndexRegistry=FakeRegistry,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", runtime)
    assert isinstance(rust_ecs.create_ecs_world(), FakeWorld)
    assert isinstance(rust_ecs.create_spatial_index_registry(), FakeRegistry)

    bad_runtime = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION + 1,
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", bad_runtime)
    with pytest.raises(BackendCapabilityError, match="ABI"):
        rust_ecs.require_ecs_runtime()

    missing_spatial = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", missing_spatial)
    with pytest.raises(BackendCapabilityError, match="EcsSpatialIndexRegistry"):
        rust_ecs.create_spatial_index_registry()


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


def test_resources_and_system_resource_mutation() -> None:
    world = EcsWorld()
    world.set_resource(Counter(1))

    @ecs.system
    def increment(counter: ecs.ResMut[Counter]) -> ecs.Action:
        return ecs.set(counter[Counter].value, counter[Counter].value + 2)

    world.add_system(increment)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 3
    world.remove_resource(Counter)
    with pytest.raises(KeyError):
        world.get_resource(Counter)


def test_supported_system_executes_in_rust_and_reads_rust_backed_views() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0), Velocity(3, 0))

    @ecs.system
    def move(entity: ecs.Query[Position, Velocity]) -> ecs.Action:
        return ecs.set(entity[Position].x, entity[Position].x + entity[Velocity].dx)

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

    @ecs.system
    def branch(entity: ecs.Query[Position], counter: ecs.ResMut[Counter]) -> ecs.Action:
        return (
            ecs.when(entity[Position].x > 1)
            .do(ecs.set(counter[Counter].value, counter[Counter].value + 2))
            .otherwise()
            .do(ecs.set(counter[Counter].value, 0))
        )

    world.add_system(branch)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 3
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_physical_system_runs"] == 1
    assert diagnostics["ecs_physical_resource_fields_written"] == 1


def test_system_do_in_order_when_otherwise_and_dt_expression() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0), Velocity(3, 0))

    @ecs.system
    def move(entity: ecs.Query[Position, Velocity]) -> ecs.Action:
        return ecs.do_in_order(
            ecs.set(entity[Position].x, entity[Position].x + entity[Velocity].dx + ecs.dt()),
            ecs.when(entity[Position].x > 3)
            .do(ecs.set(entity[Velocity].dy, 10))
            .otherwise()
            .do(ecs.set(entity[Velocity].dy, -10)),
        )

    world.add_system(move)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position, Velocity)
    assert entity[Position].x == 4
    assert entity[Velocity].dy == 10


def test_do_in_parallel_uses_snapshot_reads_for_independent_actions() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0))

    @ecs.system
    def snapshot(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.do_in_parallel(
            ecs.set(entity[Position].x, 5),
            ecs.set(entity[Position].y, entity[Position].x),
        )

    world.add_system(snapshot)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 5
    assert entity[Position].y == 1


def test_do_in_parallel_conflicts_warn_and_strict_errors() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))

    @ecs.system
    def conflict(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.do_in_parallel(
            ecs.set(entity[Position].x, 1),
            ecs.set(entity[Position].x, 2),
        )

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

    @ecs.system
    def ungrouped(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> ecs.Action:
        near = ((platform[Position].x - 5) <= hero[Position].x) & (
            hero[Position].x <= (platform[Position].x + 5)
        )
        return ecs.when(near).do(ecs.set(platform.ctx[Velocity].dx, 3))

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

    @ecs.system
    def grouped(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> ecs.Action:
        near = ((platform[Position].x - 5) <= hero[Position].x) & (
            hero[Position].x <= (platform[Position].x + 5)
        )
        return ecs.when(near.group_by(platform).any()).do(ecs.set(platform.ctx[Velocity].dx, 3))

    world.add_system(grouped)
    world.run_pre_draw_systems()

    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 3
    assert world.diagnostics().get("ecs_ambiguity_warnings", 0) == 0


def test_exists_where_scans_inner_query_without_cross_join_writes() -> None:
    world = EcsWorld()
    world.add_entity(Position(10, 0), tags=[HERO])
    world.add_entity(Position(0, 0), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system
    def exists_system(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> ecs.Action:
        has_right_hero = ecs.exists(hero).where(hero[Position].x > platform[Position].x)
        return ecs.when(has_right_hero).do(ecs.set(platform.ctx[Velocity].dx, 7))

    world.add_system(exists_system)
    world.run_pre_draw_systems()

    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 7
    assert world.diagnostics().get("ecs_ambiguity_warnings", 0) == 0


def test_udf_action_and_for_each_iterable_source() -> None:
    world = EcsWorld()
    world.add_entity(Position(1, 0))
    world.set_resource(Counter(0))

    @ecs.udf
    def boost(items: Iterable[ecs.MutEntity[Position]]) -> None:
        for item in items:
            item[Position].x += 5

    @ecs.udf
    def numbers() -> Iterable[int]:
        return (1, 2, 3)

    @ecs.system
    def udf_system(entity: ecs.Query[Position], counter: ecs.ResMut[Counter]) -> ecs.Action:
        loop = ecs.for_each(numbers())
        return ecs.do_in_order(
            cast(ecs.Action, boost(entity)),
            loop.do(ecs.set(counter[Counter].value, loop.item)),
        )

    world.add_system(udf_system)
    world.run_pre_draw_systems()

    assert world.get_entity(Position)[Position].x == 6
    assert world.get_resource(Counter).value == 3
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_udf_calls"] == 2
    assert diagnostics.get("ecs_python_fallback_system_runs", 0) == 0


def test_system_plan_explain_describes_action_tree() -> None:
    @ecs.system
    def explained(entity: ecs.Query[Position, Velocity]) -> ecs.Action:
        return ecs.do_in_parallel(
            ecs.set(entity[Position].x, entity[Position].x + entity[Velocity].dx),
            ecs.when(entity[Position].x > 10)
            .do(ecs.set(entity[Velocity].dy, 1))
            .otherwise()
            .do(ecs.set(entity[Velocity].dy, 0)),
        )

    explanation = explained.explain()
    assert "do_in_parallel" in explanation
    assert "set Position.x" in explanation
    assert "Position.x <-" in explanation
    assert "when_chain" in explanation
    assert "when[1]" in explanation
    assert "otherwise" in explanation


def test_system_plan_explain_describes_spatial_relations() -> None:
    @ecs.system
    def explained(entity: ecs.Query[Position]) -> ecs.Action:
        point = ecs.spatial.point2(entity[Position].x, entity[Position].y)
        nearby = ecs.spatial.neighbors(
            entity,
            position=point,
            radius=5.0,
            algorithm=ecs.spatial.HashGrid(cell_size=5.0),
            include_self=False,
            allow_fallback=False,
            name="nearby_positions",
        )
        return ecs.when(nearby.any()).do(ecs.set(entity.ctx[Position].y, nearby.count()))

    explanation = explained.explain()
    assert "spatial.any(nearby_positions)" in explanation
    assert "spatial.count(nearby_positions)" in explanation
    assert "spatial_relation name=nearby_positions" in explanation
    assert "algorithm=hash_grid" in explanation
    assert "dimensions=2" in explanation
    assert "origin=entity" in explanation
    assert "pair_policy=all" in explanation


def test_system_must_return_action_not_plan() -> None:
    world = EcsWorld()

    @ecs.system
    def bad() -> ecs.Action:
        return ecs.do().plan()  # type: ignore[return-value]

    with pytest.raises(SystemPlanError, match="returned SystemPlan"):
        world.add_system(bad)


def test_grouped_value_aggregates_count_sum_min_max_mean() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[PLATFORM])
    world.add_entity(Position(1, 0), tags=[HERO])
    world.add_entity(Position(2, 0), tags=[HERO])
    world.add_entity(Position(20, 0), tags=[HERO])
    world.set_resource(Counter(0))

    @ecs.system
    def aggregate_system(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position],
        hero: ecs.Query[ecs.Tag[HERO], Position],
        counter: ecs.ResMut[Counter],
    ) -> ecs.Action:
        near = (hero[Position].x - platform[Position].x).abs() <= 5
        grouped = near.group_by(platform)
        return ecs.do_in_order(
            ecs.set(counter[Counter].value, grouped.count()),
            ecs.set(platform[Position].x, grouped.sum(hero[Position].x)),
            ecs.set(platform[Position].y, grouped.mean(hero[Position].x, default=0.0)),
        )

    world.add_system(aggregate_system)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 2
    platform = world.get_entity(Position, tags=[PLATFORM])
    assert platform[Position].x == 3
    assert platform[Position].y == 1.5


def test_vector_list_markers_and_for_each_column_source() -> None:
    world = EcsWorld()
    world.add_entity(Trail([1.0, 2.0, 4.0]), VecPosition((3.0, 5.0)))
    world.set_resource(Counter(0))

    @ecs.system
    def sum_trail(entity: ecs.Query[Trail], counter: ecs.ResMut[Counter]) -> ecs.Action:
        sample = ecs.for_each(entity[Trail].samples)
        return sample.do(ecs.set(counter[Counter].value, counter[Counter].value + sample.item))

    world.add_system(sum_trail)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 7


def test_spatial_hash_neighbors_and_join_aggregates() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[HERO])
    world.add_entity(Position(3, 4), tags=[HERO])
    world.add_entity(Position(20, 0), tags=[HERO])
    world.add_entity(Position(1, 1), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system
    def neighbor_system(hero: ecs.Query[ecs.Tag[HERO], Position]) -> ecs.Action:
        pos = ecs.spatial.point2(hero[Position].x, hero[Position].y)
        neighbors = ecs.spatial.neighbors(
            hero,
            position=pos,
            radius=6.0,
            algorithm=ecs.spatial.HashGrid(cell_size=6.0),
            include_self=False,
            allow_fallback=False,
        )
        return ecs.set(hero[Position].y, neighbors.count())

    @ecs.system
    def platform_sensor(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> ecs.Action:
        nearby = ecs.spatial.join(
            platform,
            hero,
            origin_position=ecs.spatial.point2(platform[Position].x, platform[Position].y),
            target_position=ecs.spatial.point2(hero[Position].x, hero[Position].y),
            radius=4.0,
            algorithm=ecs.spatial.HashGrid(cell_size=4.0),
            allow_fallback=False,
        )
        return ecs.when(nearby.any()).do(ecs.set(platform.ctx[Velocity].dx, nearby.count()))

    world.add_system(neighbor_system)
    world.add_system(platform_sensor, order=1)
    world.run_pre_draw_systems()

    heroes = sorted(
        (entity[Position].x, entity[Position].y)
        for entity in world.iter_entities(Position, tags=[HERO])
    )
    assert heroes == [(0, 1), (3, 1), (20, 0)]
    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 2
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_spatial_indexes_built"] >= 2
    assert diagnostics["ecs_spatial_indexes_built"] <= 4
    assert diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0


def test_spatial_tree_algorithms_execute_in_rust_without_fallbacks() -> None:
    @ecs.system
    def tree_system(entity: ecs.Query[Position]) -> ecs.Action:
        pos = ecs.spatial.point2(entity[Position].x, entity[Position].y)
        relation = ecs.spatial.neighbors(
            entity,
            position=pos,
            radius=4.0,
            algorithm=ecs.spatial.Quadtree(ecs.spatial.Bounds2D(-10, -10, 10, 10)),
        )
        return ecs.set(entity[Position].y, relation.count())

    world = EcsWorld()
    world.add_entity(Position(0, 0))
    world.add_system(tree_system)
    world.run_pre_draw_systems()
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_physical_system_runs"] == 1
    assert diagnostics["ecs_spatial_algorithm_quadtree"] == 1
    assert diagnostics["ecs_spatial_indexes_built"] == 1
    assert diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0
    assert diagnostics.get("ecs_python_fallback_system_runs", 0) == 0

    strict_world = EcsWorld()
    strict_world.configure(strict=True)
    strict_world.add_entity(Position(0, 0))
    strict_world.add_system(tree_system)
    strict_world.run_pre_draw_systems()
    strict_diagnostics = strict_world.diagnostics()
    assert strict_diagnostics["ecs_spatial_algorithm_quadtree"] == 1
    assert strict_diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0


def test_spatial_aabb_overlaps_deduplicate_self_pairs() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), Box(4, 4))
    world.add_entity(Position(2, 0), Box(4, 4))
    world.add_entity(Position(20, 0), Box(2, 2))

    @ecs.system
    def overlap_system(entity: ecs.Query[Position, Box]) -> ecs.Action:
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
            allow_fallback=False,
        )
        return ecs.when(overlaps.any()).do(ecs.set(entity.ctx[Position].y, overlaps.count()))

    world.add_system(overlap_system)
    world.run_pre_draw_systems()

    positions = sorted(
        (entity[Position].x, entity[Position].y) for entity in world.iter_entities(Position)
    )
    assert positions == [(0, 1), (2, 0), (20, 0)]
    assert world.diagnostics()["ecs_spatial_deduplicated_pairs"] >= 1


def test_system_dependencies_run_conditions_and_sets() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))
    should_run = False

    @ecs.system
    def first(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.set(entity[Position].x, entity[Position].x + 1)

    @ecs.system
    def second(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.set(entity[Position].x, entity[Position].x * 10)

    @ecs.system
    def skipped(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.set(entity[Position].y, 99)

    world.add_system(first, name="first")
    world.add_system(second, name="second", after=["first"])
    world.add_system(skipped, name="skipped", run_if=lambda: should_run)
    world.run_pre_draw_systems()

    entity = world.get_entity(Position)
    assert entity[Position].x == 10
    assert entity[Position].y == 0
    assert world.diagnostics()["ecs_system_run_condition_skips"] == 1

    world.configure_system_set("movement", enabled=False)
    world.add_system(first, name="set-member", set="movement")
    world.run_pre_draw_systems()
    assert world.get_entity(Position)[Position].x == 110


def test_change_detection_added_changed_and_removed_filters() -> None:
    added_world = EcsWorld()
    added_world.add_entity(Position(1, 1), Velocity(0, 0))
    added_world.add_entity(Position(10, 0), Velocity(0, 0))

    @ecs.system
    def mark_added(entity: ecs.Query[Position, ecs.Added[Position]]) -> ecs.Action:
        return ecs.set(entity[Position].y, 5)

    added_world.add_system(mark_added)
    added_world.run_pre_draw_systems()
    assert sorted(entity[Position].y for entity in added_world.iter_entities(Position)) == [5, 5]

    changed_world = EcsWorld()
    changed_entity = changed_world.add_entity(Position(1, 0))
    changed_world.run_pre_draw_systems()
    changed_world.set_component(changed_entity, Position(4, 0))

    @ecs.system
    def mark_changed(entity: ecs.Query[Position, ecs.Changed[Position]]) -> ecs.Action:
        return ecs.set(entity[Position].y, 8)

    changed_world.add_system(mark_changed)
    changed_world.run_pre_draw_systems()
    assert changed_world.get_entity(Position)[Position].y == 8

    removed_world = EcsWorld()
    survivor = removed_world.add_entity(Position(0, 0), Velocity(1, 0))
    removed_world.run_pre_draw_systems()
    removed_world.remove_component(survivor, Velocity)

    @ecs.system
    def mark_removed(entity: ecs.Query[Position, ecs.Removed[Velocity]]) -> ecs.Action:
        return ecs.set(entity[Position].y, 9)

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

    @ecs.system
    def produce(writer: ecs.EventWriter[Ping]) -> ecs.Action:
        return ecs.emit_event(cast(Any, writer), Ping(3))

    @ecs.system
    def consume(reader: ecs.EventReader[Ping], counter: ecs.ResMut[Counter]) -> ecs.Action:
        event = ecs.for_each(reader)
        return event.do(ecs.set(counter[Counter].value, counter[Counter].value + event.item.amount))

    world.add_system(produce, name="produce")
    world.add_system(consume, name="consume", after=["produce"])
    world.run_pre_draw_systems()
    assert world.get_resource(Counter).value == 3
    assert world.read_events(Ping) == (Ping(3),)

    world.run_pre_draw_systems()
    assert world.get_resource(Counter).value == 9
    world.clear_events()
    assert world.read_events(Ping) == ()


def test_system_dependency_cycles_error() -> None:
    world = EcsWorld()

    @ecs.system
    def one() -> ecs.Action:
        return ecs.do()

    @ecs.system
    def two() -> ecs.Action:
        return ecs.do()

    world.add_system(one, name="one")
    world.add_system(two, name="two", after=["one"])
    with pytest.raises(SystemPlanError, match="cycle"):
        world.add_system(one, name="one-again", after=["two"], before=["one"])


def test_ecs_runs_before_before_draw_with_before_after_ecs_hooks() -> None:
    events: list[str] = []

    class Recorder(Plugin):
        name = "ecs-recorder"

        def before_ecs(self, context) -> None:
            del context
            events.append("before_ecs")

        def after_ecs(self, context) -> None:
            del context
            events.append("after_ecs")

        def before_draw(self, context) -> None:
            del context
            events.append("before_draw")

    @ecs.udf(side_effects=True)
    def mark_system_run() -> None:
        events.append("system")

    @ecs.system
    def marker_system() -> ecs.Action:
        return cast(ecs.Action, mark_system_run())

    class EcsLifecycleSketch(Sketch):
        def setup(self) -> None:
            self.create_canvas(8, 8)
            self.add_system(marker_system)

        def draw(self) -> None:
            events.append("draw")
            self.no_loop()

    clear_plugins()
    try:
        install_plugin(Recorder())
        EcsLifecycleSketch().run(max_frames=1)
    finally:
        clear_plugins()

    assert events == ["before_ecs", "system", "after_ecs", "before_draw", "draw"]
