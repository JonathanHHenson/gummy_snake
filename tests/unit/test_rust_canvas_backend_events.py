from __future__ import annotations

import pytest
from rust_canvas_context_helpers import EventSketch, make_canvas_context
from rust_canvas_fakes import FakeCanvas
from rust_canvas_modules import FakeCanvasModule

from gummysnake import constants as c
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.events.input_state import KeyboardEvent
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from gummysnake.rust import canvas as canvas_bridge


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


def test_canvas_backend_interactive_cleans_up_when_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()

    def interrupt(_sketch: object) -> None:
        raise KeyboardInterrupt

    backend._dispatch_pending_events = interrupt  # type: ignore[method-assign]

    with pytest.raises(KeyboardInterrupt):
        backend._run_interactive(sketch)

    assert canvas.closed is True
    assert ("close",) in canvas.calls


def test_canvas_backend_interactive_max_frames_stops_after_requested_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._run_interactive(sketch, max_frames=1)

    assert sketch.context is not None
    assert sketch.context.frame_count == 1


def test_canvas_backend_interactive_max_frames_exits_when_paused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    sketch.context.no_loop()

    backend._run_interactive(sketch, max_frames=1)

    assert sketch.context.frame_count == 0


def test_canvas_backend_unbounded_interactive_respects_no_loop_from_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    context = sketch.context
    canvas = backend.renderer.runtime_canvas()
    polls = 0

    def poll_events() -> list[dict[str, object]]:
        nonlocal polls
        polls += 1
        if polls >= 5:
            canvas.closed = True
        return []

    def draw_frame() -> None:
        context.state.timing.frame_count += 1
        context.no_loop()

    canvas.poll_events = poll_events
    sketch._draw_frame = draw_frame  # type: ignore[method-assign]
    monkeypatch.setattr("gummysnake.backend.canvas.time.sleep", lambda _delay: None)

    backend._run_interactive(sketch)

    assert sketch.context.frame_count == 1
    assert polls >= 5


def test_canvas_backend_interactive_close_during_draw_aborts_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    context = sketch.context
    canvas = backend.renderer.runtime_canvas()

    def pump_native_events() -> bool:
        canvas.closed = True
        return True

    def draw() -> None:
        context.rect(1, 2, 3, 4)
        context.state.timing.frame_count += 1

    canvas.pump_native_events = pump_native_events
    sketch.draw = draw  # type: ignore[method-assign]

    backend._run_interactive(sketch)

    assert sketch._running is False
    assert context.frame_count == 0
    assert ("rect", 1.0, 2.0, 3.0, 4.0) not in canvas.calls


def test_canvas_backend_unbounded_context_run_uses_interactive_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()
    canvas.events.append({"type": "close"})

    backend.run(sketch)

    assert ("open_window",) in canvas.calls


def test_canvas_backend_explicit_headless_suppresses_unbounded_interactive_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend(headless=True)
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)
    canvas = backend.renderer.runtime_canvas()

    backend.run(sketch)

    assert ("open_window",) not in canvas.calls
    assert sketch.context.frame_count == 1


def test_canvas_backend_dispatches_default_physical_mouse_events_as_logical(
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
    assert sketch.context.mouse_y == 3
    assert sketch.context.mouse_is_pressed is True
    assert sketch.context.mouse_button == c.LEFT_BUTTON
    assert sketch.events == [
        ("mouse_pressed", 10, 5, c.LEFT_BUTTON),
        ("mouse_dragged", 12, 3, 2, -4),
        ("mouse_wheel", 12, 3, 1, -2),
    ]


def test_canvas_backend_dispatches_sdl_logical_mouse_events_without_density_scaling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {
            "type": "mouse_pressed",
            "x": 20,
            "y": 10,
            "button": 1,
            "modifiers": 4,
            "coordinates": "logical",
        },
    )
    backend._dispatch_canvas_event(
        sketch,
        {
            "type": "mouse_dragged",
            "x": 24,
            "y": 6,
            "dx": 4,
            "dy": -8,
            "button": "left",
            "coordinates": "logical",
        },
    )
    backend._dispatch_canvas_event(
        sketch,
        {
            "type": "mouse_wheel",
            "x": 24,
            "y": 6,
            "scroll_x": 1,
            "scroll_y": -2,
            "coordinates": "logical",
        },
    )

    assert sketch.context is not None
    assert sketch.context.mouse_x == 24
    assert sketch.context.mouse_y == 6
    assert sketch.context.mouse_is_pressed is True
    assert sketch.context.mouse_button == c.LEFT_BUTTON
    assert sketch.events == [
        ("mouse_pressed", 20, 10, c.LEFT_BUTTON),
        ("mouse_dragged", 24, 6, 4, -8),
        ("mouse_wheel", 24, 6, 1, -2),
    ]


