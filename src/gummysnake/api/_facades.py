"""Property-style global-mode facades."""

from __future__ import annotations

from gummysnake.api.current import require_context
from gummysnake.core.vector import Vector, create_vector


class CurrentFacade:
    @property
    def width(self) -> int:
        return require_context().width

    @property
    def height(self) -> int:
        return require_context().height

    @property
    def frame_count(self) -> int:
        return require_context().frame_count

    @property
    def delta_time(self) -> float:
        return require_context().delta_time

    @property
    def pixel_density(self) -> float:
        return require_context().pixel_density()

    @property
    def display_density(self) -> float:
        return require_context().display_density()

    @property
    def is_looping(self) -> bool:
        return require_context().is_looping()


class MouseFacade:
    @property
    def x(self) -> float:
        return require_context().mouse_x

    @property
    def y(self) -> float:
        return require_context().mouse_y

    @property
    def previous_x(self) -> float:
        return require_context().pmouse_x

    @property
    def previous_y(self) -> float:
        return require_context().pmouse_y

    @property
    def moved_x(self) -> float:
        return require_context().moved_x

    @property
    def moved_y(self) -> float:
        return require_context().moved_y

    @property
    def is_pressed(self) -> bool:
        return require_context().mouse_is_pressed

    @property
    def button(self) -> str | None:
        return require_context().mouse_button

    @property
    def position(self) -> Vector:
        return create_vector(self.x, self.y)

    @property
    def previous_position(self) -> Vector:
        return create_vector(self.previous_x, self.previous_y)


class KeyboardFacade:
    @property
    def key(self) -> str | None:
        return require_context().key

    @property
    def code(self) -> int | None:
        return require_context().key_code

    @property
    def is_pressed(self) -> bool:
        return require_context().key_is_pressed

    def is_down(self, key_code: int | str) -> bool:
        if isinstance(key_code, str):
            if len(key_code) != 1:
                raise ValueError("keyboard.is_down() string keys must be one character.")
            context = require_context()
            return context.key_is_down(ord(key_code.lower())) or context.key_is_down(
                ord(key_code.upper())
            )
        return require_context().key_is_down(key_code)


current = CurrentFacade()
mouse = MouseFacade()
keyboard = KeyboardFacade()
