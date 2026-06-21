from __future__ import annotations

from typing import cast

import pytest
from rust_canvas_context_helpers import FakeSketch, make_canvas_context
from rust_canvas_modules import (
    FakeCanvasModule,
    FakeCanvasModuleWithoutGpu,
    FakeCanvasModuleWithoutNativeWindow,
)

from gummysnake import constants as c
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust import canvas as canvas_bridge


def test_canvas_backend_reports_implemented_capabilities() -> None:
    capabilities = CanvasBackend.capabilities

    assert capabilities.interactive is False
    assert capabilities.headless is True
    assert capabilities.text is True
    assert capabilities.images is True
    assert capabilities.pixels is True
    assert capabilities.pixel_readback is True
    assert capabilities.pixel_update is True
    assert capabilities.canvas_export is True
    assert capabilities.mouse is False
    assert capabilities.keyboard is False
    assert capabilities.touch is False
    assert capabilities.paths is True
    assert capabilities.transforms is True
    assert capabilities.blend_modes == frozenset(
        {
            c.BLEND,
            c.REPLACE,
            c.ADD,
            c.DARKEST,
            c.LIGHTEST,
            c.DIFFERENCE,
            c.EXCLUSION,
            c.MULTIPLY,
            c.SCREEN,
        }
    )
    assert capabilities.three_d is True
    assert capabilities.shaders is True
    assert capabilities.sound is True


def test_canvas_backend_enables_input_capabilities_when_native_runtime_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()

    assert backend.capabilities.interactive is True
    assert backend.capabilities.mouse is True
    assert backend.capabilities.keyboard is True
    assert backend.capabilities.touch is True
    assert backend.capabilities.pointer_lock is True


def test_canvas_backend_rejects_interactive_without_native_window_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutNativeWindow())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend(headless=False)
    backend.create_canvas(10, 10)

    with pytest.raises(BackendCapabilityError, match="native window support"):
        backend.run(FakeSketch())  # type: ignore[arg-type]


def test_canvas_backend_gpu_status_uses_runtime_canvas_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutGpu())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()
    assert "headless rendering can continue" in backend.gpu_status()


def test_canvas_backend_runs_headless_frames_and_accepts_webgl(
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

    backend.create_canvas(10, 10, renderer=c.WEBGL)
    assert backend.renderer.width == 10


def test_canvas_backend_delegates_pointer_lock_to_runtime_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend(headless=False)
    backend.create_canvas(10, 10)
    canvas = backend.renderer.runtime_canvas()
    canvas.open_window()

    assert backend.request_pointer_lock() is True
    assert canvas.pointer_locked() is True
    assert ("request_pointer_lock",) in canvas.calls

    assert backend.exit_pointer_lock() is True
    assert canvas.pointer_locked() is False
    assert ("exit_pointer_lock",) in canvas.calls


def test_canvas_backend_applies_pending_pointer_lock_mode_to_runtime_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()
    assert backend.pointer_lock_mode() == "clamped"
    backend.set_pointer_lock_mode("fixed")
    backend.create_canvas(10, 10)

    canvas = backend.renderer.runtime_canvas()
    assert canvas.pointer_lock_mode() == "fixed"
    assert ("set_pointer_lock_mode", "fixed") in canvas.calls


def test_canvas_backend_delegates_text_input_to_runtime_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend(headless=False)
    backend.create_canvas(10, 10)
    canvas = backend.renderer.runtime_canvas()
    canvas.open_window()

    assert backend.text_input_active() is False
    assert backend.start_text_input() is True
    assert backend.text_input_active() is True
    assert ("start_text_input",) in canvas.calls

    assert backend.stop_text_input() is True
    assert backend.text_input_active() is False
    assert ("stop_text_input",) in canvas.calls


def test_canvas_backend_repeated_create_canvas_preserves_existing_pixel_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    backend.create_canvas(100, 50, pixel_density=2)

    backend.create_canvas(100, 50)

    assert backend.renderer.pixel_density == 2
    assert backend.renderer.physical_width == 200


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


def test_canvas_backend_frame_pacing_diagnostics_are_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    sketch.context.enable_frame_pacing_diagnostics()

    backend.run(sketch, max_frames=2)

    report = cast(dict[str, bool | float | int | None], sketch.context.frame_pacing_diagnostics())
    assert report["enabled"] is True
    assert report["frames"] == 2
    assert report["last_draw_duration_ms"] is not None
    assert report["last_present_duration_ms"] is not None
    assert report["mean_draw_duration_ms"] is not None
    assert report["mean_present_duration_ms"] is not None
    assert report["mean_draw_duration_ms"] >= 0.0
    assert report["mean_present_duration_ms"] >= 0.0

    sketch.context.reset_frame_pacing_diagnostics()
    reset = cast(dict[str, bool | float | int | None], sketch.context.frame_pacing_diagnostics())
    assert reset["frames"] == 0


def test_canvas_next_frame_delay_skips_missed_frames() -> None:
    backend = CanvasBackend.__new__(CanvasBackend)
    backend._next_frame_time = 0.0
    interval = 1.0 / 60.0

    first_delay = backend._next_frame_delay(0.002, interval)
    delayed = backend._next_frame_delay(0.250, interval)

    assert first_delay == interval - 0.002
    assert 0.0 < delayed <= interval
    assert backend._next_frame_time > 0.250
