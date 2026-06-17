from __future__ import annotations

from pathlib import Path

import pytest

from p5 import constants as c
from p5.backends.canvas import CanvasBackend
from p5.backends.canvas_renderer import CanvasRenderer
from p5.context import SketchContext
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.exceptions import ArgumentValidationError, BackendCapabilityError
from p5.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from p5.rust import canvas as canvas_bridge
from p5.rust.canvas import (
    canvas_health_check,
    canvas_import_error,
    canvas_native_window_available,
    is_canvas_available,
    require_canvas_extension,
)
from p5.sketch import Sketch


class FakeCanvas:
    def __init__(
        self,
        width: int,
        height: int,
        pixel_density: float,
        mode: str,
        renderer: str,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.mode = mode
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.calls: list[tuple[object, ...]] = []
        self.events: list[dict[str, object]] = []
        self.closed = False
        self.window_open = False
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def resize(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)
        self.calls.append(("resize", width, height, pixel_density, renderer))

    def dimensions(self) -> tuple[int, int, int, int, float]:
        return (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )

    def display_density(self) -> float:
        return 1.0 if not self.window_open else max(1.0, self.pixel_density)

    def open_window(self) -> None:
        self.mode = "interactive"
        self.window_open = True
        self.closed = False
        self.calls.append(("open_window",))

    def should_close(self) -> bool:
        return self.closed

    def poll_events(self) -> list[dict[str, object]]:
        events = self.events
        self.events = []
        return events

    def begin_frame(self) -> None:
        self.calls.append(("begin_frame",))

    def end_frame(self) -> None:
        self.calls.append(("end_frame",))

    def present(self) -> None:
        self.calls.append(("present",))

    def close(self) -> None:
        self.closed = True
        self.calls.append(("close",))

    def background(self, rgba: tuple[int, int, int, int]) -> None:
        self.calls.append(("background", rgba))
        self.pixels = bytes(rgba) * (self.physical_width * self.physical_height)

    def clear(self) -> None:
        self.calls.append(("clear",))
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def point(self, *args: object) -> None:
        self.calls.append(("point", *args))

    def line(self, *args: object) -> None:
        self.calls.append(("line", *args))

    def polygon(self, *args: object) -> None:
        self.calls.append(("polygon", *args))

    def ellipse(self, *args: object) -> None:
        self.calls.append(("ellipse", *args))

    def arc(self, *args: object) -> None:
        self.calls.append(("arc", *args))

    def load_pixels(self) -> bytes:
        return self.pixels

    def update_pixels(self, pixels: bytes) -> None:
        expected = self.physical_width * self.physical_height * 4
        if len(pixels) != expected:
            raise ValueError(f"Pixel buffer length must be {expected}, got {len(pixels)}.")
        self.pixels = pixels

    def save(self, path: str) -> None:
        self.calls.append(("save", path))
        Path(path).write_bytes(b"fake-png")


class FakeCanvasModule:
    Canvas = FakeCanvas

    def health_check(self) -> str:
        return "fake-canvas"

    def native_window_available(self) -> bool:
        return True


class FakeSketch:
    def __init__(self) -> None:
        self.frames = 0
        self.context = None

    def _draw_frame(self) -> None:
        self.frames += 1


class EventSketch(Sketch):
    def __init__(self) -> None:
        super().__init__(backend="canvas")
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
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)
    return sketch, backend


def test_canvas_health_check_reports_unavailable_or_extension() -> None:
    assert canvas_health_check() in {"unavailable", "rust-canvas"}
    assert canvas_native_window_available() in {True, False}
    assert is_canvas_available() in {True, False}
    assert canvas_import_error() is None or isinstance(canvas_import_error(), ImportError)


def test_canvas_wrapper_uses_loaded_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCanvasModule()
    monkeypatch.setattr(canvas_bridge, "_canvas", fake)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    assert is_canvas_available()
    assert canvas_health_check() == "fake-canvas"
    assert canvas_native_window_available() is True
    assert require_canvas_extension() is fake