def test_canvas_backend_updates_mouse_inside_window_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None

    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_moved", "x": 10, "y": 12, "inside_window": True},
    )
    assert sketch.context.mouse_inside_window is True

    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_window_state", "inside_window": False},
    )
    assert sketch.context.mouse_inside_window is False


def test_canvas_backend_dispatches_keyboard_events_and_pressed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    assert KeyboardEvent(key="l", key_code=ord("l")).matches("l") is True

    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_released", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "code": "ArrowLeft"})
    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "key": "Space"})
    backend._dispatch_canvas_event(sketch, {"type": "key_typed", "text": "é"})

    assert sketch.context is not None
    assert sketch.context.key_is_down(ord("a")) is False
    assert sketch.context.key_is_down(c.LEFT_ARROW) is True
    assert sketch.context.key_is_down(ord(" ")) is True
    assert sketch.events == [
        ("key_pressed", "a", ord("a")),
        ("key_released", "a", ord("a")),
        ("key_pressed", None, c.LEFT_ARROW),
        ("key_pressed", "Space", ord(" ")),
        ("key_typed", "é", ord("é")),
    ]


def test_canvas_backend_dispatches_touch_events_with_logical_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {
            "type": "touch_started",
            "id": 7,
            "x": 20,
            "y": 10,
            "pressure": 0.5,
            "phase": "started",
            "timestamp": 1.25,
            "device": "screen",
        },
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "touch_moved", "id": 7, "x": 24, "y": 6, "pressure": 0.75},
    )

    assert sketch.context is not None
    touch = sketch.context.touches[0]
    assert touch.id == 7
    assert (touch.x, touch.y) == (12, 3)
    assert (touch.previous_x, touch.previous_y) == (10, 5)
    assert touch.pressure == 0.75

    backend._dispatch_canvas_event(sketch, {"type": "touch_ended", "id": 7, "x": 24, "y": 6})
    assert sketch.context.touches == []


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
    assert ("resize_canvas", 120, 80, 1.5, c.P2D) in backend.renderer.runtime_canvas().calls
    assert ("resize", 120, 80, 1.5, c.P2D) not in backend.renderer.runtime_canvas().calls
    assert sketch.context is not None
    assert sketch.context.width == 120
    assert sketch.context.height == 80


def test_canvas_backend_caps_oversized_interactive_resize_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LimitedTextureCanvas(FakeCanvas):
        def resize_canvas(
            self, width: int, height: int, pixel_density: float, renderer: str
        ) -> None:
            physical_width = round(width * pixel_density)
            if physical_width > 2048:
                raise ValueError(
                    "Canvas physical width "
                    f"{physical_width} exceeds the GPU texture limit of 2048. "
                    "Reduce create_canvas() width or pixel_density()."
                )
            super().resize_canvas(width, height, pixel_density, renderer)

    class LimitedTextureCanvasModule(FakeCanvasModule):
        Canvas = LimitedTextureCanvas

    monkeypatch.setattr(canvas_bridge, "_canvas", LimitedTextureCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "resized", "width": 1200, "height": 800, "pixel_density": 2},
    )

    assert backend.renderer.width == 1200
    assert backend.renderer.height == 800
    assert backend.renderer.physical_width <= 2048
    assert backend.renderer.pixel_density < 2
    assert context.width == 1200
    assert context.height == 800
    assert context.pixel_density() < 2
