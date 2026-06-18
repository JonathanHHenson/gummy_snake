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
FRAMES = 60
REPEATS = 1
EXAMPLES = ("primitives", "shader")
BACKENDS = ("canvas", "pyglet")
MIN_CANVAS_TO_PYGLET_RATIO = 1.15

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

    from examples.new_rust_backend.canvas_webgl_primitives import CanvasWebGLPrimitivesDemo
    from examples.new_rust_backend.canvas_webgl_shader import CanvasWebGLShaderDemo

    example = sys.argv[1]
    backend = sys.argv[2]
    frames = int(sys.argv[3])

    if backend == "canvas" and not is_canvas_available():
        print(json.dumps({"skipped": True, "reason": "canvas extension unavailable"}))
        raise SystemExit(0)

    demo_type = {
        "primitives": CanvasWebGLPrimitivesDemo,
        "shader": CanvasWebGLShaderDemo,
    }[example]

    backend_instance = CanvasBackend(interactive=True) if backend == "canvas" else PygletBackend()
    demo = demo_type(backend=backend, export_canvas=False)
    demo.context = SketchContext(demo, backend_instance, plugins=GLOBAL_PLUGIN_REGISTRY)
    GLOBAL_PLUGIN_REGISTRY.bind_runtime(demo.context, demo)
    demo._running = True

    start = 0.0
    with activate_context(demo.context):
        demo.context.plugins.dispatch_lifecycle("before_preload", demo.context)
        demo.preload()
        demo.context.plugins.dispatch_lifecycle("before_setup", demo.context)
        demo.setup()
        demo.context.ensure_canvas()
        demo.context.plugins.dispatch_lifecycle("after_setup", demo.context)
        start = time.perf_counter()
        backend_instance.run(demo, max_frames=frames)
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "example": example,
                "backend": backend,
                "frames": frames,
                "elapsed": elapsed,
                "fps": frames / max(elapsed, 1e-9),
            }
        )
    )
    """
)


@dataclass(frozen=True)
class BenchmarkSummary:
    example: str
    backend: str
    samples: tuple[float, ...]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)

    @property
    def min_fps(self) -> float:
        return min(self.samples)

    @property
    def max_fps(self) -> float:
        return max(self.samples)


def _run_example(
    example: str,
    backend: str,
    *,
    frames: int = FRAMES,
    repeats: int = REPEATS,
) -> BenchmarkSummary:
    samples: list[float] = []
    for _ in range(repeats):
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, example, backend, str(frames)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(
                f"WEBGL benchmark example={example!r} backend={backend!r} failed\n{detail}"
            )
        stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(stdout_lines[-1])
        if payload.get("skipped"):
            pytest.skip(str(payload["reason"]))
        samples.append(float(payload["fps"]))
    return BenchmarkSummary(example=example, backend=backend, samples=tuple(samples))


@pytest.mark.benchmark
@pytest.mark.parametrize("example", EXAMPLES)
@pytest.mark.parametrize("backend", BACKENDS)
def test_canvas_webgl_examples_execute_interactively(example: str, backend: str) -> None:
    summary = _run_example(example, backend)
    print(
        f"WEBGL benchmark {summary.example}/{summary.backend}: "
        f"mean_fps={summary.mean_fps:.2f} min_fps={summary.min_fps:.2f} "
        f"max_fps={summary.max_fps:.2f}"
    )
    assert summary.mean_fps > 0


@pytest.mark.benchmark
@pytest.mark.parametrize("example", EXAMPLES)
def test_canvas_webgl_is_significantly_faster_than_pyglet(example: str) -> None:
    canvas = _run_example(example, "canvas")
    pyglet = _run_example(example, "pyglet")
    ratio = canvas.mean_fps / pyglet.mean_fps
    print(
        f"WEBGL benchmark ratio {example}: canvas/pyglet={ratio:.3f} "
        f"canvas={canvas.mean_fps:.2f} pyglet={pyglet.mean_fps:.2f}"
    )

    assert ratio >= MIN_CANVAS_TO_PYGLET_RATIO
