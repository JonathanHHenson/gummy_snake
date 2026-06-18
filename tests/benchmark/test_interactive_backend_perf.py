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
    from p5.sketch import Sketch

    from examples.new_rust_backend.canvas_asteroids import AsteroidsDemo

    backend_name = sys.argv[1]
    frames = int(sys.argv[2])


    class BenchmarkSketch(Sketch):
        def __init__(self, backend_name: str) -> None:
            super().__init__(backend=backend_name)
            self.demo = AsteroidsDemo(export_canvas=False)

        def preload(self) -> None:
            pass

        def setup(self) -> None:
            self.demo.setup()

        def draw(self) -> None:
            self.demo.draw()

        def key_pressed(self, event: object = None) -> None:
            self.demo.key_pressed(event)

        def key_typed(self, event: object = None) -> None:
            self.demo.key_typed(event)

        def mouse_pressed(self, event: object = None) -> None:
            self.demo.mouse_pressed(event)


    def run_demo() -> None:
        if backend_name == "canvas":
            if not is_canvas_available():
                print(json.dumps({"skipped": True, "reason": "canvas extension unavailable"}))
                return
            backend = CanvasBackend(interactive=True)
        else:
            backend = PygletBackend()

        sketch = BenchmarkSketch(backend_name)
        sketch.context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
        GLOBAL_PLUGIN_REGISTRY.bind_runtime(sketch.context, sketch)
        sketch._running = True

        start = 0.0
        with activate_context(sketch.context):
            sketch.context.plugins.dispatch_lifecycle("before_preload", sketch.context)
            sketch.preload()
            sketch.context.plugins.dispatch_lifecycle("before_setup", sketch.context)
            sketch.setup()
            sketch.context.ensure_canvas()
            sketch.context.plugins.dispatch_lifecycle("after_setup", sketch.context)
            start = time.perf_counter()
            backend.run(sketch, max_frames=frames)

        elapsed = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "backend": backend_name,
                    "frames": frames,
                    "elapsed": elapsed,
                    "fps": frames / max(elapsed, 1e-9),
                }
            )
        )


    if __name__ == "__main__":
        run_demo()
    """
)


@dataclass(frozen=True)
class BenchmarkSummary:
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


def _run_backend(backend: str, *, frames: int = FRAMES, repeats: int = REPEATS) -> BenchmarkSummary:
    samples: list[float] = []
    for _ in range(repeats):
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, backend, str(frames)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"interactive benchmark backend {backend!r} failed\n{detail}")
        stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(stdout_lines[-1])
        if payload.get("skipped"):
            pytest.skip(str(payload["reason"]))
        samples.append(float(payload["fps"]))
    return BenchmarkSummary(backend=backend, samples=tuple(samples))


@pytest.mark.benchmark
@pytest.mark.parametrize("backend", BACKENDS)
def test_interactive_backend_benchmark_executes(backend: str) -> None:
    summary = _run_backend(backend)
    print(
        f"interactive benchmark {summary.backend}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f}"
    )
    assert summary.mean_fps > 0


@pytest.mark.benchmark
def test_canvas_interactive_regression_against_pyglet() -> None:
    canvas = _run_backend("canvas")
    pyglet = _run_backend("pyglet")
    ratio = canvas.mean_fps / pyglet.mean_fps
    print(f"interactive benchmark ratio: canvas/pyglet={ratio:.3f}")

    assert canvas.mean_fps >= 30.0
    assert ratio >= 1.05
