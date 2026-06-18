from __future__ import annotations

import json
import statistics
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRAMES = 180
REPEATS = 2
EXAMPLES = ("text", "touch", "sound")
BACKENDS = ("canvas", "pyglet")
CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import sys
    import time

    from p5.api.current import activate_context
    from p5.backends.canvas import CanvasBackend
    from p5.backends.pyglet import PygletBackend
    from p5.context import SketchContext
    from p5.plugins.registry import GLOBAL_PLUGIN_REGISTRY
    from p5.rust.canvas import is_canvas_available

    from examples.new_rust_backend.canvas_native_text import CanvasNativeTextDemo
    from examples.new_rust_backend.canvas_sound_media import CanvasSoundMediaDemo
    from examples.new_rust_backend.canvas_touch_input import CanvasTouchInputDemo

    example = sys.argv[1]
    backend_name = sys.argv[2]
    frames = int(sys.argv[3])
    demos = {
        "text": CanvasNativeTextDemo,
        "touch": CanvasTouchInputDemo,
        "sound": CanvasSoundMediaDemo,
    }

    if backend_name == "canvas":
        if not is_canvas_available():
            print(json.dumps({"skipped": True, "reason": "canvas extension unavailable"}))
            raise SystemExit(0)
        backend = CanvasBackend(interactive=True)
    else:
        backend = PygletBackend()

    demo = demos[example](backend=backend_name, export_canvas=False)
    demo.context = SketchContext(demo, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    GLOBAL_PLUGIN_REGISTRY.bind_runtime(demo.context, demo)
    demo._running = True

    with activate_context(demo.context):
        demo.context.plugins.dispatch_lifecycle("before_preload", demo.context)
        demo.preload()
        demo.context.plugins.dispatch_lifecycle("before_setup", demo.context)
        demo.setup()
        demo.context.ensure_canvas()
        demo.context.plugins.dispatch_lifecycle("after_setup", demo.context)
        start = time.perf_counter()
        backend.run(demo, max_frames=frames)

    elapsed = time.perf_counter() - start
    print(json.dumps({"backend": backend_name, "frames": frames, "fps": frames / elapsed}))
    """
)


@dataclass(frozen=True)
class BenchmarkSummary:
    backend: str
    samples: tuple[float, ...]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)


def _run_example(example: str, backend: str) -> BenchmarkSummary:
    samples: list[float] = []
    for _ in range(REPEATS):
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, example, backend, str(FRAMES)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"{example} benchmark backend {backend!r} failed\n{detail}")
        stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(stdout_lines[-1])
        if payload.get("skipped"):
            pytest.skip(str(payload["reason"]))
        samples.append(float(payload["fps"]))
    return BenchmarkSummary(backend=backend, samples=tuple(samples))


@pytest.mark.benchmark
@pytest.mark.parametrize("example", EXAMPLES)
@pytest.mark.parametrize("backend", BACKENDS)
def test_canvas_migration_examples_execute_interactively(example: str, backend: str) -> None:
    summary = _run_example(example, backend)
    assert summary.mean_fps > 0


@pytest.mark.benchmark
@pytest.mark.parametrize("example", EXAMPLES)
def test_canvas_migration_examples_are_significantly_faster_than_pyglet(example: str) -> None:
    canvas = _run_example(example, "canvas")
    pyglet = _run_example(example, "pyglet")
    ratio = canvas.mean_fps / pyglet.mean_fps
    print(
        f"canvas migration benchmark {example}: canvas/pyglet={ratio:.3f} "
        f"canvas={canvas.mean_fps:.2f} pyglet={pyglet.mean_fps:.2f}"
    )
    assert canvas.mean_fps >= 30.0
    assert ratio >= 1.10
