"""Shared helpers for simple filled-primitive renderer fast paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.context import SketchContext

PRIMITIVE_RECT = 1
PRIMITIVE_TRIANGLE = 2
PRIMITIVE_ELLIPSE = 3


def queue_fill_primitive(context: SketchContext, kind: int, coords: tuple[float, ...]) -> bool:
    """Try to enqueue a simple filled shape through the renderer fast path."""

    queue = getattr(context.renderer, "queue_fill_primitive_fast_path", None)
    if not callable(queue):
        return False
    return bool(queue(kind, coords, context.state.style, context.state.transform.matrix))
