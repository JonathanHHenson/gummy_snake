from __future__ import annotations

from dataclasses import dataclass

import pytest

from gummysnake import ecs
from gummysnake.ecs.world import EcsWorld

pytestmark = pytest.mark.stress


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


def _spatial_system(radius: float):
    @ecs.system
    def count_neighbors(entity: ecs.Query[Position]) -> ecs.Action:
        point = ecs.spatial.point2(entity[Position].x, entity[Position].y)
        neighbors = ecs.spatial.neighbors(
            entity,
            position=point,
            radius=radius,
            algorithm=ecs.spatial.HashGrid(cell_size=max(1.0, radius)),
            include_self=False,
            allow_fallback=False,
        )
        return ecs.set(entity[Position].y, neighbors.count())

    return count_neighbors


def test_ecs_system_churn_releases_spatial_plans_and_keeps_diagnostics_resettable() -> None:
    world = EcsWorld()
    for index in range(128):
        world.add_entity(Position(float(index % 16), float(index // 16)))

    for iteration in range(30):
        handle = world.add_system(_spatial_system(3.0 + iteration % 4), name=f"spatial-{iteration}")
        world.run_pre_draw_systems()
        assert world.diagnostics()["ecs_spatial_indexes_built"] >= 1
        world.remove_system(handle)
        world.reset_diagnostics()
        assert world.diagnostics().get("ecs_spatial_indexes_built", 0) == 0


def test_ecs_entity_churn_keeps_spatial_queries_consistent() -> None:
    world = EcsWorld()
    world.add_system(_spatial_system(4.0), name="neighbors")

    for frame in range(40):
        created = [
            world.add_entity(Position(float(index), float(frame)), Velocity(1.0, 0.0))
            for index in range(32)
        ]
        world.run_pre_draw_systems()
        assert len(tuple(world.iter_entities(Position))) == 32
        for entity in created[::2]:
            world.despawn_entity(entity)
        for entity in list(world.iter_entities(Position)):
            entity[Position].x += 0.25
        for entity in created[1::2]:
            world.despawn_entity(entity)
        assert len(tuple(world.iter_entities(Position))) == 0
