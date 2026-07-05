"""Shared pieces for explicit sketch facade mixins."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from gummysnake.context import SketchContext
from gummysnake.core.color import Color

Number = int | float
ColorValue = Color | str


class SupportsText(Protocol):
    """Public SupportsText value."""

    def __str__(self) -> str: ...


class SketchFacadeBaseMixin:
    """Public SketchFacadeBaseMixin value."""

    context: SketchContext | None

    @property
    def _ctx(self) -> SketchContext:
        if self.context is None:
            raise RuntimeError("Sketch context is not available until run() starts.")
        return self.context

    def _ctx_call(self, name: str, *args: object, **kwargs: object) -> object:
        method = cast(Callable[..., object], getattr(self._ctx, name))
        return method(*args, **kwargs)
