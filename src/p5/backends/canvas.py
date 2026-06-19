"""Experimental Rust-powered canvas backend."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from p5 import constants as c
from p5.backends.base import BackendCapabilities
from p5.backends.canvas_renderer import CanvasRenderer
from p5.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from p5.exceptions import ArgumentValidationError, BackendCapabilityError
from p5.rust.canvas import canvas_health_check, require_canvas_extension

if TYPE_CHECKING:
    from p5.sketch import Sketch


_MOUSE_EVENT_TYPES = {
    "mouse_moved",
    "mouse_dragged",
    "mouse_pressed",
    "mouse_released",
    "mouse_clicked",
    "mouse_double_clicked",
    "mouse_wheel",
}

_KEYBOARD_EVENT_TYPES = {"key_pressed", "key_released", "key_typed"}
_TOUCH_EVENT_TYPES = {"touch_started", "touch_moved", "touch_ended", "touch_cancelled"}
_TEXTURE_LIMIT_RE = re.compile(r"GPU texture limit of (\d+)")

_SPECIAL_KEY_CODES = {
    "backspace": c.BACKSPACE,
    "tab": c.TAB,
    "enter": c.ENTER,
    "return": c.RETURN,
    "escape": c.ESCAPE,
    "esc": c.ESCAPE,
    "shift": c.SHIFT,
    "control": c.CONTROL,
    "ctrl": c.CONTROL,
    "alt": c.ALT,
    "option": c.OPTION,
    "arrowup": c.UP_ARROW,
    "up": c.UP_ARROW,
    "up_arrow": c.UP_ARROW,
    "arrowdown": c.DOWN_ARROW,
    "down": c.DOWN_ARROW,
    "down_arrow": c.DOWN_ARROW,
    "arrowleft": c.LEFT_ARROW,
    "left": c.LEFT_ARROW,
    "left_arrow": c.LEFT_ARROW,
    "arrowright": c.RIGHT_ARROW,
    "right": c.RIGHT_ARROW,
    "right_arrow": c.RIGHT_ARROW,
}

_MOUSE_BUTTONS = {
    "left": c.LEFT_BUTTON,
    "primary": c.LEFT_BUTTON,
    "1": c.LEFT_BUTTON,
    1: c.LEFT_BUTTON,
    "center": c.CENTER_BUTTON,
    "middle": c.CENTER_BUTTON,
    "2": c.CENTER_BUTTON,
    2: c.CENTER_BUTTON,
    "right": c.RIGHT_BUTTON,
    "secondary": c.RIGHT_BUTTON,
    "3": c.RIGHT_BUTTON,
    3: c.RIGHT_BUTTON,
}


class CanvasBackend:
    """Opt-in backend adapter for the ``p5_canvas`` Rust runtime.

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
        shaders=True,
        sound=True,
    )

    def __init__(self, *, interactive: bool = False) -> None:
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
        self._interactive = interactive
        self._running = False
        self._frames_drawn = 0
        self._next_frame_time = 0.0

    def health_check(self) -> str:
        """Return the underlying Rust canvas extension health check."""

        return canvas_health_check()

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
        renderer: str = c.P2D,
    ) -> None:
        self._ensure_supported_renderer(renderer)
        self.renderer.resize(
            width,
            height,
            1.0 if pixel_density is None else pixel_density,
            mode="headless",
        )

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: str = c.P2D,
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return self.renderer.display_density()

    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        """Run the sketch.

        Bounded runs stay deterministic and offscreen for tests, scripts, and
        exports. When the native runtime is available, an unbounded canvas sketch
        with an active ``SketchContext`` automatically enters interactive mode and
        polls Rust-originated window/input events between scheduled frames.
        """

        should_run_interactive = self._interactive or (
            max_frames is None
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
            self._dispatch_pending_events(sketch)
            if max_frames is not None:
                self._draw_and_present(sketch)
                self._frames_drawn += 1
                if self._frames_drawn >= max_frames:
                    break
                continue
            now = time.perf_counter()
            if now >= self._next_frame_time:
                self._draw_and_present(sketch)
                self._frames_drawn += 1
                self._advance_next_frame_time(now, interval)
            delay = max(0.0, min(self._next_frame_time - time.perf_counter(), interval))
            if delay > 0:
                time.sleep(delay)
        self.stop()

    def _draw_and_present(self, sketch: Sketch) -> None:
        context = getattr(sketch, "context", None)
        before_frame_count = context.state.timing.frame_count if context is not None else None
        sketch._draw_frame()
        after_frame_count = context.state.timing.frame_count if context is not None else None
        if before_frame_count is None or after_frame_count != before_frame_count:
            self.present()

    def _open_interactive_window(self, canvas: object) -> None:
        native_window_available = getattr(canvas, "native_window_available", None)
        if callable(native_window_available) and not bool(native_window_available()):
            raise BackendCapabilityError(
                "The installed p5.rust._canvas extension exposes the runtime bridge but was built "
                "without native window/event-loop support. Run with a bounded frame count for "
                "headless canvas rendering or rebuild p5_canvas after enabling native runtime "
                "support."
            )
        open_window = getattr(canvas, "open_window", None)
        if callable(open_window):
            open_window()
            self.renderer._sync_dimensions()
            return
        raise BackendCapabilityError(
            "The installed p5.rust._canvas extension does not expose native interactive window "
            "primitives yet. Rebuild the current p5_canvas crate or run with a bounded "
            "frame count for headless canvas rendering."
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
        events = poll_events()
        if not isinstance(events, Iterable):
            raise BackendCapabilityError("Canvas poll_events() must return an iterable.")
        for payload in cast(Iterable[object], events):
            self._dispatch_canvas_event(sketch, payload)

    def _dispatch_canvas_event(self, sketch: Sketch, payload: object) -> None:
        context = self._sketch_context(sketch)
        event_payload = self._event_mapping(payload)
        event_type = str(event_payload.get("type", ""))
        if event_type in _MOUSE_EVENT_TYPES:
            context.dispatch_mouse_event(self._mouse_event(event_payload))
            return
        if event_type in _KEYBOARD_EVENT_TYPES:
            context.dispatch_keyboard_event(self._keyboard_event(event_payload))
            return
        if event_type in _TOUCH_EVENT_TYPES:
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

    def _event_mapping(self, payload: object) -> Mapping[str, object]:
        if isinstance(payload, Mapping):
            return cast(Mapping[str, object], payload)
        as_dict = getattr(payload, "as_dict", None)
        if callable(as_dict):
            value = as_dict()
            if isinstance(value, Mapping):
                return cast(Mapping[str, object], value)
        raise BackendCapabilityError("Canvas runtime events must be mappings or expose as_dict().")

    def _mouse_event(self, payload: Mapping[str, object]) -> MouseEvent:
        x = self._float_payload(payload, "x", default=0.0)
        y = self._float_payload(payload, "y", default=0.0)
        dx = self._float_payload(payload, "dx", default=0.0)
        dy = self._float_payload(payload, "dy", default=0.0)
        if str(payload.get("coordinates", "physical")) != "logical":
            x, y = self._logical_pointer_position(x, y)
            dx, dy = self._logical_pointer_delta(dx, dy)
        return MouseEvent(
            x=x,
            y=y,
            dx=dx,
            dy=dy,
            button=self._normalize_mouse_button(payload.get("button")),
            scroll_x=self._float_payload(payload, "scroll_x", default=0.0),
            scroll_y=self._float_payload(payload, "scroll_y", default=0.0),
            modifiers=self._optional_int(payload.get("modifiers")),
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
            key_code=self._normalize_key_code(raw_key_code, key_value),
            modifiers=self._optional_int(payload.get("modifiers")),
            type=str(payload["type"]),
        )

    def _touch_event(self, payload: Mapping[str, object], context: Any) -> TouchEvent:
        touch_id = self._int_payload(payload, "id")
        x = self._float_payload(payload, "x", default=0.0)
        y = self._float_payload(payload, "y", default=0.0)
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
            pressure=self._optional_float(payload.get("pressure")),
            phase=str(payload.get("phase", payload["type"])),
            timestamp=self._optional_float(payload.get("timestamp")),
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
        width = self._int_payload(payload, "width")
        height = self._int_payload(payload, "height")
        pixel_density = self._float_payload(
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

    def _normalize_mouse_button(self, button: object) -> str | None:
        if button is None:
            return None
        normalized = _MOUSE_BUTTONS.get(button)
        if normalized is not None:
            return normalized
        return _MOUSE_BUTTONS.get(str(button).lower(), str(button))

    def _normalize_key_code(self, key_code: object, key: str | None = None) -> int | None:
        if key_code is None:
            if key is not None and len(key) == 1:
                return ord(key)
            return None
        if isinstance(key_code, int):
            return key_code
        if isinstance(key_code, float):
            return int(key_code)
        text = str(key_code)
        special = _SPECIAL_KEY_CODES.get(text.lower())
        if special is not None:
            return special
        if len(text) == 1:
            return ord(text)
        if key is not None and len(key) == 1:
            return ord(key)
        return None

    def _next_frame_delay(self, now: float, interval: float) -> float:
        self._advance_next_frame_time(now, interval)
        return max(0.0, self._next_frame_time - now)

    def _advance_next_frame_time(self, now: float, interval: float) -> None:
        self._next_frame_time += interval
        while self._next_frame_time <= now:
            self._next_frame_time += interval

    def _ensure_supported_renderer(self, renderer: str) -> None:
        if renderer not in {c.P2D, c.WEBGL}:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend currently implements only P2D and WEBGL "
                f"renderers, got {renderer!r}."
            )

    def _sketch_context(self, sketch: Sketch) -> Any:
        if sketch.context is None:
            raise BackendCapabilityError("Canvas runtime requires an active SketchContext.")
        return sketch.context

    def _float_payload(
        self,
        payload: Mapping[str, object],
        key: str,
        *,
        default: float | None = None,
    ) -> float:
        value: Any = payload.get(key, default)
        if value is None:
            raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
        return float(value)

    def _int_payload(self, payload: Mapping[str, object], key: str) -> int:
        value: Any = payload.get(key)
        if value is None:
            raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
        return int(value)

    def _optional_int(self, value: object) -> int | None:
        raw_value: Any = value
        return None if raw_value is None else int(raw_value)

    def _optional_float(self, value: object) -> float | None:
        raw_value: Any = value
        return None if raw_value is None else float(raw_value)
