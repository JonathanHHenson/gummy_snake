"""Backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field

from gummysnake import constants as c
from gummysnake.core.vector import Vector
from gummysnake.exceptions import BackendCapabilityError

_SPACE_KEY_NAMES = {"space", "spacebar"}


@dataclass(slots=True)
class MouseEvent:
    x: float
    y: float
    button: str | None = None
    dx: float = 0.0
    dy: float = 0.0
    previous_x: float | None = None
    previous_y: float | None = None
    window_x: float | None = None
    window_y: float | None = None
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    click_count: int = 0
    modifiers: int | None = None
    inside_window: bool | None = None
    type: str = "mouse"

    @property
    def position(self) -> Vector:
        return Vector(self.x, self.y)

    @property
    def delta(self) -> Vector:
        return Vector(self.dx, self.dy)

    @property
    def previous_position(self) -> Vector | None:
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def window_position(self) -> Vector | None:
        if self.window_x is None or self.window_y is None:
            return None
        return Vector(self.window_x, self.window_y)

    @property
    def scroll(self) -> Vector:
        return Vector(self.scroll_x, self.scroll_y)


@dataclass(slots=True)
class KeyboardEvent:
    key: str | None = None
    key_code: int | None = None
    code: str | None = None
    text: str | None = None
    repeat: bool = False
    modifiers: int | None = None
    type: str = "keyboard"

    def matches(self, value: str | int) -> bool:
        if isinstance(value, int):
            return self.key_code == value
        if self.key == value:
            return True
        if len(value) == 1 and self.key_code == ord(value):
            return True
        if value == " " and self.key is not None and self.key.lower() in _SPACE_KEY_NAMES:
            return True
        return value.lower() in _SPACE_KEY_NAMES and self.key == " "


@dataclass(slots=True)
class TouchPoint:
    id: int
    x: float
    y: float
    previous_x: float | None = None
    previous_y: float | None = None
    pressure: float | None = None
    phase: str | None = None
    timestamp: float | None = None
    device: str | None = None

    @property
    def position(self) -> Vector:
        return Vector(self.x, self.y)

    @property
    def previous_position(self) -> Vector | None:
        if self.previous_x is None or self.previous_y is None:
            return None
        return Vector(self.previous_x, self.previous_y)

    @property
    def delta(self) -> Vector | None:
        previous = self.previous_position
        if previous is None:
            return None
        return self.position - previous


@dataclass(slots=True)
class TouchEvent:
    touches: list[TouchPoint] = field(default_factory=list)
    changed_touches: list[TouchPoint] = field(default_factory=list)
    type: str = "touch"


@dataclass(slots=True)
class InputState:
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
