# pyright: reportFunctionMemberAccess=false
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
# pyright: reportUnknownMemberType=false
from __future__ import annotations

from tests.helpers.ecs_fixtures import *  # noqa: F403


def test_rust_udf_expands_to_physical_expression_plan() -> None:
    world = EcsWorld()
    world.add_entity(Position(3, 0))

    @ecs.udf_plan
    def hypotenuse(value: ecs.Expression[float]) -> ecs.Expression[float]:
        return (value * value + 1.0).sqrt()

    @ecs.system_plan
    def udf_expression_system(entity: ecs.Query[Position]) -> None:
        entity[Position].x.set_to(cast(ecs.Expression, hypotenuse(entity[Position].x)))

    world.add_system(udf_expression_system)
    world.run_pre_draw_systems()

    assert world.get_entity(Position)[Position].x == pytest.approx(10.0**0.5)
    assert world.diagnostics().get("ecs_udf_calls", 0) == 0


def test_system_plan_explain_describes_action_tree() -> None:
    @ecs.system_plan(parallel=True)
    def explained(entity: ecs.Query[Position, Velocity]) -> None:
        entity[Position].x.increase_by(entity[Velocity].dx)
        with ecs.conditional():
            with ecs.when(entity[Position].x > 10):
                entity[Velocity].dy.set_to(1)
            with ecs.otherwise():
                entity[Velocity].dy.set_to(0)

    explanation = explained.explain()
    assert "do_in_parallel" in explanation
    assert "set Position.x" in explanation
    assert "Position.x <-" in explanation
    assert "when_chain" in explanation
    assert "when[1]" in explanation
    assert "otherwise" in explanation


def test_system_plan_explain_describes_spatial_relations() -> None:
    @ecs.system_plan
    def explained(entity: ecs.Query[Position]) -> None:
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
        with ecs.conditional(), ecs.when(nearby.any()):
            entity.ctx[Position].y.set_to(nearby.count())

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

    @ecs.system_plan
    def bad() -> ecs.Action:
        return ecs.do_in_order().plan()  # type: ignore[return-value]

    with pytest.raises(SystemPlanError, match="returned SystemPlan"):
        world.add_system(bad)


def test_context_system_migration_and_active_session_errors() -> None:
    world = EcsWorld()
    proxy = ecs.QueryProxy("entity", ecs.Query[Position])

    with pytest.raises(SystemPlanError, match="active @ecs.system_plan plan-build session"):
        proxy[Position].x.set_to(1)

    @ecs.system_plan
    def old_return(entity: ecs.Query[Position]) -> ecs.Action:
        return ecs.set(entity[Position].x, 1)

    with pytest.raises(SystemPlanError, match="returned an ecs.Action"):
        world.add_system(old_return)

    @ecs.system_plan
    def read_only(counter: ecs.Res[Counter]) -> None:
        counter[Counter].value.set_to(1)

    world.set_resource(Counter(0))
    with pytest.raises(SystemPlanError, match="read-only"):
        world.add_system(read_only)


def test_without_query_term_and_explicit_python_system_diagnostics() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0))
    world.add_entity(Position(10, 0), Velocity(1, 0))

    @ecs.system_plan
    def mark_stationary(entity: ecs.Query[Position, ecs.Without[Velocity]]) -> None:
        entity[Position].y.set_to(5)

    @ecs.system
    def collect_positions(entities: ecs.Query[Position]) -> None:
        for entity in entities:
            entity[Position].x += 1

    world.add_system(mark_stationary)
    world.add_system(collect_positions, after=["mark_stationary"])
    world.run_pre_draw_systems()

    positions = sorted(
        (entity[Position].x, entity[Position].y) for entity in world.iter_entities(Position)
    )
    assert positions == [(1, 5), (11, 0)]
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_python_system_calls"] == 1
    assert diagnostics["ecs_python_system_barriers"] == 1
    assert diagnostics["ecs_python_system_entities_materialized"] == 2


def test_python_udf_and_system_metadata_validation() -> None:
    with pytest.raises(SystemPlanError, match="unknown parameter"):

        @ecs.udf(mutations={"missing": {ecs.EntityMutation[Position]()}})
        def bad_udf(items: Iterable[ecs.Entity[Position]]) -> None:
            del items

    with pytest.raises(SystemPlanError, match="unknown parameter"):

        @ecs.system(queries={"missing": ecs.Query[Position]})
        def bad_system(entities: object) -> None:
            del entities

    with pytest.raises(SystemPlanError, match="must be ecs.Query"):

        @ecs.system(queries={"entities": object()})
        def bad_query_metadata(entities: object) -> None:
            del entities


def test_grouped_value_aggregates_count_sum_min_max_mean() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[PLATFORM])
    world.add_entity(Position(1, 0), tags=[HERO])
    world.add_entity(Position(2, 0), tags=[HERO])
    world.add_entity(Position(20, 0), tags=[HERO])
    world.set_resource(Counter(0))

    @ecs.system_plan
    def aggregate_system(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position],
        hero: ecs.Query[ecs.Tag[HERO], Position],
        counter: ecs.ResMut[Counter],
    ) -> None:
        near = (hero[Position].x - platform[Position].x).abs() <= 5
        grouped = near.group_by(platform)
        counter[Counter].value.set_to(grouped.count())
        platform[Position].x.set_to(grouped.sum(hero[Position].x))
        platform[Position].y.set_to(grouped.mean(hero[Position].x, default=0.0))

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

    @ecs.system_plan
    def sum_trail(entity: ecs.Query[Trail], counter: ecs.ResMut[Counter]) -> None:
        with ecs.for_each(entity[Trail].samples) as sample:
            counter[Counter].value.increase_by(sample)

    world.add_system(sum_trail)
    world.run_pre_draw_systems()

    assert world.get_resource(Counter).value == 7


