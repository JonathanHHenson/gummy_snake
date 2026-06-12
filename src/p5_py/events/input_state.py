"""Backend-normalized input state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MouseEvent:
    x: float
    y: float
    button: str | None = None
    dx: float = 0.0
    dy: float = 0.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    type: str = "mouse"


@dataclass(slots=True)
class KeyboardEvent:
    key: str | None = None
    key_code: int | None = None
    modifiers: int | None = None
    type: str = "keyboard"


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

    def update_mouse(self, x: float, y: float) -> None:
        self.previous_mouse_x = self.mouse_x
        self.previous_mouse_y = self.mouse_y
        self.mouse_x = x
        self.mouse_y = y
        self.moved_x = self.mouse_x - self.previous_mouse_x
        self.moved_y = self.mouse_y - self.previous_mouse_y

    def key_is_down(self, key_code: int) -> bool:
        return key_code in self.pressed_keys
