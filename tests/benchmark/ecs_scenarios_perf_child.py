from __future__ import annotations

import importlib.util
import json
import platform
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import gummysnake as gs

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = ROOT / "examples" / "09_performance" / "ecs_scenarios"

SCENES = {
    "rust_2d_primitives_branching": EXAMPLE_ROOT / "rust_2d_primitives_branching.py",
    "python_systems_udfs_sprites": EXAMPLE_ROOT / "python_systems_udfs_sprites.py",
    "structural_churn_tags_components": EXAMPLE_ROOT / "structural_churn_tags_components.py",
    "spatial_events_for_each_stress": EXAMPLE_ROOT / "spatial_events_for_each_stress.py",
    "webgl_3d_ecs_primitives_models": EXAMPLE_ROOT / "webgl_3d_ecs_primitives_models.py",
}


def _load_scene(name: str, path: Path, frames: int, headless: bool) -> ModuleType:
    sys.argv = [
        str(path),
        "--frames",
        str(frames),
        "--no-save",
        "--headless" if headless else "--interactive",
    ]
    module_name = f"ecs_scenarios_perf_scene_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load ECS performance scenario {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _flatten_numeric(mapping: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                if isinstance(child_value, bool | int | float):
                    flattened[f"{key}.{child_key}"] = child_value
        elif isinstance(value, bool | int | float):
            flattened[str(key)] = value
    return flattened


def _run_full_scene(scene_name: str, frames: int, headless: bool) -> dict[str, Any]:
    path = SCENES[scene_name]
    scene = _load_scene(scene_name, path, frames, headless)
    original_setup = scene.setup
    original_draw = getattr(scene, "draw", None)
    state: dict[str, Any] = {"start": 0.0}

    def setup() -> None:
        original_setup()
        if original_draw is not None and not callable(original_draw):
            gs.add_system(original_draw)
        gs.frame_rate(10_000)
        gs.reset_renderer_performance_counters()
        gs.reset_ecs_diagnostics()
        state["start"] = time.perf_counter()

    def draw() -> None:
        if callable(original_draw):
            original_draw()

    if original_draw is not None and not callable(original_draw):
        context = gs.run(setup=setup, headless=headless, max_frames=frames)
    else:
        context = gs.run(setup=setup, draw=draw, headless=headless, max_frames=frames)
    elapsed = time.perf_counter() - float(state["start"])
    renderer_metrics = _flatten_numeric(context.renderer_performance_counters())
    ecs_metrics = _flatten_numeric(context.ecs_diagnostics())
    return {
        "scene": scene_name,
        "phase": "full",
        "frames": frames,
        "elapsed": elapsed,
        "fps": frames / max(elapsed, 1.0e-9),
        "backend_mode": "headless" if headless else "interactive",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "metrics": {"renderer": renderer_metrics, "ecs": ecs_metrics},
    }


def main(argv: list[str]) -> None:
    if len(argv) != 4:
        raise SystemExit(
            "usage: ecs_scenarios_perf_child.py <scene> <frames> <headless|interactive>"
        )
    scene_name = argv[1]
    frames = int(argv[2])
    mode = argv[3]
    if scene_name not in SCENES:
        raise ValueError(f"unknown ECS performance benchmark scenario: {scene_name}")
    if mode not in {"headless", "interactive"}:
        raise ValueError("benchmark mode must be 'headless' or 'interactive'")
    print(json.dumps(_run_full_scene(scene_name, frames, mode == "headless"), sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
