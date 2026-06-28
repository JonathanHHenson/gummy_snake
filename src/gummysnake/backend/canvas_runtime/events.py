"""Canvas backend runtime event normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.exceptions import BackendCapabilityError

MOUSE_EVENT_TYPES = {
    "mouse_moved",
    "mouse_dragged",
    "mouse_pressed",
    "mouse_released",
    "mouse_clicked",
    "mouse_double_clicked",
    "mouse_wheel",
}

KEYBOARD_EVENT_TYPES = {"key_pressed", "key_released", "key_typed"}
TOUCH_EVENT_TYPES = {"touch_started", "touch_moved", "touch_ended", "touch_cancelled"}

SPECIAL_KEY_CODES = {
    "space": ord(" "),
    "spacebar": ord(" "),
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

MOUSE_BUTTONS = {
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


def event_mapping(payload: object) -> Mapping[str, object]:
    """Event mapping.
    
    Args:
        payload: The payload value. Expected type: `object`.
    
    Returns:
        The return value. Type: `Mapping[str, object]`.
    """
    if isinstance(payload, Mapping):
        return cast(Mapping[str, object], payload)
    as_dict = getattr(payload, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    raise BackendCapabilityError("Canvas runtime events must be mappings or expose as_dict().")


def float_payload(
    payload: Mapping[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float:
    """Float payload.
    
    Args:
        payload: The payload value. Expected type: `Mapping[str, object]`.
        key: The key value. Expected type: `str`.
        default: The default value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `float`.
    """
    value: Any = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return float(value)


def int_payload(
    payload: Mapping[str, object],
    key: str,
    *,
    default: int | None = None,
) -> int:
    """Int payload.
    
    Args:
        payload: The payload value. Expected type: `Mapping[str, object]`.
        key: The key value. Expected type: `str`.
        default: The default value. Expected type: `int | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `int`.
    """
    value: Any = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return int(value)


def bool_payload(
    payload: Mapping[str, object],
    key: str,
    *,
    default: bool | None = None,
) -> bool:
    """Bool payload.
    
    Args:
        payload: The payload value. Expected type: `Mapping[str, object]`.
        key: The key value. Expected type: `str`.
        default: The default value. Expected type: `bool | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `bool`.
    """
    value: Any = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return bool_value(value)


def optional_int(value: object) -> int | None:
    """Optional int.
    
    Args:
        value: The value value. Expected type: `object`.
    
    Returns:
        The return value. Type: `int | None`.
    """
    raw_value: Any = value
    return None if raw_value is None else int(raw_value)


def optional_float(value: object) -> float | None:
    """Optional float.
    
    Args:
        value: The value value. Expected type: `object`.
    
    Returns:
        The return value. Type: `float | None`.
    """
    raw_value: Any = value
    return None if raw_value is None else float(raw_value)


def optional_bool(value: object) -> bool | None:
    """Optional bool.
    
    Args:
        value: The value value. Expected type: `object`.
    
    Returns:
        The return value. Type: `bool | None`.
    """
    return None if value is None else bool_value(value)


def bool_value(value: object) -> bool:
    """Bool value.
    
    Args:
        value: The value value. Expected type: `object`.
    
    Returns:
        The return value. Type: `bool`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_mouse_button(button: object) -> str | None:
    """Normalize mouse button.
    
    Args:
        button: The button value. Expected type: `object`.
    
    Returns:
        The return value. Type: `str | None`.
    """
    if button is None:
        return None
    normalized = MOUSE_BUTTONS.get(button)
    if normalized is not None:
        return normalized
    return MOUSE_BUTTONS.get(str(button).lower(), str(button))


def normalize_key_code(key_code: object, key: str | None = None) -> int | None:
    """Normalize key code.
    
    Args:
        key_code: The key code value. Expected type: `object`.
        key: The key value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `int | None`.
    """
    if key_code is None:
        if key is not None and len(key) == 1:
            return ord(key)
        return None
    if isinstance(key_code, int):
        return key_code
    if isinstance(key_code, float):
        return int(key_code)
    text = str(key_code)
    special = SPECIAL_KEY_CODES.get(text.lower())
    if special is not None:
        return special
    if len(text) == 1:
        return ord(text)
    if key is not None and len(key) == 1:
        return ord(key)
    return None
