"""Input state and event dispatch methods for SketchContext."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.api.current import activate_context
from gummysnake.backend.canvas_runtime import events as canvas_events
from gummysnake.core.input_events import (
    KeyboardEvent,
    MotionEvent,
    MouseEvent,
    TouchEvent,
    TouchPoint,
)
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
        """Mouse x.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.mouse_x

    @property
    def mouse_y(self) -> float:
        """Mouse y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.mouse_y

    @property
    def pmouse_x(self) -> float:
        """Pmouse x.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.previous_mouse_x

    @property
    def pmouse_y(self) -> float:
        """Pmouse y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.previous_mouse_y

    @property
    def moved_x(self) -> float:
        """Moved x.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.moved_x

    @property
    def moved_y(self) -> float:
        """Moved y.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.moved_y

    @property
    def mouse_is_pressed(self) -> bool:
        """Mouse is pressed.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self.state.input.mouse_is_pressed

    @property
    def mouse_inside_window(self) -> bool:
        """Mouse inside window.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self.state.input.mouse_inside_window

    @property
    def mouse_button(self) -> str | None:
        """Mouse button.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self.state.input.mouse_button

    @property
    def key(self) -> str | None:
        """Key.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self.state.input.key

    @property
    def key_code(self) -> int | None:
        """Key code.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int | None`.
        """
        return self.state.input.key_code

    @property
    def code(self) -> str | None:
        """Code.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self.state.input.code

    @property
    def typed_text(self) -> str | None:
        """Typed text.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str | None`.
        """
        return self.state.input.text

    @property
    def text_input_active(self) -> bool:
        """Text input active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self.state.input.text_input_active

    @property
    def key_is_pressed(self) -> bool:
        """Key is pressed.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self.state.input.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        """Touches.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[TouchPoint]`.
        """
        return list(self.state.input.touches)

    def update_mouse_event(self, event: MouseEvent, *, pressed: bool | None = None) -> None:
        """Update mouse event.
        
        Args:
            event: The event value. Expected type: `MouseEvent`.
            pressed: The pressed value. Expected type: `bool | None`. Defaults to `None`.
        
        Returns:
            None.
        """
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
        """Update mouse inside window.
        
        Args:
            inside_window: The inside window value. Expected type: `bool`.
        
        Returns:
            None.
        """
        self.state.input.mouse_inside_window = inside_window

    def dispatch_mouse_event(self, event: MouseEvent) -> None:
        """Dispatch mouse event.
        
        Args:
            event: The event value. Expected type: `MouseEvent`.
        
        Returns:
            None.
        """
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
        """Update keyboard event.
        
        Args:
            event: The event value. Expected type: `KeyboardEvent`.
            pressed: The pressed value. Expected type: `bool | None`. Defaults to `None`.
        
        Returns:
            None.
        """
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
        """Dispatch keyboard event.
        
        Args:
            event: The event value. Expected type: `KeyboardEvent`.
        
        Returns:
            None.
        """
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
        """Update touch event.
        
        Args:
            event: The event value. Expected type: `TouchEvent`.
        
        Returns:
            None.
        """
        self.state.input.require_touch_supported()
        self.state.input.update_touches(event.touches)

    def dispatch_touch_event(self, event: TouchEvent) -> None:
        """Dispatch touch event.
        
        Args:
            event: The event value. Expected type: `TouchEvent`.
        
        Returns:
            None.
        """
        self.update_touch_event(event)
        with activate_context(self):
            self.plugins.dispatch_event(EventHookName.ON_TOUCH_EVENT, self, event)
            self.sketch._dispatch_callback(event.type, event)

    def dispatch_motion_event(self, event: MotionEvent) -> None:
        """Dispatch motion event.
        
        Args:
            event: The event value. Expected type: `MotionEvent`.
        
        Returns:
            None.
        """
        with activate_context(self):
            self.sketch._dispatch_callback(event.type, event)

    def update_sensor_sample(
        self,
        *,
        acceleration_x: float | None = None,
        acceleration_y: float | None = None,
        acceleration_z: float | None = None,
        rotation_x: float | None = None,
        rotation_y: float | None = None,
        rotation_z: float | None = None,
        orientation: str | None = None,
    ) -> MotionEvent:
        """Update sensor sample.
        
        Args:
            acceleration_x: The acceleration x value. Expected type: `float | None`. Defaults to
                `None`.
            acceleration_y: The acceleration y value. Expected type: `float | None`. Defaults to
                `None`.
            acceleration_z: The acceleration z value. Expected type: `float | None`. Defaults to
                `None`.
            rotation_x: The rotation x value. Expected type: `float | None`. Defaults to `None`.
            rotation_y: The rotation y value. Expected type: `float | None`. Defaults to `None`.
            rotation_z: The rotation z value. Expected type: `float | None`. Defaults to `None`.
            orientation: The orientation value. Expected type: `str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `MotionEvent`.
        """
        previous_acceleration = (
            self.state.input.acceleration_x,
            self.state.input.acceleration_y,
            self.state.input.acceleration_z,
        )
        event = self.state.input.update_motion(
            acceleration_x=acceleration_x,
            acceleration_y=acceleration_y,
            acceleration_z=acceleration_z,
            rotation_x=rotation_x,
            rotation_y=rotation_y,
            rotation_z=rotation_z,
            orientation=orientation,
        )
        moved = (
            _motion_distance(
                event.acceleration_x - previous_acceleration[0],
                event.acceleration_y - previous_acceleration[1],
                event.acceleration_z - previous_acceleration[2],
            )
            >= self.state.input.move_threshold
        )
        shaken = (
            _motion_distance(event.acceleration_x, event.acceleration_y, event.acceleration_z)
            >= self.state.input.shake_threshold
        )
        turned = event.turn_axis is not None
        if moved:
            self.dispatch_motion_event(_motion_event_with_type(event, "device_moved"))
        if turned:
            self.dispatch_motion_event(_motion_event_with_type(event, "device_turned"))
        if shaken:
            self.dispatch_motion_event(_motion_event_with_type(event, "device_shaken"))
        return event

    def set_move_threshold(self, value: float) -> None:
        """Set move threshold.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.state.input.move_threshold = max(0.0, float(value))

    def set_shake_threshold(self, value: float) -> None:
        """Set shake threshold.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.state.input.shake_threshold = max(0.0, float(value))

    def key_is_down(self, key_code: int | str) -> bool:
        """Key is down.
        
        Args:
            key_code: The key code value. Expected type: `int | str`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if isinstance(key_code, str):
            normalized = canvas_events.normalize_key_code(key_code, key_code)
            if normalized is not None and self.state.input.key_is_down(normalized):
                return True
            if len(key_code) == 1 and self.state.input.key_is_down(ord(key_code.upper())):
                return True
            return self.state.input.code_is_down(key_code)
        return self.state.input.key_is_down(key_code)

    def set_pointer_lock_mode(self, mode: c.PointerLockMode | str) -> c.PointerLockMode:
        """Set pointer lock mode.
        
        Args:
            mode: The mode value. Expected type: `c.PointerLockMode | str`.
        
        Returns:
            The return value. Type: `c.PointerLockMode`.
        """
        normalized = c.PointerLockMode(str(mode))
        self.state.input.pointer_lock_mode = normalized
        callback = getattr(self.backend, "set_pointer_lock_mode", None)
        if callable(callback):
            callback(normalized.value)
        return normalized

    def pointer_lock_mode(self) -> c.PointerLockMode:
        """Pointer lock mode.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `c.PointerLockMode`.
        """
        return self.state.input.pointer_lock_mode

    def start_text_input(self) -> bool:
        """Start text input.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
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
        """Stop text input.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        callback = getattr(self.backend, "stop_text_input", None)
        if not callable(callback):
            self.state.input.text_input_active = False
            return False
        stopped = bool(callback())
        self.state.input.text_input_active = not stopped
        return stopped

    def is_text_input_active(self) -> bool:
        """Is text input active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        callback = getattr(self.backend, "text_input_active", None)
        if callable(callback):
            self.state.input.text_input_active = bool(callback())
        return self.state.input.text_input_active

    def request_pointer_lock(self) -> bool:
        """Request pointer lock.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
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
        """Exit pointer lock.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
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


def _motion_distance(x: float, y: float, z: float) -> float:
    return (x * x + y * y + z * z) ** 0.5


def _motion_event_with_type(event: MotionEvent, event_type: str) -> MotionEvent:
    return MotionEvent(
        acceleration_x=event.acceleration_x,
        acceleration_y=event.acceleration_y,
        acceleration_z=event.acceleration_z,
        rotation_x=event.rotation_x,
        rotation_y=event.rotation_y,
        rotation_z=event.rotation_z,
        orientation=event.orientation,
        previous_acceleration_x=event.previous_acceleration_x,
        previous_acceleration_y=event.previous_acceleration_y,
        previous_acceleration_z=event.previous_acceleration_z,
        previous_rotation_x=event.previous_rotation_x,
        previous_rotation_y=event.previous_rotation_y,
        previous_rotation_z=event.previous_rotation_z,
        turn_axis=event.turn_axis,
        timestamp=event.timestamp,
        type=event_type,
    )
