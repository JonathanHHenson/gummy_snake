"""Runtime event translation for the Rust canvas backend."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, cast

from gummysnake.backend._canvas import events as canvas_events
from gummysnake.backend._canvas.backend._protocols import CanvasBackendHost
from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND

if TYPE_CHECKING:
    from gummysnake.sketch import Sketch

_TEXTURE_LIMIT_RE = re.compile(r"GPU texture limit of (\d+)")


def _backend(self: object) -> CanvasBackendHost:
    return cast(CanvasBackendHost, self)


class CanvasBackendEventsMixin:
    def _dispatch_pending_events(self, sketch: Sketch) -> None:
        canvas = _backend(self).renderer.runtime_canvas()
        poll_events = getattr(canvas, "poll_events", None)
        if not callable(poll_events):
            return
        poll_start = _backend(self)._perf_counter()
        events = poll_events()
        poll_duration_ms = (_backend(self)._perf_counter() - poll_start) * 1000.0
        if _backend(self)._frame_pacing_enabled:
            frame_pacing = _backend(self)._frame_pacing
            frame_pacing["event_polls"] = self._pacing_int(frame_pacing["event_polls"]) + 1
            _backend(self)._record_pacing_duration("event_poll", poll_duration_ms)
        if not isinstance(events, Iterable):
            raise BackendCapabilityError("Canvas poll_events() must return an iterable.")
        for payload in cast(Iterable[object], events):
            self._dispatch_canvas_event(sketch, payload)

    def _dispatch_canvas_event(self, sketch: Sketch, payload: object) -> None:
        context = _backend(self)._sketch_context(sketch)
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
            _backend(self).stop()
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
            touches=touches, changed_touches=[changed_touch], type=str(payload["type"])
        )

    def _handle_resize_event(self, payload: Mapping[str, object]) -> None:
        width = canvas_events.int_payload(payload, "width")
        height = canvas_events.int_payload(payload, "height")
        pixel_density = canvas_events.float_payload(
            payload,
            "pixel_density",
            default=_backend(self).renderer.pixel_density,
        )
        try:
            _backend(self).renderer.resize(width, height, pixel_density)
        except ArgumentValidationError as exc:
            capped_density = self._resize_event_fallback_density(width, height, pixel_density, exc)
            if capped_density is None:
                raise
            _backend(self).renderer.resize(width, height, capped_density)

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
        density = _backend(self).renderer.pixel_density
        return float(x) / density, float(y) / density

    def _logical_pointer_delta(self, dx: float, dy: float) -> tuple[float, float]:
        density = _backend(self).renderer.pixel_density
        return float(dx) / density, float(dy) / density

    def _open_interactive_window(self, canvas: object) -> None:
        native_window_available = getattr(canvas, "native_window_available", None)
        if callable(native_window_available) and not bool(native_window_available()):
            raise BackendCapabilityError(
                "The installed gummysnake.rust._canvas runtime exposes the runtime bridge "
                "but was built without native window/event-loop support. Run with a bounded "
                "frame count for headless canvas rendering, or rebuild/reinstall the canvas "
                "runtime with native "
                f"window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        open_window = getattr(canvas, "open_window", None)
        if callable(open_window):
            open_window()
            _backend(self).renderer._sync_dimensions()
            return
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime does not expose native "
            "interactive window primitives. Run with a bounded frame count for headless "
            "canvas rendering, or "
            f"rebuild the current gummy_canvas crate with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )

    @staticmethod
    def _pacing_int(value: object) -> int:
        return int(value) if isinstance(value, int | float) else 0

    @staticmethod
    def _perf_counter() -> float:
        import time

        return time.perf_counter()
