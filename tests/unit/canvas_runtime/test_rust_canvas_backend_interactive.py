from __future__ import annotations

import pytest

from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from tests.helpers.canvas_runtime.context import (
    EventSketch,
    install_fake_canvas_runtime,
    make_canvas_context,
)


def test_canvas_backend_opens_interactive_window_and_reports_display_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()

    canvas.events.append({"type": "close"})
    backend._run_interactive(sketch)

    assert ("open_window",) in canvas.calls
    assert backend.display_density() == 2.0
    assert sketch.context is not None
    assert sketch.context.frame_count == 0
    assert canvas.closed is True


def test_canvas_backend_interactive_cleans_up_when_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()

    def interrupt(_sketch: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(backend, "_dispatch_pending_events", interrupt)

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
    monkeypatch.setattr(sketch, "_draw_frame", draw_frame)
    monkeypatch.setattr("gummysnake.backend.canvas.time.sleep", lambda _delay: None)

    backend._run_interactive(sketch)

    assert sketch.context.frame_count == 1
    assert polls >= 5


def test_canvas_backend_interactive_tick_is_the_only_event_pump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()
    poll_events = canvas.poll_events
    polls = 0

    def counted_poll_events() -> list[dict[str, object]]:
        nonlocal polls
        polls += 1
        return poll_events()

    canvas.poll_events = counted_poll_events

    backend._run_interactive(sketch, max_frames=1)

    assert polls == 1
    assert not hasattr(canvas, "pump_native_events")


def test_canvas_backend_applies_frame_rate_changes_to_the_next_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    context = sketch.context
    sleeps: list[float] = []

    def draw_frame() -> None:
        context.state.timing.target_frame_rate = 20.0
        context.state.timing.frame_count += 1

    monkeypatch.setattr(sketch, "_draw_frame", draw_frame)
    monkeypatch.setattr(backend, "_perf_counter", lambda: 10.0)
    monkeypatch.setattr(backend, "_sleep", sleeps.append)
    backend._next_frame_time = 10.0

    backend._interactive_tick(sketch, context)

    assert backend._next_frame_time == pytest.approx(10.05)
    assert sleeps == pytest.approx([0.05])


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
    install_fake_canvas_runtime(monkeypatch)
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
