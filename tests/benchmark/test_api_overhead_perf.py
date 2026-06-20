from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pytest

import p5
from p5.api.current import activate_context
from p5.backends.base import BackendCapabilities
from p5.context import SketchContext
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from p5.sketch import Sketch

ITERATIONS = 20_000
REPEATS = 5


class NoopRenderer:
    width = 128
    height = 128
    physical_width = 128
    physical_height = 128
    pixel_density = 1.0

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.width = width
        self.height = height
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.pixel_density = pixel_density

    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def present(self) -> None: ...
    def close(self) -> None: ...
    def background(self, color) -> None: ...
    def clear(self) -> None: ...
    def point(self, x, y, style, transform) -> None: ...
    def line(self, x1, y1, x2, y2, style, transform) -> None: ...
    def polygon(self, points, style, transform, *, close=True) -> None: ...
    def ellipse(self, x, y, width, height, style, transform) -> None: ...
    def arc(self, x, y, width, height, start, stop, mode, style, transform) -> None: ...
    def draw_image(self, image, dx, dy, dw, dh, style, transform, *, source=None) -> None: ...
    def text(self, value, x, y, style, transform) -> None: ...

    def text_width(self, value: str, style: StyleState) -> float:
        return len(value) * style.text_size * 0.5

    def text_ascent(self, style: StyleState) -> float:
        return style.text_size * 0.8

    def text_descent(self, style: StyleState) -> float:
        return style.text_size * 0.2

    def load_pixels(self) -> list[int]:
        return [0] * (self.physical_width * self.physical_height * 4)

    def load_pixel_bytes(self) -> bytes:
        return bytes(self.physical_width * self.physical_height * 4)

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes:
        return bytes(width * height * 4)

    def update_pixels(self, pixels: Sequence[int]) -> None: ...
    def update_pixel_region(
        self,
        pixels: Sequence[int],
        width: int,
        height: int,
        x: int,
        y: int,
        *,
        alpha_composite: bool = True,
    ) -> None: ...
    def filter_pixels(self, mode, value=None) -> None: ...
    def blend_region(self, source_image, source, destination, mode) -> None: ...
    def save(self, path: str) -> None: ...


class NoopBackend:
    name = "noop"
    capabilities = BackendCapabilities(headless=True)

    def __init__(self) -> None:
        self.renderer = NoopRenderer()

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer=p5.P2D,
    ) -> None:
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float,
        *,
        renderer=p5.P2D,
    ) -> None:
        self.renderer.resize(width, height, pixel_density)

    def display_density(self) -> float:
        return 1.0

    def run(self, sketch, *, max_frames: int | None = None) -> None: ...
    def stop(self) -> None: ...
    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def present(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class ApiBenchmarkCase:
    layer: str
    operation: str
    callback: Callable[[], object]


@dataclass(frozen=True)
class ApiBenchmarkSummary:
    layer: str
    operation: str
    samples_ns: tuple[float, ...]

    @property
    def mean_ns(self) -> float:
        return statistics.mean(self.samples_ns)

    @property
    def min_ns(self) -> float:
        return min(self.samples_ns)

    @property
    def max_ns(self) -> float:
        return max(self.samples_ns)


def _make_context() -> tuple[Sketch, SketchContext, p5.Image]:
    sketch = Sketch()
    backend = NoopBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(128, 128)
    image = p5.Image(8, 8, bytes([255, 0, 0, 255] * 64))
    return sketch, context, image


def _measure(callback: Callable[[], object]) -> tuple[float, ...]:
    samples: list[float] = []
    for _ in range(REPEATS):
        start = time.perf_counter_ns()
        for _ in range(ITERATIONS):
            callback()
        elapsed = time.perf_counter_ns() - start
        samples.append(elapsed / ITERATIONS)
    return tuple(samples)


def _build_cases(sketch: Sketch, context: SketchContext, image: p5.Image) -> list[ApiBenchmarkCase]:
    renderer = context.renderer
    style = context.state.style
    transform = Matrix2D()
    fast = context.fast()

    return [
        ApiBenchmarkCase("global", "fill", lambda: p5.fill(16, 32, 48, 192)),
        ApiBenchmarkCase("global", "line", lambda: p5.line(1, 2, 40, 50)),
        ApiBenchmarkCase("global", "circle", lambda: p5.circle(24, 24, 12)),
        ApiBenchmarkCase("global", "image", lambda: p5.image(image, 8, 8, 16, 16)),
        ApiBenchmarkCase("global", "text_width", lambda: p5.text_width("dispatch")),
        ApiBenchmarkCase("sketch", "fill", lambda: sketch.fill(16, 32, 48, 192)),
        ApiBenchmarkCase("sketch", "line", lambda: sketch.line(1, 2, 40, 50)),
        ApiBenchmarkCase("sketch", "circle", lambda: sketch.circle(24, 24, 12)),
        ApiBenchmarkCase("context", "fill", lambda: context.fill(16, 32, 48, 192)),
        ApiBenchmarkCase("context", "line", lambda: context.line(1, 2, 40, 50)),
        ApiBenchmarkCase("context", "circle", lambda: context.circle(24, 24, 12)),
        ApiBenchmarkCase("context", "image", lambda: context.image(image, 8, 8, 16, 16)),
        ApiBenchmarkCase("context", "text_width", lambda: context.text_width("dispatch")),
        ApiBenchmarkCase("fast", "line", lambda: fast.line(1, 2, 40, 50)),
        ApiBenchmarkCase("fast", "circle", lambda: fast.circle(24, 24, 12)),
        ApiBenchmarkCase("fast", "image", lambda: fast.image(image, 8, 8, 16, 16)),
        ApiBenchmarkCase("fast", "text_width", lambda: fast.text_width("dispatch")),
        ApiBenchmarkCase(
            "renderer",
            "line",
            lambda: renderer.line(1, 2, 40, 50, style, transform),
        ),
        ApiBenchmarkCase(
            "renderer",
            "circle",
            lambda: renderer.ellipse(24, 24, 12, 12, style, transform),
        ),
        ApiBenchmarkCase(
            "renderer",
            "image",
            lambda: renderer.draw_image(image, 8, 8, 16, 16, style, transform),
        ),
        ApiBenchmarkCase(
            "renderer",
            "text_width",
            lambda: renderer.text_width("dispatch", style),
        ),
    ]


@pytest.mark.benchmark
def test_api_dispatch_microbenchmarks() -> None:
    sketch, context, image = _make_context()
    with activate_context(context):
        summaries = [
            ApiBenchmarkSummary(case.layer, case.operation, _measure(case.callback))
            for case in _build_cases(sketch, context, image)
        ]

    for summary in summaries:
        print(
            f"api_microbenchmark {summary.layer}.{summary.operation}: "
            f"mean_ns={summary.mean_ns:.1f} min_ns={summary.min_ns:.1f} "
            f"max_ns={summary.max_ns:.1f} iterations={ITERATIONS} repeats={REPEATS}"
        )
        assert summary.mean_ns > 0

    by_case = {(summary.layer, summary.operation): summary for summary in summaries}
    for operation in ("line", "circle", "image", "text_width"):
        assert by_case[("fast", operation)].mean_ns < by_case[("global", operation)].mean_ns
