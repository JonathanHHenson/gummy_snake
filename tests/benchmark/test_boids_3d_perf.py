from __future__ import annotations

import json
import os
import statistics
import sys
import textwrap
from dataclasses import dataclass

import pytest
from benchmark_helpers import run_json_subprocess

FRAMES = int(os.environ.get("GUMMY_BOIDS_BENCHMARK_FRAMES", "3"))
REPEATS = int(os.environ.get("GUMMY_BOIDS_BENCHMARK_REPEATS", "1"))
TARGET_FPS = 120.0
PHASES = ("full", "simulation", "mesh")
BENCHMARK_MODE = os.environ.get("GUMMY_BOIDS_BENCHMARK_MODE", "headless")

CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import importlib
    import json
    import platform
    import sys
    import time

    phase = sys.argv[1]
    frames = int(sys.argv[2])
    mode = sys.argv[3]
    headless = mode != "interactive"

    sys.argv = [
        "examples/09_performance/boids_3d.py",
        "--frames",
        str(frames),
        "--no-save",
        "--headless" if headless else "--interactive",
    ]
    boids = importlib.import_module("examples.09_performance.boids_3d")

    def _renderer_counters():
        try:
            return boids.gs.renderer_performance_counters()
        except Exception:
            return {}

    if phase == "simulation":
        world = boids._prepare_boids_world()
        start = time.perf_counter()
        for _ in range(frames):
            world.run_pre_draw_systems()
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": 120.0,
            "backend_mode": "ecs-world",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {"ecs": world.diagnostics()},
        }
    elif phase == "mesh":
        world = boids._prepare_boids_world(add_system=False)
        state_buckets = boids._bucket_states(boids._boid_states_from_world(world))
        boids._boid_model()
        start = time.perf_counter()
        for _ in range(frames):
            for bucket_states in state_buckets:
                boids._boid_transform_keys(bucket_states)
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": 120.0,
            "backend_mode": "ecs-world",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {"ecs": world.diagnostics()},
        }
    elif phase == "full":
        state = {"start": 0.0, "metrics": {}, "ecs_metrics": {}}

        def setup() -> None:
            boids.setup()
            boids.gs.frame_rate(10_000)
            state["start"] = time.perf_counter()

        def draw() -> None:
            boids.draw()
            if boids.gs.frame_count() == frames - 1:
                state["metrics"] = _renderer_counters()
                state["ecs_metrics"] = boids.gs.ecs_diagnostics()

        boids.gs.run(setup=setup, draw=draw, headless=headless, max_frames=frames)
        elapsed = time.perf_counter() - state["start"]
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": 120.0,
            "backend_mode": "headless" if headless else "interactive",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {"renderer": state["metrics"], "ecs": state["ecs_metrics"]},
        }
    else:
        raise ValueError(f"unknown boids benchmark phase: {phase}")

    print(json.dumps(payload, sort_keys=True))
    """
)


@dataclass(frozen=True)
class BoidsBenchmarkSummary:
    phase: str
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


def _run_phase(
    phase: str, *, frames: int = FRAMES, repeats: int = REPEATS
) -> BoidsBenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(repeats):
        payload = run_json_subprocess(
            [sys.executable, "-c", CHILD_CODE, phase, str(frames), BENCHMARK_MODE],
            f"boids benchmark phase {phase!r}",
        )
        samples.append(float(payload["fps"]))
        metadata = {
            "backend_mode": payload["backend_mode"],
            "boid_count": payload["boid_count"],
            "elapsed": payload["elapsed"],
            "frames": payload["frames"],
            "metrics": payload["metrics"],
            "platform": payload["platform"],
            "python": payload["python"],
            "target_fps": payload["target_fps"],
        }
    return BoidsBenchmarkSummary(phase=phase, samples=tuple(samples), metadata=metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("phase", PHASES)
def test_boids_3d_benchmark_baseline(phase: str) -> None:
    summary = _run_phase(phase)
    print(
        f"boids_3d_benchmark {summary.phase}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f} "
        f"target_fps={TARGET_FPS:.2f} meets_target={summary.meets_target} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps > 0.0
