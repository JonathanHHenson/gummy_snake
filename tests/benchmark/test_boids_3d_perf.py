from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRAMES = 120
REPEATS = 1
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
        boids._prepare_boids()
        start = time.perf_counter()
        for _ in range(frames):
            boids._rebuild_grid()
            for index in range(boids.BOID_COUNT):
                boids._update_boid(index)
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": 120.0,
            "backend_mode": "none",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {},
        }
    elif phase == "mesh":
        boids._prepare_boids()
        start = time.perf_counter()
        for _ in range(frames):
            for indices in boids.bucket_indices:
                boids._flock_model(indices)
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": 120.0,
            "backend_mode": "none",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {},
        }
    elif phase == "full":
        state = {"start": 0.0, "metrics": {}}

        def setup() -> None:
            boids.setup()
            boids.gs.frame_rate(10_000)
            state["start"] = time.perf_counter()

        def draw() -> None:
            boids.draw()
            if boids.gs.frame_count() == frames - 1:
                state["metrics"] = _renderer_counters()

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
            "metrics": state["metrics"],
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
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, phase, str(frames), BENCHMARK_MODE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"boids benchmark phase {phase!r} failed\n{detail}")
        payload = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
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
