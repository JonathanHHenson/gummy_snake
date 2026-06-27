"""Input and callback enum values."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class MouseButton(StrEnum):
    """Normalized mouse button names."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class PointerLockMode(StrEnum):
    """Pointer-lock coordinate handling modes."""

    UNCLAMPED = "unclamped"
    CLAMPED = "clamped"
    FIXED = "fixed"


class KeyCode(IntEnum):
    """Gummy Snake-style public keyboard key code values."""

    BACKSPACE = 8
    TAB = 9
    ENTER = 13
    ESCAPE = 27
    SHIFT = 16
    CONTROL = 17
    ALT = 18
    UP_ARROW = 38
    DOWN_ARROW = 40
    LEFT_ARROW = 37
    RIGHT_ARROW = 39


class TouchEventName(StrEnum):
    """Normalized touch callback/event names."""

    TOUCH_STARTED = "touch_started"
    TOUCH_MOVED = "touch_moved"
    TOUCH_ENDED = "touch_ended"


class CallbackEventName(StrEnum):
    """Normalized sketch callback/event names accepted by ``on()``."""

    MOUSE_MOVED = "mouse_moved"
    MOUSE_DRAGGED = "mouse_dragged"
    MOUSE_PRESSED = "mouse_pressed"
    MOUSE_RELEASED = "mouse_released"
    MOUSE_CLICKED = "mouse_clicked"
    MOUSE_DOUBLE_CLICKED = "mouse_double_clicked"
    MOUSE_WHEEL = "mouse_wheel"
    KEY_PRESSED = "key_pressed"
    KEY_RELEASED = "key_released"
    KEY_TYPED = "key_typed"
    TOUCH_STARTED = "touch_started"
    TOUCH_MOVED = "touch_moved"
    TOUCH_ENDED = "touch_ended"
    TOUCH_CANCELLED = "touch_cancelled"
    DEVICE_MOVED = "device_moved"
    DEVICE_TURNED = "device_turned"
    DEVICE_SHAKEN = "device_shaken"


__all__ = [
    "CallbackEventName",
    "KeyCode",
    "MouseButton",
    "PointerLockMode",
    "TouchEventName",
]
