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


__all__ = [
    "window_width",
    "window_height",
    "display_width",
    "display_height",
    "focused",
    "cursor",
    "no_cursor",
]