def test_canvas_wrapper_raises_capability_error_when_extension_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="p5.rust._canvas"):
        require_canvas_extension()


def test_canvas_backend_reports_implemented_capabilities() -> None:
    capabilities = CanvasBackend.capabilities

    assert capabilities.interactive is False
    assert capabilities.headless is True
    assert capabilities.text is False
    assert capabilities.images is False
    assert capabilities.pixels is True
    assert capabilities.pixel_readback is True
    assert capabilities.pixel_update is True
    assert capabilities.canvas_export is True
    assert capabilities.mouse is False
    assert capabilities.keyboard is False
    assert capabilities.touch is False
    assert capabilities.paths is True
    assert capabilities.transforms is True
    assert capabilities.blend_modes == frozenset({c.BLEND})
    assert capabilities.three_d is False
    assert capabilities.shaders is False
    assert capabilities.sound is False


def test_canvas_backend_enables_input_capabilities_when_native_runtime_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()

    assert backend.capabilities.interactive is True
    assert backend.capabilities.mouse is True
    assert backend.capabilities.keyboard is True


def test_canvas_backend_runs_headless_frames_and_rejects_webgl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()
    backend.create_canvas(10, 5, pixel_density=2)

    assert backend.health_check() == "fake-canvas"
    assert backend.renderer.width == 10
    assert backend.renderer.physical_width == 20
    assert backend.display_density() == 1.0

    sketch = FakeSketch()
    backend.run(sketch, max_frames=2)  # type: ignore[arg-type]
    assert sketch.frames == 2

    with pytest.raises(BackendCapabilityError, match="P2D"):
        backend.create_canvas(10, 10, renderer=c.WEBGL)


def test_canvas_renderer_allocates_and_mirrors_dimensions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    renderer.resize(12, 6, pixel_density=1.5)

    assert renderer.width == 12
    assert renderer.height == 6
    assert renderer.physical_width == 18
    assert renderer.physical_height == 9
    assert renderer.pixel_density == 1.5


def test_canvas_renderer_converts_style_color_and_transform_payloads() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    style = StyleState(fill_color=Color(255, 0, 0, 128), stroke_color=Color(0, 0, 255, 255))
    style.stroke_weight = 3
    transform = Matrix2D(1, 2, 3, 4, 5, 6)

    renderer.polygon([(1, 2), (3, 4)], style, transform, close=False)

    canvas = renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "polygon"
    assert call[1] == [(1, 2), (3, 4)]
    assert call[2] == {
        "fill": (255, 0, 0, 128),
        "stroke": (0, 0, 255, 255),
        "stroke_weight": 3.0,
        "blend_mode": c.BLEND,
        "erasing": False,
    }
    assert call[3] == (1, 2, 3, 4, 5, 6)
    assert call[4] is False


def test_canvas_renderer_pixels_and_save_round_trip(tmp_path: Path) -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(2, 1)

    renderer.background(Color(10, 20, 30, 255))
    assert renderer.load_pixels() == [10, 20, 30, 255, 10, 20, 30, 255]

    renderer.update_pixels([255, 0, 0, 255, 0, 0, 255, 255])
    assert renderer.load_pixels() == [255, 0, 0, 255, 0, 0, 255, 255]

    output = tmp_path / "canvas.png"
    renderer.save(output)
    assert output.read_bytes() == b"fake-png"


def test_canvas_renderer_maps_rust_value_errors() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    with pytest.raises(ArgumentValidationError, match="positive"):
        renderer.resize(0, 1)

    renderer.resize(1, 1)
    with pytest.raises(ArgumentValidationError, match="Pixel buffer length"):
        renderer.update_pixels([1, 2, 3])


