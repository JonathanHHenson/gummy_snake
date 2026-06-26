"""Input state forwards for object sketches."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.events.input_state import TouchPoint
from gummysnake.sketch._facade.base import SketchFacadeBaseMixin


class SketchFacadeInputMixin(SketchFacadeBaseMixin):
    @property
    def mouse_x(self) -> float:
        return self._ctx.mouse_x

    @property
    def mouse_y(self) -> float:
        return self._ctx.mouse_y

    @property
    def pmouse_x(self) -> float:
        return self._ctx.pmouse_x

    @property
    def pmouse_y(self) -> float:
        return self._ctx.pmouse_y

    @property
    def moved_x(self) -> float:
        return self._ctx.moved_x

    @property
    def moved_y(self) -> float:
        return self._ctx.moved_y

    @property
    def mouse_is_pressed(self) -> bool:
        return self._ctx.mouse_is_pressed

    @property
    def mouse_inside_window(self) -> bool:
        return self._ctx.mouse_inside_window

    @property
    def mouse_button(self) -> str | None:
        return self._ctx.mouse_button

    @property
    def key(self) -> str | None:
        return self._ctx.key

    @property
    def key_code(self) -> int | None:
        return self._ctx.key_code

    @property
    def code(self) -> str | None:
        return self._ctx.code

    @property
    def typed_text(self) -> str | None:
        return self._ctx.typed_text

    @property
    def key_is_pressed(self) -> bool:
        return self._ctx.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        return self._ctx.touches

    def key_is_down(self, key_code: int | str) -> bool:
        return self._ctx.key_is_down(key_code)

    def start_text_input(self) -> bool:
        return self._ctx.start_text_input()

    def stop_text_input(self) -> bool:
        return self._ctx.stop_text_input()

    def is_text_input_active(self) -> bool:
        return self._ctx.is_text_input_active()

    def request_pointer_lock(self) -> bool:
        return self._ctx.request_pointer_lock()

    def exit_pointer_lock(self) -> bool:
        return self._ctx.exit_pointer_lock()

    def pointer_lock_mode(self, mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
        if mode is None:
            return self._ctx.pointer_lock_mode()
        return self._ctx.set_pointer_lock_mode(mode)
