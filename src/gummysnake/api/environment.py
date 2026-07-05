"""Global-mode window, display, focus, and cursor wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


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


def fullscreen(value: bool | None = None) -> bool:
    context = require_context()
    if value is not None:
        requested = bool(value)
        callback = getattr(context.backend, "set_fullscreen", None)
        if callable(callback):
            requested = bool(callback(requested))
        context._fullscreen = requested
    return bool(context._fullscreen)


def focused() -> bool:
    context = require_context()
    callback = getattr(context.backend, "focused", None)
    if callable(callback):
        context._focused = bool(callback())
    return bool(context._focused)


def cursor(kind: str | None = None) -> str | None:
    context = require_context()
    if kind is not None:
        context._cursor_kind = str(kind)
        context._cursor_visible = True
        callback = getattr(context.backend, "set_cursor", None)
        if callable(callback):
            callback(context._cursor_kind)
    return context._cursor_kind


def no_cursor() -> None:
    context = require_context()
    context._cursor_visible = False
    callback = getattr(context.backend, "set_cursor_visible", None)
    if callable(callback):
        callback(False)


__all__ = [
    "window_width",
    "window_height",
    "display_width",
    "display_height",
    "fullscreen",
    "focused",
    "cursor",
    "no_cursor",
]
