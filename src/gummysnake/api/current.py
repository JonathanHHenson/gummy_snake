"""Active sketch context management for global mode."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from gummysnake.exceptions import ContextError

if TYPE_CHECKING:
    from gummysnake.context import SketchContext

_ACTIVE_CONTEXT: ContextVar[SketchContext | None] = ContextVar(
    "gummysnake_active_context", default=None
)


def get_active_context() -> SketchContext | None:
    """Return the sketch context active in the current task.

    Returns:
        The current ``SketchContext`` when code is running inside a sketch callback,
        otherwise ``None``.
    """

    return _ACTIVE_CONTEXT.get()


def require_context() -> SketchContext:
    """Return the active sketch context or raise a helpful error.

    Returns:
        The current ``SketchContext`` for global-mode drawing and state APIs.
    """

    context = get_active_context()
    if context is None:
        raise ContextError(
            "This Gummy Snake API requires an active sketch. "
            "Call it from setup(), draw(), or run a Sketch."
        )
    return context


@contextmanager
def activate_context(context: SketchContext) -> Generator[None]:
    """Temporarily make a sketch context active for global-mode APIs.

    Args:
        context: Sketch context to expose through functions such as ``gs.line()``
            and ``gs.width()`` while the context manager is active.
    """

    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield
    finally:
        _ACTIVE_CONTEXT.reset(token)
