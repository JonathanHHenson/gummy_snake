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
    """Shared active-context access and documentation for object-mode forwards."""

    __facade_doc_topic__ = "Use this object-mode helper with the active sketch context."

    context: SketchContext | None

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Give each public forwarding override useful editor-help text.

        Facade methods intentionally remain small delegates so the canonical API
        owns validation and state changes.  The generated documentation keeps
        those explicit delegates discoverable without duplicating the canonical
        API reference on every forwarding implementation.
        """
        super().__init_subclass__(**kwargs)
        topic = cls.__dict__.get("__facade_doc_topic__", cls.__facade_doc_topic__)
        for name, member in cls.__dict__.items():
            if name.startswith("_"):
                continue
            function = member.fget if isinstance(member, property) else member
            if callable(function) and not function.__doc__:
                function.__doc__ = (
                    f"{name.replace('_', ' ').capitalize()}. {topic} "
                    "It preserves the matching global-mode behavior."
                )

    @property
    def _ctx(self) -> SketchContext:
        if self.context is None:
            raise RuntimeError("Sketch context is not available until run() starts.")
        return self.context

    def _ctx_call(self, name: str, *args: object, **kwargs: object) -> object:
        method = cast(Callable[..., object], getattr(self._ctx, name))
        return method(*args, **kwargs)
