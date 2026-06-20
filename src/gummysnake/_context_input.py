"""Input state and event dispatch methods for SketchContext."""

from __future__ import annotations

from typing import Any

from gummysnake.api.current import activate_context
from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from gummysnake.plugins.base import EventHookName


class InputContextMixin:
    state: Any
    plugins: Any
    sketch: Any
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

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
    def mouse_button(self) -> str | None:
        return self.state.input.mouse_button

    @property
    def key(self) -> str | None:
        return self.state.input.key

    @property
    def key_code(self) -> int | None:
        return self.state.input.key_code

    @property
    def key_is_pressed(self) -> bool:
        return self.state.input.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        return list(self.state.input.touches)

    def update_mouse_event(self, event: MouseEvent, *, pressed: bool | None = None) -> None:
        self.state.input.update_mouse(event.x, event.y, dx=event.dx, dy=event.dy)
        if event.button is not None:
            self.state.input.mouse_button = event.button
        if pressed is not None:
            self.state.input.mouse_is_pressed = pressed
            if not pressed and event.button is not None:
                self.state.input.mouse_button = event.button

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
        if pressed is not None:
            self.state.input.key_is_pressed = pressed
        if event.key_code is not None and pressed is not None:
            if pressed:
                self.state.input.pressed_keys.add(event.key_code)
            else:
                self.state.input.pressed_keys.discard(event.key_code)

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

    def key_is_down(self, key_code: int) -> bool:
        return self.state.input.key_is_down(key_code)
