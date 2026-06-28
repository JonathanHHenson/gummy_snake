"""Active sketch context management for global mode."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from gummysnake.exceptions import ContextError

if TYPE_CHECKING:
    from gummysnake.context import SketchContext

_ACTIVE_CONTEXT: ContextVar[Any | None] = ContextVar("gummysnake_active_context", default=None)


def get_active_context() -> SketchContext | None:
    """Get active context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `SketchContext | None`.
    """
    return cast("SketchContext | None", _ACTIVE_CONTEXT.get())


def require_context() -> SketchContext:
    """Require context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `SketchContext`.
    """
    context = get_active_context()
    if context is None:
        raise ContextError(
            "This Gummy Snake API requires an active sketch. "
            "Call it from setup(), draw(), or run a Sketch."
        )
    return context


@contextmanager
def activate_context(context: Any) -> Generator[None]:
    """Activate context.
    
    Args:
        context: The context value. Expected type: `Any`.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield
    finally:
        _ACTIVE_CONTEXT.reset(token)