def test_canvas_renderer_keeps_unimplemented_features_explicit() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(1, 1)

    with pytest.raises(BackendCapabilityError, match="image drawing"):
        renderer.draw_image(object(), 0, 0, 1, 1, StyleState(), Matrix2D.identity())  # type: ignore[arg-type]
    with pytest.raises(BackendCapabilityError, match="text drawing"):
        renderer.text("hello", 0, 0, StyleState(), Matrix2D.identity())
    with pytest.raises(BackendCapabilityError, match="region blending"):
        renderer.blend_region(None, (0, 0, 1, 1), (0, 0, 1, 1), c.BLEND)


def test_canvas_backend_headless_run_defaults_to_requested_frame_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    backend.create_canvas(8, 8)
    sketch = FakeSketch()

    backend.run(sketch, max_frames=0)  # type: ignore[arg-type]
    assert sketch.frames == 0

    backend.run(sketch)  # type: ignore[arg-type]
    assert sketch.frames == 1

    backend.run(sketch, max_frames=3)  # type: ignore[arg-type]
    assert sketch.frames == 4
    canvas = backend.renderer.runtime_canvas()
    assert ("present",) in canvas.calls


def test_canvas_backend_opens_interactive_window_and_reports_display_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()

    canvas.events.append({"type": "close"})
    backend._run_interactive(sketch)

    assert ("open_window",) in canvas.calls
    assert backend.display_density() == 2.0
    assert canvas.closed is True


def test_canvas_backend_interactive_max_frames_stops_after_requested_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._run_interactive(sketch, max_frames=1)

    assert sketch.context is not None
    assert sketch.context.frame_count == 1


def test_canvas_backend_unbounded_context_run_uses_interactive_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()
    canvas.events.append({"type": "close"})

    backend.run(sketch)

    assert ("open_window",) in canvas.calls


def test_canvas_backend_dispatches_mouse_events_with_logical_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_pressed", "x": 20, "y": 10, "button": 1, "modifiers": 4},
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_dragged", "x": 24, "y": 6, "dx": 4, "dy": -8, "button": "left"},
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_wheel", "x": 24, "y": 6, "scroll_x": 1, "scroll_y": -2},
    )

    assert sketch.context is not None
    assert sketch.context.mouse_x == 12
    assert sketch.context.mouse_y == 47
    assert sketch.context.mouse_is_pressed is True
    assert sketch.context.mouse_button == c.LEFT_BUTTON
    assert sketch.events == [
        ("mouse_pressed", 10, 45, c.LEFT_BUTTON),
        ("mouse_dragged", 12, 47, 2, 4),
        ("mouse_wheel", 12, 47, 1, -2),
    ]


def test_canvas_backend_dispatches_keyboard_events_and_pressed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_released", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "code": "ArrowLeft"})
    backend._dispatch_canvas_event(sketch, {"type": "key_typed", "text": "é"})

    assert sketch.context is not None
    assert sketch.context.key_is_down(ord("a")) is False
    assert sketch.context.key_is_down(c.LEFT_ARROW) is True
    assert sketch.events == [
        ("key_pressed", "a", ord("a")),
        ("key_released", "a", ord("a")),
        ("key_pressed", None, c.LEFT_ARROW),
        ("key_typed", "é", ord("é")),
    ]


def test_canvas_backend_handles_resize_events(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "resized", "width": 120, "height": 80, "pixel_density": 1.5},
    )

    assert backend.renderer.width == 120
    assert backend.renderer.height == 80
    assert backend.renderer.physical_width == 180
    assert backend.renderer.physical_height == 120
    assert sketch.context is not None
    assert sketch.context.width == 120
    assert sketch.context.height == 80


def test_canvas_next_frame_delay_skips_missed_frames() -> None:
    backend = CanvasBackend.__new__(CanvasBackend)
    backend._next_frame_time = 0.0
    interval = 1.0 / 60.0

    first_delay = backend._next_frame_delay(0.002, interval)
    delayed = backend._next_frame_delay(0.250, interval)

    assert first_delay == interval - 0.002
    assert 0.0 < delayed <= interval
    assert backend._next_frame_time > 0.250
