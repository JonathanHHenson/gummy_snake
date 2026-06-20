"""Experimental Rust-powered canvas backend."""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake import constants as c
from gummysnake.backends import _canvas_events as canvas_events
from gummysnake.backends.base import BackendCapabilities
from gummysnake.backends.canvas_renderer import CanvasRenderer
from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.rust.canvas import (
    GUMMY_CANVAS_BUILD_COMMAND,
    canvas_gpu_status,
    canvas_health_check,
    require_canvas_extension,
)

if TYPE_CHECKING:
    from gummysnake.sketch import Sketch


_TEXTURE_LIMIT_RE = re.compile(r"GPU texture limit of (\d+)")


def _pacing_float(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _pacing_int(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


class CanvasBackend:
    """Opt-in backend adapter for the ``gummy_canvas`` Rust runtime.

    The Rust canvas crate owns the pixel surface and, for native builds, the
    window/event source. The Python backend remains responsible for preserving
    the existing sketch lifecycle order and dispatching normalized events into
    ``SketchContext``.
    """

    name = "canvas"
    capabilities = BackendCapabilities(
        interactive=False,
        headless=True,
        text=True,
        images=True,
        pixels=True,
        pixel_readback=True,
        pixel_update=True,
        canvas_export=True,
        mouse=False,
        keyboard=False,
        touch=False,
        paths=True,
        transforms=True,
        blend_modes=frozenset(
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
        ),
        three_d=True,
        software_three_d=True,
        native_three_d=False,
        shaders=True,
        native_shaders=False,
        sound=True,
    )

    def __init__(self, *, headless: bool | None = None) -> None:
        self._canvas_module = require_canvas_extension()
        native_runtime = self._native_window_available()
        self.capabilities = replace(
            type(self).capabilities,
            interactive=native_runtime,
            mouse=native_runtime,
            keyboard=native_runtime,
            touch=native_runtime,
        )
        self.renderer = CanvasRenderer(self._canvas_module)
        self._headless = headless
        self._interactive = headless is False
        self._running = False
        self._frames_drawn = 0
        self._next_frame_time = 0.0
        self._debug = os.environ.get("GUMMY_CANVAS_DEBUG") == "1"
        self._last_idle_debug_frame: int | None = None
        self._frame_pacing_enabled = os.environ.get("GUMMY_CANVAS_PACING_DEBUG") == "1"
        self._frame_pacing: dict[str, float | int | bool | None] = {}
        self._last_present_time: float | None = None
        self.reset_frame_pacing_diagnostics()

    def health_check(self) -> str:
        """Return the underlying Rust canvas extension health check."""

        return canvas_health_check()

    def gpu_status(self) -> str:
        """Return an actionable GPU availability diagnostic for this canvas runtime."""

        canvas = self.renderer._canvas
        runtime_status = getattr(canvas, "gpu_status", None) if canvas is not None else None
        if callable(runtime_status):
            status = str(runtime_status())
            if status == "available":
                return status
            return (
                f"{status}; headless rendering can continue through CPU-backed canvas paths, "
                "but native interactive presentation and GPU-accelerated drawing may be "
                "disabled or slower."
            )
        return canvas_gpu_status()

    def _native_window_available(self) -> bool:
        native_window_available = getattr(self._canvas_module, "native_window_available", None)
        if callable(native_window_available):
            return bool(native_window_available())
        return False

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        self._ensure_supported_renderer(renderer)
        density = self.renderer.pixel_density if pixel_density is None else pixel_density
        self.renderer.resize(
            width,
            height,
            density,
            mode="headless",
        )

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return self.renderer.display_density()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._frame_pacing_enabled = bool(enabled)
        if reset:
            self.reset_frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        enabled = self._frame_pacing_enabled
        self._frame_pacing = {
            "enabled": enabled,
            "frames": 0,
            "event_polls": 0,
            "draw_duration_ms_total": 0.0,
            "present_duration_ms_total": 0.0,
            "event_poll_duration_ms_total": 0.0,
            "frame_interval_ms_total": 0.0,
            "max_draw_duration_ms": 0.0,
            "max_present_duration_ms": 0.0,
            "max_event_poll_duration_ms": 0.0,
            "max_frame_interval_ms": 0.0,
            "last_draw_duration_ms": None,
            "last_present_duration_ms": None,
            "last_event_poll_duration_ms": None,
            "last_frame_interval_ms": None,
        }
        self._last_present_time = None

    def frame_pacing_diagnostics(self) -> dict[str, float | int | bool | None]:
        report = dict(self._frame_pacing)
        frames = _pacing_int(report.get("frames"))
        event_polls = _pacing_int(report.get("event_polls"))
        report["mean_draw_duration_ms"] = (
            _pacing_float(report.get("draw_duration_ms_total")) / frames if frames else 0.0
        )
        report["mean_present_duration_ms"] = (
            _pacing_float(report.get("present_duration_ms_total")) / frames if frames else 0.0
        )
        report["mean_frame_interval_ms"] = (
            _pacing_float(report.get("frame_interval_ms_total")) / max(1, frames - 1)
            if frames > 1
            else 0.0
        )
        report["mean_event_poll_duration_ms"] = (
            _pacing_float(report.get("event_poll_duration_ms_total")) / event_polls
            if event_polls
            else 0.0
        )
        return report

    def _record_pacing_duration(self, kind: str, duration_ms: float) -> None:
        if not self._frame_pacing_enabled:
            return
        total_key = f"{kind}_duration_ms_total"
        max_key = f"max_{kind}_duration_ms"
        last_key = f"last_{kind}_duration_ms"
        self._frame_pacing[total_key] = _pacing_float(self._frame_pacing[total_key]) + duration_ms
        self._frame_pacing[max_key] = max(_pacing_float(self._frame_pacing[max_key]), duration_ms)
        self._frame_pacing[last_key] = duration_ms

    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        """Run the sketch.

        Bounded runs stay deterministic and offscreen for tests, scripts, and
        exports. When the native runtime is available, an unbounded canvas sketch
        with an active ``SketchContext`` automatically enters interactive mode and
        polls Rust-originated window/input events between scheduled frames.
        """

        should_run_interactive = self._interactive or (
            self._headless is None
            and max_frames is None
            and self.capabilities.interactive
            and getattr(sketch, "context", None) is not None
        )
        if should_run_interactive:
            self._run_interactive(sketch, max_frames=max_frames)
        else:
            self._run_headless(sketch, max_frames=1 if max_frames is None else max_frames)

    def stop(self) -> None:
        self._running = False
        self.renderer.close()

    def present(self) -> None:
        self.renderer.present()

    def _run_headless(self, sketch: Sketch, *, max_frames: int) -> None:
        self._running = True
        for _ in range(max(0, max_frames)):
            if not self._running:
                break
            self._draw_and_present(sketch)

    def _run_interactive(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        canvas = self.renderer.runtime_canvas()
        self._open_interactive_window(canvas)
        self._running = True
        self._frames_drawn = 0
        context = self._sketch_context(sketch)
        interval = 1.0 / max(1.0, context.state.timing.target_frame_rate)
        self._next_frame_time = time.perf_counter()

        while self._running and not self._should_close(canvas):
            was_looping = context.state.looping
            self._dispatch_pending_events(sketch)
            self._wake_for_pending_draw(context, was_looping=was_looping)
            if max_frames is not None:
                drew_frame = self._draw_and_present(sketch)
                self._debug_interactive_tick("bounded interactive tick", context, drew_frame)
                if drew_frame:
                    self._frames_drawn += 1
                elif not context.state.looping and not context.state.redraw_requested:
                    break
                if self._frames_drawn >= max_frames:
                    break
                continue
            now = time.perf_counter()
            draw_pending = context.state.looping or context.state.redraw_requested
            if draw_pending and now >= self._next_frame_time:
                drew_frame = self._draw_and_present(sketch)
                if drew_frame:
                    self._frames_drawn += 1
                self._debug_interactive_tick("interactive draw tick", context, drew_frame)
                self._advance_next_frame_time(now, interval)
            elif not draw_pending:
                self._debug_interactive_idle(context)
            if draw_pending:
                delay = max(0.0, min(self._next_frame_time - time.perf_counter(), interval))
            else:
                delay = min(interval, 1.0 / 60.0)
            if delay > 0:
                time.sleep(delay)
        self.stop()

    def _wake_for_pending_draw(self, context: Any, *, was_looping: bool) -> None:
        if context.state.redraw_requested or (context.state.looping and not was_looping):
            self._next_frame_time = time.perf_counter()

    def _debug_interactive_tick(self, label: str, context: Any, drew_frame: bool) -> None:
        if not self._debug:
            return
        self._last_idle_debug_frame = None
        print(
            "[canvas-debug] "
            f"{label} drew={drew_frame} looping={context.state.looping} "
            f"redraw={context.state.redraw_requested} frame={context.state.timing.frame_count}",
            flush=True,
        )

    def _debug_interactive_idle(self, context: Any) -> None:
        if not self._debug or self._last_idle_debug_frame == context.state.timing.frame_count:
            return
        self._last_idle_debug_frame = context.state.timing.frame_count
        print(
            "[canvas-debug] interactive idle "
            f"looping={context.state.looping} redraw={context.state.redraw_requested} "
            f"frame={context.state.timing.frame_count}",
            flush=True,
        )

    def _draw_and_present(self, sketch: Sketch) -> bool:
        context = getattr(sketch, "context", None)
        before_frame_count = context.state.timing.frame_count if context is not None else None
        draw_start = time.perf_counter()
        sketch._draw_frame()
        draw_duration_ms = (time.perf_counter() - draw_start) * 1000.0
        after_frame_count = context.state.timing.frame_count if context is not None else None
        if before_frame_count is None or after_frame_count != before_frame_count:
            present_start = time.perf_counter()
            self.present()
            present_end = time.perf_counter()
            self._record_pacing_duration("draw", draw_duration_ms)
            self._record_pacing_duration("present", (present_end - present_start) * 1000.0)
            self._record_present_interval(present_end)
            return True
        return False

    def _record_present_interval(self, now: float) -> None:
        if not self._frame_pacing_enabled:
            return
        self._frame_pacing["frames"] = _pacing_int(self._frame_pacing["frames"]) + 1
        if self._last_present_time is not None:
            interval_ms = (now - self._last_present_time) * 1000.0
            self._frame_pacing["frame_interval_ms_total"] = (
                _pacing_float(self._frame_pacing["frame_interval_ms_total"]) + interval_ms
            )
            self._frame_pacing["max_frame_interval_ms"] = max(
                _pacing_float(self._frame_pacing["max_frame_interval_ms"]), interval_ms
            )
            self._frame_pacing["last_frame_interval_ms"] = interval_ms
        self._last_present_time = now

    def _open_interactive_window(self, canvas: object) -> None:
        native_window_available = getattr(canvas, "native_window_available", None)
        if callable(native_window_available) and not bool(native_window_available()):
            raise BackendCapabilityError(
                "The installed gummysnake.rust._canvas extension exposes the runtime bridge "
                "but was built without native window/event-loop support. Run with a bounded "
                "frame count for headless canvas rendering, or rebuild/reinstall the canvas "
                "runtime with native "
                f"window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        open_window = getattr(canvas, "open_window", None)
        if callable(open_window):
            open_window()
            self.renderer._sync_dimensions()
            return
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas extension does not expose native "
            "interactive window primitives. Run with a bounded frame count for headless "
            "canvas rendering, or "
            f"rebuild the current gummy_canvas crate with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )

    def _should_close(self, canvas: object) -> bool:
        should_close = getattr(canvas, "should_close", None)
        if callable(should_close):
            return bool(should_close())
        return False

    def _dispatch_pending_events(self, sketch: Sketch) -> None:
        canvas = self.renderer.runtime_canvas()
        poll_events = getattr(canvas, "poll_events", None)
        if not callable(poll_events):
            return
        poll_start = time.perf_counter()
        events = poll_events()
        poll_duration_ms = (time.perf_counter() - poll_start) * 1000.0
        if self._frame_pacing_enabled:
            self._frame_pacing["event_polls"] = _pacing_int(self._frame_pacing["event_polls"]) + 1
            self._record_pacing_duration("event_poll", poll_duration_ms)
        if not isinstance(events, Iterable):
            raise BackendCapabilityError("Canvas poll_events() must return an iterable.")
        for payload in cast(Iterable[object], events):
            self._dispatch_canvas_event(sketch, payload)

    def _dispatch_canvas_event(self, sketch: Sketch, payload: object) -> None:
        context = self._sketch_context(sketch)
        event_payload = canvas_events.event_mapping(payload)
        event_type = str(event_payload.get("type", ""))
        if event_type in canvas_events.MOUSE_EVENT_TYPES:
            context.dispatch_mouse_event(self._mouse_event(event_payload))
            return
        if event_type in canvas_events.KEYBOARD_EVENT_TYPES:
            context.dispatch_keyboard_event(self._keyboard_event(event_payload))
            return
        if event_type in canvas_events.TOUCH_EVENT_TYPES:
            context.dispatch_touch_event(self._touch_event(event_payload, context))
            return
        if event_type == "resized":
            self._handle_resize_event(event_payload)
            context._sync_canvas_state()
            return
        if event_type in {"close", "closed"}:
            sketch.stop()
            self.stop()
            return
        raise BackendCapabilityError(f"Unsupported canvas runtime event type {event_type!r}.")

    def _mouse_event(self, payload: Mapping[str, object]) -> MouseEvent:
        x = canvas_events.float_payload(payload, "x", default=0.0)
        y = canvas_events.float_payload(payload, "y", default=0.0)
        dx = canvas_events.float_payload(payload, "dx", default=0.0)
        dy = canvas_events.float_payload(payload, "dy", default=0.0)
        if str(payload.get("coordinates", "physical")) != "logical":
            x, y = self._logical_pointer_position(x, y)
            dx, dy = self._logical_pointer_delta(dx, dy)
        return MouseEvent(
            x=x,
            y=y,
            dx=dx,
            dy=dy,
            button=canvas_events.normalize_mouse_button(payload.get("button")),
            scroll_x=canvas_events.float_payload(payload, "scroll_x", default=0.0),
            scroll_y=canvas_events.float_payload(payload, "scroll_y", default=0.0),
            modifiers=canvas_events.optional_int(payload.get("modifiers")),
            type=str(payload["type"]),
        )

    def _keyboard_event(self, payload: Mapping[str, object]) -> KeyboardEvent:
        key = payload.get("key")
        text = payload.get("text")
        key_text = text if payload.get("type") == "key_typed" and text is not None else key
        key_value = None if key_text is None else str(key_text)
        raw_key_code = payload.get("key_code", payload.get("code", key))
        return KeyboardEvent(
            key=key_value,
            key_code=canvas_events.normalize_key_code(raw_key_code, key_value),
            modifiers=canvas_events.optional_int(payload.get("modifiers")),
            type=str(payload["type"]),
        )

    def _touch_event(self, payload: Mapping[str, object], context: Any) -> TouchEvent:
        touch_id = canvas_events.int_payload(payload, "id")
        x = canvas_events.float_payload(payload, "x", default=0.0)
        y = canvas_events.float_payload(payload, "y", default=0.0)
        if str(payload.get("coordinates", "physical")) != "logical":
            x, y = self._logical_pointer_position(x, y)
        previous = {touch.id: touch for touch in context.state.input.touches}
        previous_touch = previous.get(touch_id)
        changed_touch = TouchPoint(
            id=touch_id,
            x=x,
            y=y,
            previous_x=getattr(previous_touch, "x", None),
            previous_y=getattr(previous_touch, "y", None),
            pressure=canvas_events.optional_float(payload.get("pressure")),
            phase=str(payload.get("phase", payload["type"])),
            timestamp=canvas_events.optional_float(payload.get("timestamp")),
            device=None if payload.get("device") is None else str(payload["device"]),
        )
        touches = [touch for touch in context.state.input.touches if touch.id != touch_id]
        if payload["type"] in {"touch_started", "touch_moved"}:
            touches.append(changed_touch)
        return TouchEvent(
            touches=touches,
            changed_touches=[changed_touch],
            type=str(payload["type"]),
        )

    def _handle_resize_event(self, payload: Mapping[str, object]) -> None:
        width = canvas_events.int_payload(payload, "width")
        height = canvas_events.int_payload(payload, "height")
        pixel_density = canvas_events.float_payload(
            payload,
            "pixel_density",
            default=self.renderer.pixel_density,
        )
        try:
            self.renderer.resize(width, height, pixel_density)
        except ArgumentValidationError as exc:
            capped_density = self._resize_event_fallback_density(width, height, pixel_density, exc)
            if capped_density is None:
                raise
            self.renderer.resize(width, height, capped_density)

    def _resize_event_fallback_density(
        self,
        width: int,
        height: int,
        pixel_density: float,
        exc: ArgumentValidationError,
    ) -> float | None:
        match = _TEXTURE_LIMIT_RE.search(str(exc))
        if match is None:
            return None
        max_dimension = max(width, height)
        if max_dimension <= 0:
            return None
        texture_limit = int(match.group(1))
        capped_density = math.nextafter(texture_limit / max_dimension, 0.0)
        if capped_density <= 0 or capped_density >= pixel_density:
            return None
        return capped_density

    def _logical_pointer_position(self, x: float, y: float) -> tuple[float, float]:
        density = self.renderer.pixel_density
        return float(x) / density, float(y) / density

    def _logical_pointer_delta(self, dx: float, dy: float) -> tuple[float, float]:
        density = self.renderer.pixel_density
        return float(dx) / density, float(dy) / density

    def _next_frame_delay(self, now: float, interval: float) -> float:
        self._advance_next_frame_time(now, interval)
        return max(0.0, self._next_frame_time - now)

    def _advance_next_frame_time(self, now: float, interval: float) -> None:
        self._next_frame_time += interval
        while self._next_frame_time <= now:
            self._next_frame_time += interval

    def _ensure_supported_renderer(self, renderer: c.RendererMode) -> None:
        if renderer not in {c.P2D, c.WEBGL}:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend currently implements only P2D and WEBGL "
                f"renderers, got {renderer!r}."
            )

    def _sketch_context(self, sketch: Sketch) -> Any:
        if sketch.context is None:
            raise BackendCapabilityError("Canvas runtime requires an active SketchContext.")
        return sketch.context
