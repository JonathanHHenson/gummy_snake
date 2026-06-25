"""Global-mode timing, environment, and input wrappers."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.events.input_state import TouchPoint


def frame_rate(value: float | None = None) -> float:
    return require_context().frame_rate(value)


def frame_count() -> int:
    return require_context().frame_count


def delta_time() -> float:
    return require_context().delta_time


def millis() -> float:
    return require_context().millis()


def no_loop() -> None:
    require_context().no_loop()


def loop() -> None:
    require_context().loop()


def redraw() -> None:
    require_context().redraw()


def is_looping() -> bool:
    return require_context().is_looping()


def get_target_frame_rate() -> float:
    return require_context().frame_rate()


def window_width() -> int:
    return require_context().width


def window_height() -> int:
    return require_context().height


def display_width() -> int:
    context = require_context()
    return round(context.width * context.display_density())


def display_height() -> int:
    context = require_context()
    return round(context.height * context.display_density())


def focused() -> bool:
    """Return whether the sketch is focused.

    The current canvas runtime exposes this as a portable compatibility helper:
    headless and backend-agnostic sketches are considered focused.
    """

    return True


def cursor(_kind: str | None = None) -> None:
    """Accept cursor changes as a portable no-op in the current canvas runtime."""

    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def no_cursor() -> None:
    """Accept cursor hiding as a portable no-op in the current canvas runtime."""

    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def mouse_x() -> float:
    return require_context().mouse_x


def mouse_y() -> float:
    return require_context().mouse_y


def pmouse_x() -> float:
    return require_context().pmouse_x


def pmouse_y() -> float:
    return require_context().pmouse_y


def moved_x() -> float:
    return require_context().moved_x


def moved_y() -> float:
    return require_context().moved_y


def mouse_is_pressed() -> bool:
    return require_context().mouse_is_pressed


def mouse_is_inside_window() -> bool:
    return require_context().mouse_inside_window


def mouse_button() -> str | None:
    return require_context().mouse_button


def key() -> str | None:
    return require_context().key


def key_code() -> int | None:
    return require_context().key_code


def key_is_pressed() -> bool:
    return require_context().key_is_pressed


def start_text_input() -> bool:
    return require_context().start_text_input()


def stop_text_input() -> bool:
    return require_context().stop_text_input()


def is_text_input_active() -> bool:
    return require_context().is_text_input_active()


def key_is_down(key_code: int | str) -> bool:
    return require_context().key_is_down(key_code)


def touches() -> list[TouchPoint]:
    return require_context().touches


def request_pointer_lock() -> bool:
    return require_context().request_pointer_lock()


def exit_pointer_lock() -> bool:
    return require_context().exit_pointer_lock()


def pointer_lock_mode(mode: c.PointerLockMode | str | None = None) -> c.PointerLockMode:
    context = require_context()
    if mode is None:
        return context.pointer_lock_mode()
    return context.set_pointer_lock_mode(mode)
