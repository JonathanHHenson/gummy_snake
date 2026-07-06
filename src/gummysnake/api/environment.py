"""Global-mode window, display, focus, and cursor wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


def window_width() -> int:
    """Return the logical width of the sketch window.

    Returns:
        The canvas width in logical sketch pixels.
    """

    return require_context().width


def window_height() -> int:
    """Return the logical height of the sketch window.

    Returns:
        The canvas height in logical sketch pixels.
    """

    return require_context().height


def display_width() -> int:
    """Return the canvas width after display-density scaling.

    Returns:
        The physical backing width in pixels for the current display density.
    """

    context = require_context()
    return round(context.width * context.display_density())


def display_height() -> int:
    """Return the canvas height after display-density scaling.

    Returns:
        The physical backing height in pixels for the current display density.
    """

    context = require_context()
    return round(context.height * context.display_density())


def fullscreen(value: bool | None = None) -> bool:
    """Get or request fullscreen mode for the active sketch window.

    Args:
        value: Set to ``True`` to request fullscreen, ``False`` to leave
            fullscreen, or omit to only read the current state.

    Returns:
        ``True`` when Gummy Snake believes the sketch is fullscreen.
    """

    context = require_context()
    if value is not None:
        requested = bool(value)
        callback = getattr(context.backend, "set_fullscreen", None)
        if callable(callback):
            requested = bool(callback(requested))
        context._fullscreen = requested
    return bool(context._fullscreen)


def focused() -> bool:
    """Return whether the sketch window currently has input focus.

    Returns:
        ``True`` when keyboard and pointer input should go to the sketch window.
    """

    context = require_context()
    callback = getattr(context.backend, "focused", None)
    if callable(callback):
        context._focused = bool(callback())
    return bool(context._focused)


def cursor(kind: str | None = None) -> str | None:
    """Get or change the sketch window cursor.

    Args:
        kind: Optional cursor name to request from the active backend.

    Returns:
        The current cursor name, or ``None`` when no cursor has been selected.
    """

    context = require_context()
    if kind is not None:
        context._cursor_kind = str(kind)
        context._cursor_visible = True
        callback = getattr(context.backend, "set_cursor", None)
        if callable(callback):
            callback(context._cursor_kind)
    return context._cursor_kind


def no_cursor() -> None:
    """Hide the cursor over the active sketch window."""

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
