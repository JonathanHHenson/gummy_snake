"""Shared pieces for explicit sketch facade mixins."""

from __future__ import annotations

from typing import Protocol

from gummysnake.context import SketchContext
from gummysnake.core.color import Color

Number = int | float
ColorValue = Color | str


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class SketchFacadeBaseMixin:
    context: SketchContext | None

    @property
    def _ctx(self) -> SketchContext:
        if self.context is None:
            raise RuntimeError("Sketch context is not available until run() starts.")
        return self.context
