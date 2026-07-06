"""Input snapshot state facade."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.core.input_events import MotionEvent, TouchPoint, _update_motion_state


class InputState:
    """Compatibility facade for Rust-owned input snapshots."""

    acceleration_x: float
    acceleration_y: float
    acceleration_z: float
    previous_acceleration_x: float
    previous_acceleration_y: float
    previous_acceleration_z: float
    rotation_x: float
    rotation_y: float
    rotation_z: float
    previous_rotation_x: float
    previous_rotation_y: float
    previous_rotation_z: float
    device_orientation: str
    turn_axis: str | None
    move_threshold: float
    shake_threshold: float

    __slots__ = (
        "_rust",
        "acceleration_x",
        "acceleration_y",
        "acceleration_z",
        "previous_acceleration_x",
        "previous_acceleration_y",
        "previous_acceleration_z",
        "rotation_x",
        "rotation_y",
        "rotation_z",
        "previous_rotation_x",
        "previous_rotation_y",
        "previous_rotation_z",
        "device_orientation",
        "turn_axis",
        "move_threshold",
        "shake_threshold",
    )

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state
        self.acceleration_x = 0.0
        self.acceleration_y = 0.0
        self.acceleration_z = 0.0
        self.previous_acceleration_x = 0.0
        self.previous_acceleration_y = 0.0
        self.previous_acceleration_z = 0.0
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self.rotation_z = 0.0
        self.previous_rotation_x = 0.0
        self.previous_rotation_y = 0.0
        self.previous_rotation_z = 0.0
        self.device_orientation = "unknown"
        self.turn_axis = None
        self.move_threshold = 0.5
        self.shake_threshold = 30.0

    @property
    def mouse_x(self) -> float:
        return float(self._rust.mouse_x)

    @property
    def mouse_y(self) -> float:
        return float(self._rust.mouse_y)

    @property
    def previous_mouse_x(self) -> float:
        return float(self._rust.previous_mouse_x)

    @previous_mouse_x.setter
    def previous_mouse_x(self, value: float) -> None:
        self._rust.previous_mouse_x = float(value)

    @property
    def previous_mouse_y(self) -> float:
        return float(self._rust.previous_mouse_y)

    @previous_mouse_y.setter
    def previous_mouse_y(self, value: float) -> None:
        self._rust.previous_mouse_y = float(value)

    @property
    def moved_x(self) -> float:
        return float(self._rust.moved_x)

    @property
    def moved_y(self) -> float:
        return float(self._rust.moved_y)

    @property
    def mouse_is_pressed(self) -> bool:
        return bool(self._rust.mouse_is_pressed)

    @mouse_is_pressed.setter
    def mouse_is_pressed(self, value: bool) -> None:
        self._rust.mouse_is_pressed = bool(value)

    @property
    def mouse_inside_window(self) -> bool:
        return bool(self._rust.mouse_inside_window)

    @mouse_inside_window.setter
    def mouse_inside_window(self, value: bool) -> None:
        self._rust.mouse_inside_window = bool(value)

    @property
    def mouse_button(self) -> str | None:
        return self._rust.mouse_button

    @mouse_button.setter
    def mouse_button(self, value: str | None) -> None:
        self._rust.mouse_button = value

    @property
    def key(self) -> str | None:
        return self._rust.key

    @key.setter
    def key(self, value: str | None) -> None:
        self._rust.key = value

    @property
    def key_code(self) -> int | None:
        value = self._rust.key_code
        return None if value is None else int(value)

    @key_code.setter
    def key_code(self, value: int | None) -> None:
        self._rust.key_code = None if value is None else int(value)

    @property
    def code(self) -> str | None:
        return self._rust.code

    @code.setter
    def code(self, value: str | None) -> None:
        self._rust.code = value

    @property
    def text(self) -> str | None:
        return self._rust.text

    @text.setter
    def text(self, value: str | None) -> None:
        self._rust.text = value

    @property
    def text_input_active(self) -> bool:
        return bool(self._rust.text_input_active)

    @text_input_active.setter
    def text_input_active(self, value: bool) -> None:
        self._rust.text_input_active = bool(value)

    @property
    def key_is_pressed(self) -> bool:
        return bool(self._rust.key_is_pressed)

    @key_is_pressed.setter
    def key_is_pressed(self, value: bool) -> None:
        self._rust.key_is_pressed = bool(value)

    @property
    def touches(self) -> list[TouchPoint]:
        return [TouchPoint(**dict(payload)) for payload in self._rust.touch_payload()]

    @touches.setter
    def touches(self, value: list[TouchPoint]) -> None:
        self._rust.update_touches(value)

    @property
    def touch_supported(self) -> bool:
        return bool(self._rust.touch_supported)

    @touch_supported.setter
    def touch_supported(self, value: bool) -> None:
        self._rust.touch_supported = bool(value)

    @property
    def pointer_locked(self) -> bool:
        return bool(self._rust.pointer_locked)

    @pointer_locked.setter
    def pointer_locked(self, value: bool) -> None:
        self._rust.pointer_locked = bool(value)

    @property
    def pointer_lock_mode(self) -> c.PointerLockMode:
        return c.PointerLockMode(str(self._rust.pointer_lock_mode))

    @pointer_lock_mode.setter
    def pointer_lock_mode(self, value: c.PointerLockMode | str) -> None:
        self._rust.pointer_lock_mode = c.PointerLockMode(str(value)).value

    def set_key_down(self, key_code: int, pressed: bool) -> None:
        self._rust.set_key_down(int(key_code), bool(pressed))

    def set_code_down(self, code: str, pressed: bool) -> None:
        self._rust.set_code_down(str(code), bool(pressed))

    def update_mouse(
        self, x: float, y: float, *, dx: float | None = None, dy: float | None = None
    ) -> None:
        self._rust.update_mouse(float(x), float(y), dx, dy)

    def update_touches(self, touches: list[TouchPoint]) -> None:
        self._rust.update_touches(touches)

    def update_motion(
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
        return _update_motion_state(
            self,
            acceleration_x=acceleration_x,
            acceleration_y=acceleration_y,
            acceleration_z=acceleration_z,
            rotation_x=rotation_x,
            rotation_y=rotation_y,
            rotation_z=rotation_z,
            orientation=orientation,
        )

    def require_touch_supported(self) -> None:
        if not self.touch_supported:
            from gummysnake.exceptions import BackendCapabilityError

            raise BackendCapabilityError(
                "Touch input is not supported by the active backend yet. "
                "The touch API is present so capable future backends can provide "
                f"{c.TOUCH_STARTED}, {c.TOUCH_MOVED}, and {c.TOUCH_ENDED} events."
            )

    def key_is_down(self, key_code: int) -> bool:
        return bool(self._rust.key_is_down(int(key_code)))

    def code_is_down(self, code: str) -> bool:
        return bool(self._rust.code_is_down(code))