def test_spatial_hash_neighbors_and_join_aggregates() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), tags=[HERO])
    world.add_entity(Position(3, 4), tags=[HERO])
    world.add_entity(Position(20, 0), tags=[HERO])
    world.add_entity(Position(1, 1), Velocity(0, 0), tags=[PLATFORM])

    @ecs.system_plan
    def neighbor_system(hero: ecs.Query[ecs.Tag[HERO], Position]) -> None:
        pos = ecs.spatial.point2(hero[Position].x, hero[Position].y)
        neighbors = ecs.spatial.neighbors(
            hero,
            position=pos,
            radius=6.0,
            algorithm=ecs.spatial.HashGrid(cell_size=6.0),
            include_self=False,
            allow_fallback=False,
        )
        hero[Position].y.set_to(neighbors.count())

    @ecs.system_plan
    def platform_sensor(
        platform: ecs.Query[ecs.Tag[PLATFORM], Position, Velocity],
        hero: ecs.Query[ecs.Tag[HERO], Position],
    ) -> None:
        nearby = ecs.spatial.join(
            platform,
            hero,
            origin_position=ecs.spatial.point2(platform[Position].x, platform[Position].y),
            target_position=ecs.spatial.point2(hero[Position].x, hero[Position].y),
            radius=4.0,
            algorithm=ecs.spatial.HashGrid(cell_size=4.0),
            allow_fallback=False,
        )
        with ecs.conditional(), ecs.when(nearby.any()):
            platform.ctx[Velocity].dx.set_to(nearby.count())

    world.add_system(neighbor_system)
    world.add_system(platform_sensor)
    world.run_pre_draw_systems()

    heroes = sorted(
        (entity[Position].x, entity[Position].y)
        for entity in world.iter_entities(Position, tags=[HERO])
    )
    assert heroes == [(0, 1), (3, 1), (20, 0)]
    assert world.get_entity(Velocity, tags=[PLATFORM])[Velocity].dx == 2
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_spatial_index_cache_len"] >= 2
    assert diagnostics["ecs_spatial_indexes_built"] <= 2
    assert diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0


def test_spatial_relations_share_target_index_across_sensor_origins() -> None:
    world = EcsWorld()
    world.add_entity(Position(0, 0), SensorOrigin(1, 0), Velocity(0, 0), tags=[HERO])
    world.add_entity(Position(0, 0), tags=[PLATFORM])
    world.add_entity(Position(1, 0), tags=[PLATFORM])

    @ecs.system_plan(parallel=True)
    def two_sensor_system(
        hero: ecs.Query[ecs.Tag[HERO], Position, SensorOrigin, Velocity],
        marker: ecs.Query[ecs.Tag[PLATFORM], Position],
    ) -> None:
        target = ecs.spatial.point2(marker[Position].x, marker[Position].y)
        centered = ecs.spatial.join(
            hero,
            marker,
            origin_position=ecs.spatial.point2(hero[Position].x, hero[Position].y),
            target_position=target,
            radius=0.25,
            algorithm=ecs.spatial.HashGrid(cell_size=1.0),
            allow_fallback=False,
            name="center_marker_sensor",
        )
        offset = ecs.spatial.join(
            hero,
            marker,
            origin_position=ecs.spatial.point2(hero[SensorOrigin].x, hero[SensorOrigin].y),
            target_position=target,
            radius=0.25,
            algorithm=ecs.spatial.HashGrid(cell_size=1.0),
            allow_fallback=False,
            name="offset_marker_sensor",
        )
        hero[Velocity].dx.set_to(centered.count())
        hero[Velocity].dy.set_to(offset.count())

    world.add_system(two_sensor_system)
    world.run_pre_draw_systems()

    hero = world.get_entity(Position, Velocity, tags=[HERO])
    assert hero[Velocity].dx == 1
    assert hero[Velocity].dy == 1
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_spatial_index_cache_len"] == 1
    assert diagnostics["ecs_spatial_indexes_built"] <= 1
    assert diagnostics["ecs_spatial_algorithm_hash_grid"] == 1
    assert diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0


def test_spatial_tree_algorithms_execute_in_rust_without_fallbacks() -> None:
    @ecs.system_plan
    def tree_system(entity: ecs.Query[Position]) -> None:
        pos = ecs.spatial.point2(entity[Position].x, entity[Position].y)
        relation = ecs.spatial.neighbors(
            entity,
            position=pos,
            radius=4.0,
            algorithm=ecs.spatial.Quadtree(ecs.spatial.Bounds2D(-10, -10, 10, 10)),
        )
        entity[Position].y.set_to(relation.count())

    world = EcsWorld()
    world.add_entity(Position(0, 0))
    world.add_system(tree_system)
    world.run_pre_draw_systems()
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_physical_system_runs"] == 1
    assert diagnostics["ecs_spatial_algorithm_quadtree"] == 1
    assert diagnostics["ecs_spatial_index_cache_len"] == 1
    assert diagnostics["ecs_spatial_indexes_built"] <= 1
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
