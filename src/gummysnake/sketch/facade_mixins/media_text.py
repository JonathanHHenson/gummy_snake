"""Text layout and accessibility forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.assets.text import Font
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin, SupportsText


class TextProperties(TypedDict, total=False):
    """Supported values accepted by :meth:`Sketch.text_properties`."""

    direction: str
    wrap: str
    weight: int


class SketchFacadeTextMixin(SketchFacadeBaseMixin):
    """Draw, measure, and describe text through an object-mode sketch."""

    __facade_doc_topic__ = "Draw, measure, or describe text using this sketch's active canvas."

    def text(self, value: SupportsText, x: float, y: float) -> None:
        self._ctx.text(value, x, y)

    def text_batch(self, items: Sequence[tuple[SupportsText, float, float]]) -> None:
        context = self._ctx
        context.renderer.text_batch(
            [(str(value), float(x), float(y)) for value, x, y in items],
            context.state.style,
            context.state.transform.matrix,
        )

    def text_size(self, size: float | None = None) -> float:
        return self._ctx.text_size(size)

    def text_font(self, font: Font | str | None = None) -> Font:
        return self._ctx.text_font(font)

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        return self._ctx.text_style(style)

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        self._ctx.text_align(horizontal, vertical)

    def text_leading(self, value: float | None = None) -> float:
        return self._ctx.text_leading(value)

    def text_width(self, value: SupportsText) -> float:
        return self._ctx.text_width(value)

    def text_widths(self, values: Sequence[SupportsText]) -> tuple[float, ...]:
        context = self._ctx
        style = context.state.style
        return tuple(context.renderer.text_width(str(value), style) for value in values)

    def text_ascent(self) -> float:
        return self._ctx.text_ascent()

    def text_descent(self) -> float:
        return self._ctx.text_descent()

    def font_ascent(self, font: Font | str | None = None) -> float:
        return self._ctx.font_ascent(font)

    def font_descent(self, font: Font | str | None = None) -> float:
        return self._ctx.font_descent(font)

    def font_width(self, value: SupportsText, font: Font | str | None = None) -> float:
        return self._ctx.font_width(value, font)

    def text_bounds(self, value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        return self._ctx.text_bounds(value, x, y)

    def font_bounds(
        self,
        value: SupportsText,
        x: float = 0.0,
        y: float = 0.0,
        font: Font | str | None = None,
    ) -> dict[str, float]:
        return self._ctx.font_bounds(value, x, y, font)

    def text_direction(self, value: str | None = None) -> str:
        return self._ctx.text_direction(value)

    def text_wrap(self, value: str | None = None) -> str:
        return self._ctx.text_wrap(value)

    def text_weight(self, value: int | None = None) -> int:
        return self._ctx.text_weight(value)

    @overload
    def text_property(self, name: Literal["direction"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["wrap"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["weight"], value: int | None = None) -> int: ...

    def text_property(self, name: str, value: str | int | None = None) -> str | int:
        return cast(str | int, self._ctx_call("text_property", name, value))

    def text_properties(
        self, **properties: Unpack[TextProperties]
    ) -> dict[str, str | int | float | c.TextStyle]:
        return cast(
            dict[str, str | int | float | c.TextStyle],
            self._ctx_call("text_properties", **properties),
        )

    def describe(self, description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
        return self._ctx.describe(description, label=label)

    def describe_element(self, name: SupportsText, description: SupportsText) -> dict[str, str]:
        return self._ctx.describe_element(name, description)

    def text_output(self) -> list[dict[str, str]]:
        return self._ctx.text_output()

    def grid_output(self) -> list[dict[str, str]]:
        return self._ctx.grid_output()
