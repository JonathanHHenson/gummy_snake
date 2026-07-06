"""Canvas backend runtime event normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from gummysnake import constants as c
from gummysnake.exceptions import BackendCapabilityError

type CanvasEventValue = None | bool | int | float | str
type CanvasEventPayload = Mapping[str, CanvasEventValue]


class _CanvasEventRecord(Protocol):
    def as_dict(self) -> CanvasEventPayload: ...


type CanvasEventSource = CanvasEventPayload | _CanvasEventRecord


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

SPECIAL_KEY_CODES: dict[str, int] = {
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

MOUSE_BUTTONS: dict[str | int | float, str] = {
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


def event_mapping(payload: CanvasEventSource) -> CanvasEventPayload:
    """Return a plain mapping for a Rust canvas event payload."""
    if isinstance(payload, Mapping):
        return cast(CanvasEventPayload, payload)
    as_dict = getattr(payload, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if isinstance(value, Mapping):
            return cast(CanvasEventPayload, value)
    raise BackendCapabilityError("Canvas runtime events must be mappings or expose as_dict().")


def float_payload(
    payload: CanvasEventPayload,
    key: str,
    *,
    default: float | None = None,
) -> float:
    """Read a required or defaulted event field as a float."""
    value = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return float(value)


def int_payload(
    payload: CanvasEventPayload,
    key: str,
    *,
    default: int | None = None,
) -> int:
    """Read a required or defaulted event field as an integer."""
    value = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return int(value)


def bool_payload(
    payload: CanvasEventPayload,
    key: str,
    *,
    default: bool | None = None,
) -> bool:
    """Read a required or defaulted event field as a boolean."""
    value = payload.get(key, default)
    if value is None:
        raise BackendCapabilityError(f"Canvas event payload is missing {key!r}.")
    return bool_value(value)


def optional_int(value: CanvasEventValue) -> int | None:
    """Convert a nullable event value to an integer."""
    return None if value is None else int(value)


def optional_float(value: CanvasEventValue) -> float | None:
    """Convert a nullable event value to a float."""
    return None if value is None else float(value)


def optional_bool(value: CanvasEventValue) -> bool | None:
    """Convert a nullable event value to a boolean."""
    return None if value is None else bool_value(value)


def bool_value(value: CanvasEventValue) -> bool:
    """Interpret common string and numeric event values as booleans."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_mouse_button(button: CanvasEventValue) -> str | None:
    """Map a canvas runtime mouse button value to Gummy Snake's button names."""
    if button is None:
        return None
    normalized = MOUSE_BUTTONS.get(button)
    if normalized is not None:
        return normalized
    return MOUSE_BUTTONS.get(str(button).lower(), str(button))


def normalize_key_code(key_code: CanvasEventValue, key: str | None = None) -> int | None:
    """Map a canvas runtime key code value to a public keyboard code."""
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
