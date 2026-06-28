"""Global-mode mouse, keyboard, touch, and pointer-lock wrappers."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.core.input_events import TouchPoint


def mouse_x() -> float:
    """Mouse x using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().mouse_x


def mouse_y() -> float:
    """Mouse y using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().mouse_y


def pmouse_x() -> float:
    """Return the previous mouse x coordinate.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().pmouse_x


def pmouse_y() -> float:
    """Return the previous mouse y coordinate.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().pmouse_y


def moved_x() -> float:
    """Moved x using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().moved_x


def moved_y() -> float:
    """Moved y using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().moved_y


def mouse_is_pressed() -> bool:
    """Mouse is pressed using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().mouse_is_pressed


def mouse_is_inside_window() -> bool:
    """Mouse is inside window using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().mouse_inside_window


def mouse_button() -> str | None:
    """Mouse button using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `str | None`.
    """
    return require_context().mouse_button


def key() -> str | None:
    """Key using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `str | None`.
    """
    return require_context().key


def key_code() -> int | None:
    """Key code using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int | None`.
    """
    return require_context().key_code


def key_is_pressed() -> bool:
    """Key is pressed using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().key_is_pressed


def start_text_input() -> bool:
    """Start text input using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().start_text_input()


def stop_text_input() -> bool:
    """Stop text input using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().stop_text_input()


def is_text_input_active() -> bool:
    """Return whether text input active is active.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().is_text_input_active()


def key_is_down(key_code: int | str) -> bool:
    """Key is down using the active input context.
    
    Args:
        key_code: The key code value. Expected type: `int | str`.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().key_is_down(key_code)


def touches() -> list[TouchPoint]:
    """Touches using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `list[TouchPoint]`.
    """
    return require_context().touches


def acceleration_x() -> float:
    """Acceleration x using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.acceleration_x


def acceleration_y() -> float:
    """Acceleration y using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.acceleration_y


def acceleration_z() -> float:
    """Acceleration z using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.acceleration_z


def p_acceleration_x() -> float:
    """Return the previous device acceleration on the x axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_acceleration_x


def p_acceleration_y() -> float:
    """Return the previous device acceleration on the y axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_acceleration_y


def p_acceleration_z() -> float:
    """Return the previous device acceleration on the z axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_acceleration_z


def rotation_x() -> float:
    """Rotation x using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.rotation_x


def rotation_y() -> float:
    """Rotation y using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.rotation_y


def rotation_z() -> float:
    """Rotation z using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.rotation_z


def p_rotation_x() -> float:
    """Return the previous device rotation around the x axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_rotation_x


def p_rotation_y() -> float:
    """Return the previous device rotation around the y axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_rotation_y


def p_rotation_z() -> float:
    """Return the previous device rotation around the z axis.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().state.input.previous_rotation_z


def device_orientation() -> str:
    """Device orientation using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `str`.
    """
    return require_context().state.input.device_orientation


def turn_axis() -> str | None:
    """Turn axis using the active input context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `str | None`.
    """
    return require_context().state.input.turn_axis


def set_move_threshold(value: float) -> None:
    """Set the move threshold value.
    
    Args:
        value: The value value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().set_move_threshold(value)


def set_shake_threshold(value: float) -> None:
    """Set the shake threshold value.
    
    Args:
        value: The value value. Expected type: `float`.
    
    Returns:
        None.
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
):
    """Inject sensor sample using the active input context.
    
    Args:
        acceleration_x: The acceleration x value. Expected type: `float | None`. Defaults to `None`.
        acceleration_y: The acceleration y value. Expected type: `float | None`. Defaults to `None`.
        acceleration_z: The acceleration z value. Expected type: `float | None`. Defaults to `None`.
        rotation_x: The rotation x value. Expected type: `float | None`. Defaults to `None`.
        rotation_y: The rotation y value. Expected type: `float | None`. Defaults to `None`.
        rotation_z: The rotation z value. Expected type: `float | None`. Defaults to `None`.
        orientation: The orientation value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value.
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
    """Request pointer lock from the active backend.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().request_pointer_lock()


def exit_pointer_lock() -> bool:
    """Exit pointer lock mode on the active backend.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().exit_pointer_lock()


def pointer_lock_mode(mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
    """Return or set the pointer-lock movement mode.
    
    Args:
        mode: The mode value. Expected type: `c.PointerLockMode | str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `c.PointerLockMode`.
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
