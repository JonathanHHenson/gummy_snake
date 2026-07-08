from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

import pytest

from gummysnake import ecs
from gummysnake.ecs.world import EcsWorld


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


@dataclass
class Counter:
    value: int


@pytest.mark.benchmark
def test_ecs_storage_query_and_executor_smoke_benchmark() -> None:
    samples: list[float] = []
    entity_count = 2_000
    for _ in range(3):
        world = EcsWorld()
        start = time.perf_counter()
        for index in range(entity_count):
            tags = ["even"] if index % 2 == 0 else ["odd"]
            world.add_entity(Position(float(index), 0.0), Velocity(1.0, 0.5), tags=tags)
        assert (
            len(tuple(world.iter_entities(Position, Velocity, tags=["even"]))) == entity_count // 2
        )
        samples.append(time.perf_counter() - start)
    mean_entities_per_second = entity_count / statistics.mean(samples)
    assert mean_entities_per_second > 10_000


@pytest.mark.benchmark
def test_ecs_system_scheduler_smoke_benchmark() -> None:
    world = EcsWorld()
    entity_count = 2_000
    for index in range(entity_count):
        world.add_entity(Position(float(index), 0.0), Velocity(1.0, 0.5))

    @ecs.system_plan
    def move(entity: ecs.Query[Position, Velocity]) -> None:
        entity[Position].x.increase_by(entity[Velocity].dx)
        entity[Position].y.increase_by(entity[Velocity].dy)

    world.add_system(move, name="move")
    start = time.perf_counter()
    world.run_pre_draw_systems()
    elapsed = time.perf_counter() - start
    first = next(iter(world.iter_entities(Position, Velocity)))
    assert first[Position].x == 1.0
    assert entity_count / max(elapsed, 1e-9) > 5_000


@pytest.mark.benchmark
def test_ecs_spatial_hash_grid_smoke_benchmark() -> None:
    world = EcsWorld()
    side = 32
    for y in range(side):
        for x in range(side):
            world.add_entity(Position(float(x * 4), float(y * 4)))

    @ecs.system_plan
    def neighbors(entity: ecs.Query[Position]) -> None:
        point = ecs.spatial.point2(entity[Position].x, entity[Position].y)
        nearby = ecs.spatial.neighbors(
            entity,
            position=point,
            radius=5.0,
            algorithm=ecs.spatial.HashGrid(cell_size=8.0),
            include_self=False,
            allow_fallback=False,
        )
        entity[Position].y.set_to(nearby.count())

    world.add_system(neighbors)
    start = time.perf_counter()
    world.run_pre_draw_systems()
    elapsed = time.perf_counter() - start
    diagnostics = world.diagnostics()
    assert diagnostics["ecs_spatial_indexes_built"] >= 1
    assert diagnostics.get("ecs_spatial_index_fallbacks", 0) == 0
    # This is a smoke/baseline benchmark for the current compatibility executor,
    # not the final Rust physical executor target.
    assert elapsed < 5.0
