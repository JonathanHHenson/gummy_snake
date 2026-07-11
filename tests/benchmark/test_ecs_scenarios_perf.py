from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from benchmark_helpers import run_json_subprocess

CHILD_RUNNER = Path(__file__).with_name("ecs_scenarios_perf_child.py")
FRAMES = int(os.environ.get("GUMMY_ECS_SCENARIOS_BENCHMARK_FRAMES", "120"))
REPEATS = int(os.environ.get("GUMMY_ECS_SCENARIOS_BENCHMARK_REPEATS", "1"))
BENCHMARK_MODE = os.environ.get("GUMMY_ECS_SCENARIOS_BENCHMARK_MODE", "headless")
MIN_MEAN_FPS = 120.0
BENCHMARK_ID = "ecs_performance_scenarios_v1"
LEGACY_CHILD_RUNNER = Path(__file__).with_name("temporary_ecs_perf_child.py")

SCENES = (
    "rust_2d_primitives_branching",
    "python_systems_udfs_sprites",
    "structural_churn_tags_components",
    "spatial_events_for_each_stress",
    "webgl_3d_ecs_primitives_models",
)


@dataclass(frozen=True)
class EcsScenarioBenchmarkSummary:
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
) -> EcsScenarioBenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(repeats):
        payload = run_json_subprocess(
            [sys.executable, str(CHILD_RUNNER), scene, str(frames), BENCHMARK_MODE],
            f"ECS performance scenario {scene!r}",
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
    return EcsScenarioBenchmarkSummary(scene=scene, samples=tuple(samples), metadata=metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("scene", SCENES)
def test_ecs_performance_scenario_benchmark(scene: str) -> None:
    summary = _run_scene(scene)
    print(
        f"ecs_scenario_benchmark {summary.scene}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps >= MIN_MEAN_FPS


@pytest.mark.benchmark
@pytest.mark.parametrize("scene", SCENES)
def test_legacy_ecs_scenario_child_preserves_payload_contract(scene: str) -> None:
    canonical = run_json_subprocess(
        [sys.executable, str(CHILD_RUNNER), scene, "1", BENCHMARK_MODE],
        f"canonical ECS performance scenario {scene!r}",
    )
    legacy = run_json_subprocess(
        [sys.executable, str(LEGACY_CHILD_RUNNER), scene, "1", BENCHMARK_MODE],
        f"legacy ECS performance scenario {scene!r}",
    )
    assert legacy.keys() == canonical.keys()
    for key in ("scene", "phase", "frames", "backend_mode", "python", "platform"):
        assert legacy[key] == canonical[key]
    assert legacy["metrics"].keys() == canonical["metrics"].keys()
    assert legacy["metrics"]["renderer"].keys() == canonical["metrics"]["renderer"].keys()
    assert legacy["metrics"]["ecs"].keys() == canonical["metrics"]["ecs"].keys()
