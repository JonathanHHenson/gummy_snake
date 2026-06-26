from __future__ import annotations

import pytest

from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from gummysnake.rust import canvas as canvas_bridge
from gummysnake.sketch import Sketch
from tests.helpers.rust_canvas_modules import FakeCanvasModule


class FakeSketch:
    def __init__(self) -> None:
        self.frames = 0
        self.context = None

    def _draw_frame(self) -> None:
        self.frames += 1


def install_fake_canvas_runtime(
    monkeypatch: pytest.MonkeyPatch,
    module: object | None = None,
) -> object:
    runtime = FakeCanvasModule() if module is None else module
    monkeypatch.setattr(canvas_bridge, "_canvas", runtime)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    return runtime


def install_missing_canvas_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))


class EventSketch(Sketch):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[object, ...]] = []

    def mouse_pressed(self, event) -> None:
        self.events.append(("mouse_pressed", event.x, event.y, event.button))

    def mouse_dragged(self, event) -> None:
        self.events.append(("mouse_dragged", event.x, event.y, event.dx, event.dy))

    def mouse_wheel(self, event) -> None:
        self.events.append(("mouse_wheel", event.x, event.y, event.scroll_x, event.scroll_y))

    def key_pressed(self, event) -> None:
        self.events.append(("key_pressed", event.key, event.key_code))

    def key_released(self, event) -> None:
        self.events.append(("key_released", event.key, event.key_code))

    def key_typed(self, event) -> None:
        self.events.append(("key_typed", event.key, event.key_code))


def make_canvas_context(monkeypatch: pytest.MonkeyPatch) -> tuple[EventSketch, CanvasBackend]:
    install_fake_canvas_runtime(monkeypatch)
    backend = CanvasBackend()
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)
    return sketch, backend
