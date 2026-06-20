"""Global-mode timing, environment, and input wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


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
    return True


def cursor(_kind: str | None = None) -> None:
    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def no_cursor() -> None:
    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def mouse_x() -> float:
    return require_context().state.input.mouse_x


def mouse_y() -> float:
    return require_context().state.input.mouse_y


def pmouse_x() -> float:
    return require_context().state.input.previous_mouse_x


def pmouse_y() -> float:
    return require_context().state.input.previous_mouse_y


def moved_x() -> float:
    return require_context().moved_x


def moved_y() -> float:
    return require_context().moved_y


def mouse_is_pressed() -> bool:
    return require_context().mouse_is_pressed


def mouse_button() -> str | None:
    return require_context().mouse_button


def key() -> str | None:
    return require_context().key


def key_code() -> int | None:
    return require_context().key_code


def key_is_pressed() -> bool:
    return require_context().key_is_pressed


def key_is_down(key_code: int) -> bool:
    return require_context().key_is_down(key_code)


def touches():
    return require_context().touches
