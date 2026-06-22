"""Active sketch context management for global mode."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from gummysnake.exceptions import ContextError

if TYPE_CHECKING:
    from gummysnake.context import SketchContext

_ACTIVE_CONTEXT: ContextVar[Any | None] = ContextVar(
    "gummysnake_active_context", default=None
)
_ACTIVE_CONTEXT_FAST: Any | None = None


def get_active_context() -> SketchContext | None:
    if _ACTIVE_CONTEXT_FAST is not None:
        return cast("SketchContext", _ACTIVE_CONTEXT_FAST)
    return cast("SketchContext | None", _ACTIVE_CONTEXT.get())


def require_context() -> SketchContext:
    context = get_active_context()
    if context is None:
        raise ContextError(
            "This Gummy Snake API requires an active sketch. "
            "Call it from setup(), draw(), or run a Sketch."
        )
    return context


@contextmanager
def activate_context(context: Any) -> Generator[None]:
    global _ACTIVE_CONTEXT_FAST
    previous = _ACTIVE_CONTEXT_FAST
    _ACTIVE_CONTEXT_FAST = context
    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield
    finally:
        _ACTIVE_CONTEXT_FAST = previous
        _ACTIVE_CONTEXT.reset(token)
