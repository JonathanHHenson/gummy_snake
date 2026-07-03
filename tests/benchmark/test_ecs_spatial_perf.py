from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from gummysnake import ecs
from gummysnake.ecs.spatial import SpatialAlgorithm
from gummysnake.ecs.world import EcsWorld


@dataclass
class Position:
    x: float
    y: float
    z: float


@dataclass
class NeighborCount:
    value: float


def _entity_count(default: int = 900) -> int:
    raw = os.environ.get("GUMMY_ECS_SPATIAL_BENCHMARK_ENTITIES")
    return int(raw) if raw is not None else default


def _diag_int(diagnostics: dict[str, object], key: str, default: int = 0) -> int:
    value = diagnostics.get(key, default)
    if isinstance(value, bool | int | float | str):
        return int(value)
    return default


def _seed_grid(world: EcsWorld, count: int, *, dimensions: int) -> None:
    side = max(1, int(count**0.5))
    for index in range(count):
        x = float((index % side) * 3)
        y = float((index // side) * 3)
        z = float((index % 17) * 2) if dimensions == 3 else 0.0
        world.add_entity(Position(x, y, z), NeighborCount(0.0))


def _seed_clustered(world: EcsWorld, count: int, *, dimensions: int) -> None:
    for index in range(count):
        cluster = index % 5
        local = index // 5
        x = float(cluster * 90 + (local % 11) * 1.7)
        y = float(cluster * 30 + ((local // 11) % 11) * 1.7)
        z = float(((local // 121) % 11) * 1.7) if dimensions == 3 else 0.0
        world.add_entity(Position(x, y, z), NeighborCount(0.0))


def _spatial_system(
    algorithm_factory: Callable[[], SpatialAlgorithm],
    *,
    dimensions: int,
    radius: float,
):
    @ecs.system
    def count_neighbors(entity: ecs.Query[Position, NeighborCount]) -> None:
        position = (
            ecs.spatial.point3(entity[Position].x, entity[Position].y, entity[Position].z)
            if dimensions == 3
            else ecs.spatial.point2(entity[Position].x, entity[Position].y)
        )
        neighbors = ecs.spatial.neighbors(
            entity,
            position=position,
            radius=radius,
            algorithm=algorithm_factory(),
            include_self=False,
            allow_fallback=False,
        )
        entity[NeighborCount].value.set_to(neighbors.count())

    return count_neighbors


def _run_spatial_case(
    algorithm_factory: Callable[[], SpatialAlgorithm],
    seed: Callable[[EcsWorld, int], None],
    *,
    dimensions: int,
    frames: int = 3,
) -> tuple[float, dict[str, object]]:
    world = EcsWorld()
    count = _entity_count()
    seed(world, count)
    world.add_system(
        _spatial_system(algorithm_factory, dimensions=dimensions, radius=8.0),
        name="count_neighbors",
    )
    start = time.perf_counter()
    for _ in range(frames):
        world.run_pre_draw_systems()
    elapsed = time.perf_counter() - start
    return elapsed, world.diagnostics()


@pytest.mark.benchmark
@pytest.mark.parametrize(
    ("name", "algorithm_factory", "seed", "dimensions"),
    [
        (
            "hash_grid_uniform_2d",
            lambda: ecs.spatial.HashGrid(cell_size=8.0, dimensions=2),
            lambda world, count: _seed_grid(world, count, dimensions=2),
            2,
        ),
        (
            "quadtree_clustered_2d",
            lambda: ecs.spatial.Quadtree(
                bounds=ecs.spatial.Bounds2D(-20.0, -20.0, 600.0, 600.0), capacity=16
            ),
            lambda world, count: _seed_clustered(world, count, dimensions=2),
            2,
        ),
        (
            "hilbert_clustered_2d",
            lambda: ecs.spatial.HilbertCurve(
                bounds=ecs.spatial.Bounds2D(-20.0, -20.0, 600.0, 600.0), bits=12
            ),
            lambda world, count: _seed_clustered(world, count, dimensions=2),
            2,
        ),
        (
            "octree_sparse_3d",
            lambda: ecs.spatial.Octree(
                bounds=ecs.spatial.Bounds3D(-20.0, -20.0, -20.0, 600.0, 600.0, 600.0),
                capacity=16,
            ),
            lambda world, count: _seed_grid(world, count, dimensions=3),
            3,
        ),
    ],
)
def test_ecs_spatial_backend_benchmark_matrix(
    name: str,
    algorithm_factory: Callable[[], SpatialAlgorithm],
    seed: Callable[[EcsWorld, int], None],
    dimensions: int,
) -> None:
    elapsed, diagnostics = _run_spatial_case(
        algorithm_factory,
        seed,
        dimensions=dimensions,
    )
    assert elapsed > 0.0
    assert _diag_int(diagnostics, "ecs_spatial_indexes_built") >= 1
    assert _diag_int(diagnostics, "ecs_spatial_index_fallbacks") == 0
    assert _diag_int(diagnostics, "ecs_spatial_candidate_rows") >= _diag_int(
        diagnostics, "ecs_spatial_exact_rows"
    )
    # Printed names make opt-in benchmark logs easy to compare without hard-coding
    # algorithm-specific gates into the test suite.
    print(
        f"{name}: elapsed={elapsed:.4f}s "
        f"built={_diag_int(diagnostics, 'ecs_spatial_indexes_built')} "
        f"reused={_diag_int(diagnostics, 'ecs_spatial_index_reuses')} "
        f"incremental={_diag_int(diagnostics, 'ecs_spatial_index_incremental_updates')} "
        f"chunks={_diag_int(diagnostics, 'ecs_spatial_parallel_chunks')} "
        f"workers={_diag_int(diagnostics, 'ecs_spatial_parallel_workers')}"
    )


@pytest.mark.benchmark
def test_ecs_spatial_cache_allocation_and_incremental_benchmark() -> None:
    world = EcsWorld()
    count = _entity_count()
    _seed_grid(world, count, dimensions=2)
    world.add_system(
        _spatial_system(
            lambda: ecs.spatial.HashGrid(cell_size=8.0, dimensions=2),
            dimensions=2,
            radius=8.0,
        ),
        name="hash_grid_neighbors",
    )
    world.run_pre_draw_systems()
    first = world.diagnostics()
    if (
        _diag_int(first, "ecs_spatial_index_full_rebuilds") == 0
        and _diag_int(first, "ecs_spatial_index_cache_len") == 0
    ):
        pytest.skip("spatial cache counters require the rebuilt gummy_canvas ECS bridge")
    world.run_pre_draw_systems()
    second = world.diagnostics()

    assert _diag_int(first, "ecs_spatial_index_full_rebuilds") >= 1
    assert _diag_int(second, "ecs_spatial_index_reuses") >= 1
    assert _diag_int(second, "ecs_spatial_index_cache_len") >= 1
    assert _diag_int(second, "ecs_spatial_candidate_buffer_growths") >= 0
    assert _diag_int(second, "ecs_spatial_thread_scratch_reuses") >= 0

    first_entity = next(iter(world.iter_entities(Position, NeighborCount)))
    first_entity[Position].x += 0.25
    world.run_pre_draw_systems()
    moved = world.diagnostics()
    assert _diag_int(moved, "ecs_spatial_index_incremental_updates") >= 1
    print(
        "hash_grid_cache: "
        f"built={_diag_int(moved, 'ecs_spatial_indexes_built')} "
        f"full={_diag_int(moved, 'ecs_spatial_index_full_rebuilds')} "
        f"incremental={_diag_int(moved, 'ecs_spatial_index_incremental_updates')} "
        f"candidate_growths={_diag_int(moved, 'ecs_spatial_candidate_buffer_growths')} "
        f"scratch_reuses={_diag_int(moved, 'ecs_spatial_thread_scratch_reuses')}"
    )
