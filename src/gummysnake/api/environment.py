"""Global-mode window, display, focus, and cursor wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


def window_width() -> int:
    """Window width using the active environment context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    return require_context().width


def window_height() -> int:
    """Window height using the active environment context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    return require_context().height


def display_width() -> int:
    """Display width using the active environment context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    context = require_context()
    return round(context.width * context.display_density())


def display_height() -> int:
    """Display height using the active environment context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    context = require_context()
    return round(context.height * context.display_density())


def fullscreen(value: bool | None = None) -> bool:
    """Get or set fullscreen intent for the active sketch.
    
    Args:
        value: The value value. Expected type: `bool | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `bool`.
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
    """Return whether the sketch is focused.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """

    context = require_context()
    callback = getattr(context.backend, "focused", None)
    if callable(callback):
        context._focused = bool(callback())
    return bool(context._focused)


def cursor(kind: str | None = None) -> str | None:
    """Get or set the active cursor kind for the current sketch.
    
    Args:
        kind: The kind value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `str | None`.
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
    """Hide the cursor for the active sketch when the backend supports it.
    
    Args:
        None.
    
    Returns:
        None.
    """

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
