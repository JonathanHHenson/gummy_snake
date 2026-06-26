"""Input state and event dispatch methods for SketchContext."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.api.current import activate_context
from gummysnake.backend.canvas_runtime import events as canvas_events
from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.plugins.base import EventHookName
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND


class InputContextMixin:
    backend: Any
    state: Any
    plugins: Any
    sketch: Any
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

    @property
    def mouse_x(self) -> float:
        return self.state.input.mouse_x

    @property
    def mouse_y(self) -> float:
        return self.state.input.mouse_y

    @property
    def pmouse_x(self) -> float:
        return self.state.input.previous_mouse_x

    @property
    def pmouse_y(self) -> float:
        return self.state.input.previous_mouse_y

    @property
    def moved_x(self) -> float:
        return self.state.input.moved_x

    @property
    def moved_y(self) -> float:
        return self.state.input.moved_y

    @property
    def mouse_is_pressed(self) -> bool:
        return self.state.input.mouse_is_pressed

    @property
    def mouse_inside_window(self) -> bool:
        return self.state.input.mouse_inside_window

    @property
    def mouse_button(self) -> str | None:
        return self.state.input.mouse_button

    @property
    def key(self) -> str | None:
        return self.state.input.key

    @property
    def key_code(self) -> int | None:
        return self.state.input.key_code

    @property
    def code(self) -> str | None:
        return self.state.input.code

    @property
    def typed_text(self) -> str | None:
        return self.state.input.text

    @property
    def text_input_active(self) -> bool:
        return self.state.input.text_input_active

    @property
    def key_is_pressed(self) -> bool:
        return self.state.input.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        return list(self.state.input.touches)

    def update_mouse_event(self, event: MouseEvent, *, pressed: bool | None = None) -> None:
        self.state.input.update_mouse(event.x, event.y, dx=event.dx, dy=event.dy)
        if event.inside_window is not None:
            self.state.input.mouse_inside_window = event.inside_window
        if event.previous_x is not None:
            self.state.input.previous_mouse_x = event.previous_x
        if event.previous_y is not None:
            self.state.input.previous_mouse_y = event.previous_y
        if event.button is not None:
            self.state.input.mouse_button = event.button
        if pressed is not None:
            self.state.input.mouse_is_pressed = pressed
            if not pressed and event.button is not None:
                self.state.input.mouse_button = event.button

    def update_mouse_inside_window(self, inside_window: bool) -> None:
        self.state.input.mouse_inside_window = inside_window

    def dispatch_mouse_event(self, event: MouseEvent) -> None:
        pressed = None
        if event.type == "mouse_pressed":
            pressed = True
        elif event.type == "mouse_released":
            pressed = False
        if event.type in {"mouse_moved", "mouse_dragged"}:
            self._frame_mouse_dx += event.dx
            self._frame_mouse_dy += event.dy
        if event.type == "mouse_wheel":
            self._frame_scroll_x += event.scroll_x
            self._frame_scroll_y += event.scroll_y
        self.update_mouse_event(event, pressed=pressed)
        with activate_context(self):
            self.plugins.dispatch_event(EventHookName.ON_MOUSE_EVENT, self, event)
            self.sketch._dispatch_callback(event.type, event)

    def update_keyboard_event(self, event: KeyboardEvent, *, pressed: bool | None = None) -> None:
        self.state.input.key = event.key
        self.state.input.key_code = event.key_code
        self.state.input.code = event.code
        self.state.input.text = event.text if event.type == "key_typed" else None
        if pressed is not None:
            self.state.input.key_is_pressed = pressed
        if event.key_code is not None and pressed is not None:
            self.state.input.set_key_down(event.key_code, pressed)
        if event.code is not None and pressed is not None:
            self.state.input.set_code_down(event.code, pressed)

    def dispatch_keyboard_event(self, event: KeyboardEvent) -> None:
        pressed = None
        if event.type == "key_pressed":
            pressed = True
        elif event.type == "key_released":
            pressed = False
        self.update_keyboard_event(event, pressed=pressed)
        with activate_context(self):
            self.plugins.dispatch_event(EventHookName.ON_KEYBOARD_EVENT, self, event)
            self.sketch._dispatch_callback(event.type, event)

    def update_touch_event(self, event: TouchEvent) -> None:
        self.state.input.require_touch_supported()
        self.state.input.update_touches(event.touches)

    def dispatch_touch_event(self, event: TouchEvent) -> None:
        self.update_touch_event(event)
        with activate_context(self):
            self.plugins.dispatch_event(EventHookName.ON_TOUCH_EVENT, self, event)
            self.sketch._dispatch_callback(event.type, event)

    def key_is_down(self, key_code: int | str) -> bool:
        if isinstance(key_code, str):
            normalized = canvas_events.normalize_key_code(key_code, key_code)
            if normalized is not None and self.state.input.key_is_down(normalized):
                return True
            if len(key_code) == 1 and self.state.input.key_is_down(ord(key_code.upper())):
                return True
            return self.state.input.code_is_down(key_code)
        return self.state.input.key_is_down(key_code)

    def set_pointer_lock_mode(self, mode: c.PointerLockMode | str) -> c.PointerLockMode:
        normalized = c.PointerLockMode(str(mode))
        self.state.input.pointer_lock_mode = normalized
        callback = getattr(self.backend, "set_pointer_lock_mode", None)
        if callable(callback):
            callback(normalized.value)
        return normalized

    def pointer_lock_mode(self) -> c.PointerLockMode:
        return self.state.input.pointer_lock_mode

    def start_text_input(self) -> bool:
        if not getattr(self.backend.capabilities, "keyboard", False):
            raise BackendCapabilityError(
                "Text input is not supported by the active backend. Run interactively with "
                f"a native canvas runtime using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        callback = getattr(self.backend, "start_text_input", None)
        if not callable(callback):
            raise BackendCapabilityError(
                "Text input is not supported by the active backend. Run interactively with "
                f"a native canvas runtime using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        active = bool(callback())
        self.state.input.text_input_active = active
        return active

    def stop_text_input(self) -> bool:
        callback = getattr(self.backend, "stop_text_input", None)
        if not callable(callback):
            self.state.input.text_input_active = False
            return False
        stopped = bool(callback())
        self.state.input.text_input_active = not stopped
        return stopped

    def is_text_input_active(self) -> bool:
        callback = getattr(self.backend, "text_input_active", None)
        if callable(callback):
            self.state.input.text_input_active = bool(callback())
        return self.state.input.text_input_active

    def request_pointer_lock(self) -> bool:
        if not getattr(self.backend.capabilities, "pointer_lock", False):
            raise BackendCapabilityError(
                "Pointer lock is not supported by the active backend. Rebuild/reinstall the "
                f"canvas runtime with native window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        callback = getattr(self.backend, "request_pointer_lock", None)
        if not callable(callback):
            raise BackendCapabilityError(
                "Pointer lock is not supported by the active backend. Rebuild/reinstall the "
                f"canvas runtime with native window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        locked = bool(callback())
        self.state.input.pointer_locked = locked
        return locked

    def exit_pointer_lock(self) -> bool:
        if not getattr(self.backend.capabilities, "pointer_lock", False):
            raise BackendCapabilityError(
                "Pointer lock is not supported by the active backend. Rebuild/reinstall the "
                f"canvas runtime with native window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        callback = getattr(self.backend, "exit_pointer_lock", None)
        if not callable(callback):
            raise BackendCapabilityError(
                "Pointer lock is not supported by the active backend. Rebuild/reinstall the "
                f"canvas runtime with native window support using `{GUMMY_CANVAS_BUILD_COMMAND}`."
            )
        locked = not bool(callback())
        self.state.input.pointer_locked = locked
        return not locked
