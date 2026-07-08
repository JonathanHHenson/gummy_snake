from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from benchmark_helpers import run_json_subprocess

CHILD_RUNNER = Path(__file__).with_name("temporary_ecs_perf_child.py")
FRAMES = int(os.environ.get("GUMMY_TEMP_ECS_BENCHMARK_FRAMES", "120"))
REPEATS = int(os.environ.get("GUMMY_TEMP_ECS_BENCHMARK_REPEATS", "1"))
BENCHMARK_MODE = os.environ.get("GUMMY_TEMP_ECS_BENCHMARK_MODE", "headless")
MIN_MEAN_FPS = 120.0

SCENES = (
    "rust_2d_primitives_branching",
    "python_systems_udfs_sprites",
    "structural_churn_tags_components",
    "spatial_events_for_each_stress",
    "webgl_3d_ecs_primitives_models",
)


@dataclass(frozen=True)
class TemporaryEcsBenchmarkSummary:
    scene: str
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


def _run_scene(
    scene: str, *, frames: int = FRAMES, repeats: int = REPEATS
) -> TemporaryEcsBenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(repeats):
        payload = run_json_subprocess(
            [sys.executable, str(CHILD_RUNNER), scene, str(frames), BENCHMARK_MODE],
            f"temporary ECS benchmark scene {scene!r}",
        )
        samples.append(float(payload["fps"]))
        metadata = {
            "backend_mode": payload["backend_mode"],
            "elapsed": payload["elapsed"],
            "frames": payload["frames"],
            "metrics": payload["metrics"],
            "phase": payload["phase"],
            "platform": payload["platform"],
            "python": payload["python"],
        }
    return TemporaryEcsBenchmarkSummary(scene=scene, samples=tuple(samples), metadata=metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("scene", SCENES)
def test_temporary_ecs_example_benchmark(scene: str) -> None:
    summary = _run_scene(scene)
    print(
        f"temporary_ecs_benchmark {summary.scene}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps >= MIN_MEAN_FPS
