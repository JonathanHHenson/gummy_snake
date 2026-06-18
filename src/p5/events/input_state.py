"""Backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field

from p5 import constants as c
from p5.exceptions import BackendCapabilityError


@dataclass(slots=True)
class MouseEvent:
    x: float
    y: float
    button: str | None = None
    dx: float = 0.0
    dy: float = 0.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    modifiers: int | None = None
    type: str = "mouse"


@dataclass(slots=True)
class KeyboardEvent:
    key: str | None = None
    key_code: int | None = None
    modifiers: int | None = None
    type: str = "keyboard"


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
    mouse_button: str | None = None
    key: str | None = None
    key_code: int | None = None
    key_is_pressed: bool = False
    pressed_keys: set[int] = field(default_factory=set)
    touches: list[TouchPoint] = field(default_factory=list)
    touch_supported: bool = False

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

    def key_is_down(self, key_code: int) -> bool:
        return key_code in self.pressed_keys
