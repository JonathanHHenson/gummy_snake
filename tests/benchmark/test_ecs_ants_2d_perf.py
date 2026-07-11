"""ECS ant-colony benchmark using the shared example-domain scenario core."""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass

import pytest

from examples.support.ant_colony.configuration import ANTS_PER_COLONY
from tests.benchmark.ant_colony_benchmark.measurement import seed_world

FRAMES = int(os.environ.get("GUMMY_ANTS_BENCHMARK_FRAMES", "120"))
WARMUP_FRAMES = int(os.environ.get("GUMMY_ANTS_BENCHMARK_WARMUP_FRAMES", "20"))
REPEATS = int(os.environ.get("GUMMY_ANTS_BENCHMARK_REPEATS", "1"))
TARGET_FPS = 100.0
BENCHMARK_ID = "ecs_ants_2d_voxel_colony_v1"


@dataclass(frozen=True)
class BenchmarkSummary:
    samples: tuple[float, ...]
    metadata: dict[str, object]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)

    @property
    def min_fps(self) -> float:
        return min(self.samples)

    @property
    def max_fps(self) -> float:
        return max(self.samples)

    @property
    def meets_target(self) -> bool:
        return self.mean_fps >= TARGET_FPS


def _run_benchmark() -> BenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(REPEATS):
        world, counts = seed_world()
        handles = tuple(scheduled.physical_plan_handle for scheduled in world._systems)
        if any(handle is None for handle in handles):
            raise AssertionError("ants benchmark systems did not compile to Rust physical plans")
        compiled_handles = tuple(handle for handle in handles if handle is not None)
        execute_batch = getattr(world._rust, "execute_compiled_plans_sequential", None)
        if not callable(execute_batch):
            raise AssertionError(
                "ants benchmark requires Rust sequential compiled-plan batch support"
            )
        for _frame in range(WARMUP_FRAMES):
            execute_batch(compiled_handles, False)
        start = time.perf_counter()
        for _frame in range(FRAMES):
            execute_batch(compiled_handles, False)
        elapsed = time.perf_counter() - start
        diagnostics = world.diagnostics()
        diagnostics.update(
            {
                "ecs_physical_system_runs": (WARMUP_FRAMES + FRAMES) * len(compiled_handles),
                "benchmark_mode": "compiled_rust_plans_sequential_batch",
                "compiled_plan_count": len(compiled_handles),
            }
        )
        samples.append(FRAMES / max(elapsed, 1.0e-9))
        metadata = {
            "counts": counts,
            "diagnostics": diagnostics,
            "elapsed": elapsed,
            "frames": FRAMES,
            "target_fps": TARGET_FPS,
            "warmup_frames": WARMUP_FRAMES,
        }
    return BenchmarkSummary(tuple(samples), metadata)


@pytest.mark.benchmark
def test_ecs_ants_2d_voxel_colony_benchmark() -> None:
    summary = _run_benchmark()
    print(
        "ecs_ants_2d_benchmark: "
        f"mean_fps={summary.mean_fps:.2f} min_fps={summary.min_fps:.2f} "
        f"max_fps={summary.max_fps:.2f} target_fps={TARGET_FPS:.2f} "
        f"meets_target={summary.meets_target} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    counts = summary.metadata["counts"]
    diagnostics = summary.metadata["diagnostics"]
    assert isinstance(counts, dict)
    assert isinstance(diagnostics, dict)
    assert summary.mean_fps > 0.0
    assert counts["ants"] == ANTS_PER_COLONY * 2
    assert counts["food_voxels"] > 0
    assert counts["walls"] > 0
    assert counts["pheromone_voxels"] > 0
    assert int(diagnostics.get("ecs_physical_system_runs", 0)) >= FRAMES
    assert int(diagnostics.get("ecs_udf_calls", 0)) == 0
    assert summary.meets_target
