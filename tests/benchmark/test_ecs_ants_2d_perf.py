"""ECS ant-colony benchmark entry point."""

from __future__ import annotations

from tests.benchmark.ant_colony_benchmark_support.benchmark_runner import (
    BenchmarkSummary,
    _run_benchmark,
    test_ecs_ants_2d_voxel_colony_benchmark,
)

__all__ = [
    "BenchmarkSummary",
    "_run_benchmark",
    "test_ecs_ants_2d_voxel_colony_benchmark",
]
