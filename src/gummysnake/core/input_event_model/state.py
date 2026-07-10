"""Mutable backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field

from gummysnake import constants as c
from gummysnake.core.input_event_model.events import MotionEvent, TouchPoint, _update_motion_state
from gummysnake.exceptions import BackendCapabilityError


@dataclass(slots=True)
class InputState:
    """Public InputState value."""

    mouse_x: float = 0.0
    mouse_y: float = 0.0
    previous_mouse_x: float = 0.0
    previous_mouse_y: float = 0.0
    moved_x: float = 0.0
    moved_y: float = 0.0
    mouse_is_pressed: bool = False
    mouse_inside_window: bool = False
    mouse_button: str | None = None
    key: str | None = None
    key_code: int | None = None
    code: str | None = None
    text: str | None = None
    text_input_active: bool = False
    key_is_pressed: bool = False
    pressed_keys: set[int] = field(default_factory=set)
    pressed_codes: set[str] = field(default_factory=set)
    touches: list[TouchPoint] = field(default_factory=list)
    touch_supported: bool = False
    pointer_locked: bool = False
    pointer_lock_mode: c.PointerLockMode = c.CLAMPED
    acceleration_x: float = 0.0
    acceleration_y: float = 0.0
    acceleration_z: float = 0.0
    previous_acceleration_x: float = 0.0
    previous_acceleration_y: float = 0.0
    previous_acceleration_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    previous_rotation_x: float = 0.0
    previous_rotation_y: float = 0.0
    previous_rotation_z: float = 0.0
    device_orientation: str = "unknown"
    turn_axis: str | None = None
    move_threshold: float = 0.5
    shake_threshold: float = 30.0

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

    def update_mouse(
        self, x: float, y: float, *, dx: float | None = None, dy: float | None = None
    ) -> None:
        self.previous_mouse_x = self.mouse_x
        self.previous_mouse_y = self.mouse_y
        self.mouse_x = x
        self.mouse_y = y
        self.moved_x = self.mouse_x - self.previous_mouse_x if dx is None else dx
        self.moved_y = self.mouse_y - self.previous_mouse_y if dy is None else dy

    def update_touches(self, touches: list[TouchPoint]) -> None:
        previous = {touch.id: touch for touch in self.touches}
        updated: list[TouchPoint] = []
        for touch in touches:
            old = previous.get(touch.id)
            updated.append(
                TouchPoint(
                    id=touch.id,
                    x=touch.x,
                    y=touch.y,
                    previous_x=touch.previous_x
                    if touch.previous_x is not None
                    else getattr(old, "x", None),
                    previous_y=touch.previous_y
                    if touch.previous_y is not None
                    else getattr(old, "y", None),
                    pressure=touch.pressure,
                    phase=touch.phase,
                    timestamp=touch.timestamp,
                    device=touch.device,
                )
            )
        self.touches = updated

    def require_touch_supported(self) -> None:
        if not self.touch_supported:
            raise BackendCapabilityError(
                "Touch input is not supported by the active backend yet. "
                "The touch API is present so capable future backends can provide "
                f"{c.TOUCH_STARTED}, {c.TOUCH_MOVED}, and {c.TOUCH_ENDED} events."
            )

    def set_key_down(self, key_code: int, pressed: bool) -> None:
        if pressed:
            self.pressed_keys.add(key_code)
        else:
            self.pressed_keys.discard(key_code)

    def set_code_down(self, code: str, pressed: bool) -> None:
        if pressed:
            self.pressed_codes.add(code)
        else:
            self.pressed_codes.discard(code)

    def key_is_down(self, key_code: int) -> bool:
        return key_code in self.pressed_keys

    def code_is_down(self, code: str) -> bool:
        return code in self.pressed_codes
