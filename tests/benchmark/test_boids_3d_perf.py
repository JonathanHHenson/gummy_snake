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
TARGET_FPS = 160.0
PHASES = ("full", "simulation", "mesh")
BENCHMARK_MODE = os.environ.get("GUMMY_BOIDS_BENCHMARK_MODE", "headless")

LOCKED_BOIDS_3D_CONSTANTS: dict[str, object] = {
    "WIDTH": 960,
    "HEIGHT": 540,
    "TARGET_FPS": 60,
    "FOV_Y": 3.141592653589793 / 3.1,
    "CAMERA_DISTANCE": 800.0,
    "CAMERA_HEIGHT": -170.0,
    "POINT_LIGHT_POSITION": (230.0, -170.0, 320.0),
    "FPS_SMOOTHING": 0.12,
    "BOID_COUNT": 3_000,
    "WORLD_X": 760.0,
    "WORLD_Y": 430.0,
    "WORLD_Z": 620.0,
    "BOUND_MARGIN": 120.0,
    "BOUND_FORCE": 0.045,
    "PERCEPTION_RADIUS": 60.0,
    "SEPARATION_RADIUS": 40.0,
    "MAX_SPEED": 5.4,
    "MIN_SPEED": 2.0,
    "MAX_FORCE": 0.075,
    "ALIGNMENT_WEIGHT": 1.0,
    "COHESION_WEIGHT": 0.7,
    "SEPARATION_WEIGHT": 1.7,
    "COHESION_SPEED_FACTOR": 0.82,
    "PALETTE": (
        (95, 185, 255, 220),
        (105, 238, 192, 215),
        (255, 216, 118, 215),
        (255, 140, 145, 212),
        (185, 145, 255, 218),
    ),
    "BOID_MODEL_LENGTH": 12.0,
    "BOID_MODEL_WIDTH": 5.0,
    "BOID_MODEL_HEIGHT": 4.2,
    "BOID_DRAW_FIELDS": ("x", "y", "z", "vx", "vy", "vz"),
    "BOID_STATE_FIELDS": ("x", "y", "z", "vx", "vy", "vz", "bucket"),
}

LOCKED_BOIDS_3D_CONSTANTS_JSON = json.dumps(LOCKED_BOIDS_3D_CONSTANTS)

CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import importlib
    import json
    import platform
    import sys
    import time

    from gummysnake.ecs.world import EcsWorld

    phase = sys.argv[1]
    frames = int(sys.argv[2])
    mode = sys.argv[3]
    locked_constants = json.loads(sys.argv[4])
    target_fps = float(sys.argv[5])
    headless = mode != "interactive"

    sys.argv = [
        "examples/09_performance/boids_3d.py",
        "--frames",
        str(frames),
        "--no-save",
        "--headless" if headless else "--interactive",
    ]
    boids = importlib.import_module("examples.09_performance.boids_3d")

    def _apply_locked_benchmark_constants() -> None:
        tuple_constants = {
            "BOID_DRAW_FIELDS",
            "BOID_STATE_FIELDS",
            "POINT_LIGHT_POSITION",
        }
        for name, value in locked_constants.items():
            if name == "PALETTE":
                value = tuple(tuple(color) for color in value)
            elif name in tuple_constants:
                value = tuple(value)
            setattr(boids, name, value)
        boids._boid_bucket_indices = [[] for _ in boids.PALETTE]
        boids._boid_model_cache = None
        steer_toward = getattr(boids, "_expr_steer_toward", None)
        if steer_toward is not None:
            kwdefaults = dict(getattr(steer_toward, "__kwdefaults__", None) or {})
            kwdefaults["speed"] = boids.MAX_SPEED
            steer_toward.__kwdefaults__ = kwdefaults

    _apply_locked_benchmark_constants()

    def _prepare_boids_world(add_system: bool = True):
        world = EcsWorld()
        if add_system:
            world.add_system(boids.simulate_boids)
        for state in boids._seed_boids():
            world.add_entity(state, tags=[boids.BOID_TAG])
        return world

    def _boid_states_from_world(world):
        return list(
            world.iter_component_fields(
                boids.BoidState,
                *boids.BOID_STATE_FIELDS,
                tags=[boids.BOID_TAG],
            )
        )

    def _renderer_counters():
        try:
            return boids.gs.renderer_performance_counters()
        except Exception:
            return {}

    if phase == "simulation":
        world = _prepare_boids_world()
        start = time.perf_counter()
        for _ in range(frames):
            world.run_pre_draw_systems()
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": target_fps,
            "backend_mode": "ecs-world",
            "boid_count": boids.BOID_COUNT,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metrics": {"ecs": world.diagnostics()},
        }
    elif phase == "mesh":
        world = _prepare_boids_world(add_system=False)
        rows = _boid_states_from_world(world)
        boids._boid_model()
        start = time.perf_counter()
        for _ in range(frames):
            for _x, _y, _z, vx, vy, vz, _bucket in rows:
                boids._orientation_quaternion(vx, vy, vz)
        elapsed = time.perf_counter() - start
        payload = {
            "phase": phase,
            "frames": frames,
            "elapsed": elapsed,
            "fps": frames / max(elapsed, 1e-9),
            "target_fps": target_fps,
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
            boids.draw.function()
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
            "target_fps": target_fps,
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
            [
                sys.executable,
                "-c",
                CHILD_CODE,
                phase,
                str(frames),
                BENCHMARK_MODE,
                LOCKED_BOIDS_3D_CONSTANTS_JSON,
                str(TARGET_FPS),
            ],
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
