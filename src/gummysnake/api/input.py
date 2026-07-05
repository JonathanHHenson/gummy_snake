"""Global-mode mouse, keyboard, touch, and pointer-lock wrappers."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.core.input_events import TouchPoint


def mouse_x() -> float:
    return require_context().mouse_x


def mouse_y() -> float:
    return require_context().mouse_y


def pmouse_x() -> float:
    return require_context().pmouse_x


def pmouse_y() -> float:
    return require_context().pmouse_y


def moved_x() -> float:
    return require_context().moved_x


def moved_y() -> float:
    return require_context().moved_y


def mouse_is_pressed() -> bool:
    return require_context().mouse_is_pressed


def mouse_is_inside_window() -> bool:
    return require_context().mouse_inside_window


def mouse_button() -> str | None:
    return require_context().mouse_button


def key() -> str | None:
    return require_context().key


def key_code() -> int | None:
    return require_context().key_code


def key_is_pressed() -> bool:
    return require_context().key_is_pressed


def start_text_input() -> bool:
    return require_context().start_text_input()


def stop_text_input() -> bool:
    return require_context().stop_text_input()


def is_text_input_active() -> bool:
    return require_context().is_text_input_active()


def key_is_down(key_code: int | str) -> bool:
    return require_context().key_is_down(key_code)


def touches() -> list[TouchPoint]:
    return require_context().touches


def acceleration_x() -> float:
    return require_context().state.input.acceleration_x


def acceleration_y() -> float:
    return require_context().state.input.acceleration_y


def acceleration_z() -> float:
    return require_context().state.input.acceleration_z


def p_acceleration_x() -> float:
    return require_context().state.input.previous_acceleration_x


def p_acceleration_y() -> float:
    return require_context().state.input.previous_acceleration_y


def p_acceleration_z() -> float:
    return require_context().state.input.previous_acceleration_z


def rotation_x() -> float:
    return require_context().state.input.rotation_x


def rotation_y() -> float:
    return require_context().state.input.rotation_y


def rotation_z() -> float:
    return require_context().state.input.rotation_z


def p_rotation_x() -> float:
    return require_context().state.input.previous_rotation_x


def p_rotation_y() -> float:
    return require_context().state.input.previous_rotation_y


def p_rotation_z() -> float:
    return require_context().state.input.previous_rotation_z


def device_orientation() -> str:
    return require_context().state.input.device_orientation


def turn_axis() -> str | None:
    return require_context().state.input.turn_axis


def set_move_threshold(value: float) -> None:
    require_context().set_move_threshold(value)


def set_shake_threshold(value: float) -> None:
    require_context().set_shake_threshold(value)


def inject_sensor_sample(
    *,
    acceleration_x: float | None = None,
    acceleration_y: float | None = None,
    acceleration_z: float | None = None,
    rotation_x: float | None = None,
    rotation_y: float | None = None,
    rotation_z: float | None = None,
    orientation: str | None = None,
):
    return require_context().update_sensor_sample(
        acceleration_x=acceleration_x,
        acceleration_y=acceleration_y,
        acceleration_z=acceleration_z,
        rotation_x=rotation_x,
        rotation_y=rotation_y,
        rotation_z=rotation_z,
        orientation=orientation,
    )


def request_pointer_lock() -> bool:
    return require_context().request_pointer_lock()


def exit_pointer_lock() -> bool:
    return require_context().exit_pointer_lock()


def pointer_lock_mode(mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
    context = require_context()
    if mode is None:
        return context.pointer_lock_mode()
    return context.set_pointer_lock_mode(mode)


__all__ = [
    "mouse_x",
    "mouse_y",
    "pmouse_x",
    "pmouse_y",
    "moved_x",
    "moved_y",
    "mouse_is_pressed",
    "mouse_is_inside_window",
    "mouse_button",
    "key",
    "key_code",
    "key_is_pressed",
    "start_text_input",
    "stop_text_input",
    "is_text_input_active",
    "key_is_down",
    "touches",
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "p_acceleration_x",
    "p_acceleration_y",
    "p_acceleration_z",
    "rotation_x",
    "rotation_y",
    "rotation_z",
    "p_rotation_x",
    "p_rotation_y",
    "p_rotation_z",
    "device_orientation",
    "turn_axis",
    "set_move_threshold",
    "set_shake_threshold",
    "inject_sensor_sample",
    "request_pointer_lock",
    "exit_pointer_lock",
    "pointer_lock_mode",
]
