"""Global-mode mouse, keyboard, touch, and pointer-lock wrappers."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.core.input_events import MotionEvent, TouchPoint


def mouse_x() -> float:
    """Return the current mouse x coordinate.

    Returns:
        The horizontal mouse position in logical canvas coordinates.
    """

    return require_context().mouse_x


def mouse_y() -> float:
    """Return the current mouse y coordinate.

    Returns:
        The vertical mouse position in logical canvas coordinates.
    """

    return require_context().mouse_y


def pmouse_x() -> float:
    """Return the previous frame's mouse x coordinate.

    Returns:
        The prior horizontal mouse position in logical canvas coordinates.
    """

    return require_context().pmouse_x


def pmouse_y() -> float:
    """Return the previous frame's mouse y coordinate.

    Returns:
        The prior vertical mouse position in logical canvas coordinates.
    """

    return require_context().pmouse_y


def moved_x() -> float:
    """Return horizontal mouse movement accumulated this frame.

    Returns:
        The change in logical x coordinates since the previous frame.
    """

    return require_context().moved_x


def moved_y() -> float:
    """Return vertical mouse movement accumulated this frame.

    Returns:
        The change in logical y coordinates since the previous frame.
    """

    return require_context().moved_y


def mouse_is_pressed() -> bool:
    """Return whether any mouse button is currently pressed.

    Returns:
        ``True`` while a mouse button is down.
    """

    return require_context().mouse_is_pressed


def mouse_is_inside_window() -> bool:
    """Return whether the pointer is inside the sketch window.

    Returns:
        ``True`` when the last pointer location is inside the active window.
    """

    return require_context().mouse_inside_window


def mouse_button() -> str | None:
    """Return the most recent mouse button name.

    Returns:
        A button name such as ``"left"`` or ``None`` when no button is known.
    """

    return require_context().mouse_button


def key() -> str | None:
    """Return the most recent key value.

    Returns:
        The latest key string, or ``None`` before any key event has occurred.
    """

    return require_context().key


def key_code() -> int | None:
    """Return the most recent keyboard key code.

    Returns:
        The latest numeric key code, or ``None`` before any key event has occurred.
    """

    return require_context().key_code


def key_is_pressed() -> bool:
    """Return whether a keyboard key is currently pressed.

    Returns:
        ``True`` while at least one key is down.
    """

    return require_context().key_is_pressed


def start_text_input() -> bool:
    """Begin text-input mode for receiving typed text events.

    Returns:
        ``True`` when the active backend supports and enabled text input.
    """

    return require_context().start_text_input()


def stop_text_input() -> bool:
    """Stop text-input mode.

    Returns:
        ``True`` when text input is inactive after the request.
    """

    return require_context().stop_text_input()


def is_text_input_active() -> bool:
    """Return whether text-input mode is active.

    Returns:
        ``True`` when typed text events are being requested from the backend.
    """

    return require_context().is_text_input_active()


def key_is_down(key_code: int | str) -> bool:
    """Return whether a specific key is currently held down.

    Args:
        key_code: Numeric key code, key name, or one-character key string to check.

    Returns:
        ``True`` when that key is currently pressed.
    """

    return require_context().key_is_down(key_code)


def touches() -> list[TouchPoint]:
    """Return the current active touch points.

    Returns:
        Touch points reported by the active backend in logical window coordinates.
    """

    return require_context().touches


def acceleration_x() -> float:
    """Return the latest device acceleration on the x axis.

    Returns:
        Acceleration value from the most recent sensor sample.
    """

    return require_context().state.input.acceleration_x


def acceleration_y() -> float:
    """Return the latest device acceleration on the y axis.

    Returns:
        Acceleration value from the most recent sensor sample.
    """

    return require_context().state.input.acceleration_y


def acceleration_z() -> float:
    """Return the latest device acceleration on the z axis.

    Returns:
        Acceleration value from the most recent sensor sample.
    """

    return require_context().state.input.acceleration_z


def p_acceleration_x() -> float:
    """Return the previous device acceleration on the x axis.

    Returns:
        X-axis acceleration from the previous sensor sample.
    """

    return require_context().state.input.previous_acceleration_x


def p_acceleration_y() -> float:
    """Return the previous device acceleration on the y axis.

    Returns:
        Y-axis acceleration from the previous sensor sample.
    """

    return require_context().state.input.previous_acceleration_y


def p_acceleration_z() -> float:
    """Return the previous device acceleration on the z axis.

    Returns:
        Z-axis acceleration from the previous sensor sample.
    """

    return require_context().state.input.previous_acceleration_z


def rotation_x() -> float:
    """Return the latest device rotation on the x axis.

    Returns:
        Rotation value from the most recent sensor sample.
    """

    return require_context().state.input.rotation_x


def rotation_y() -> float:
    """Return the latest device rotation on the y axis.

    Returns:
        Rotation value from the most recent sensor sample.
    """

    return require_context().state.input.rotation_y


def rotation_z() -> float:
    """Return the latest device rotation on the z axis.

    Returns:
        Rotation value from the most recent sensor sample.
    """

    return require_context().state.input.rotation_z


def p_rotation_x() -> float:
    """Return the previous device rotation on the x axis.

    Returns:
        X-axis rotation from the previous sensor sample.
    """

    return require_context().state.input.previous_rotation_x


def p_rotation_y() -> float:
    """Return the previous device rotation on the y axis.

    Returns:
        Y-axis rotation from the previous sensor sample.
    """

    return require_context().state.input.previous_rotation_y


def p_rotation_z() -> float:
    """Return the previous device rotation on the z axis.

    Returns:
        Z-axis rotation from the previous sensor sample.
    """

    return require_context().state.input.previous_rotation_z


def device_orientation() -> str:
    """Return the current device orientation label.

    Returns:
        Orientation string reported or inferred from the latest sensor sample.
    """

    return require_context().state.input.device_orientation


def turn_axis() -> str | None:
    """Return the axis that most recently triggered a turn event.

    Returns:
        Axis name when a turn was detected, otherwise ``None``.
    """

    return require_context().state.input.turn_axis


def set_move_threshold(value: float) -> None:
    """Set the acceleration-change threshold for ``device_moved`` events.

    Args:
        value: Minimum movement magnitude required to dispatch a movement event.
    """

    require_context().set_move_threshold(value)


def set_shake_threshold(value: float) -> None:
    """Set the acceleration threshold for ``device_shaken`` events.

    Args:
        value: Minimum acceleration magnitude required to dispatch a shake event.
    """

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
) -> MotionEvent:
    """Inject a synthetic device-motion sample into the active sketch.

    Args:
        acceleration_x: Optional x-axis acceleration value.
        acceleration_y: Optional y-axis acceleration value.
        acceleration_z: Optional z-axis acceleration value.
        rotation_x: Optional x-axis rotation value.
        rotation_y: Optional y-axis rotation value.
        rotation_z: Optional z-axis rotation value.
        orientation: Optional orientation label for the sample.

    Returns:
        The normalized motion event stored in the sketch input state.
    """

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
    """Request pointer lock for relative mouse movement.

    Returns:
        ``True`` when the active backend reports that pointer lock is active.
    """

    return require_context().request_pointer_lock()


def exit_pointer_lock() -> bool:
    """Release pointer lock if it is active.

    Returns:
        ``True`` when pointer lock is inactive after the request.
    """

    return require_context().exit_pointer_lock()


def pointer_lock_mode(mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
    """Get or set how pointer-lock movement is reported.

    Args:
        mode: Optional pointer-lock mode to set. Omit it to read the current mode.

    Returns:
        The active pointer-lock mode.
    """

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
