"""Global-mode text, font metric, and accessibility wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.text import Font


def _context_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class TextProperties(TypedDict, total=False):
    direction: str
    wrap: str
    weight: int


def text(value: SupportsText, x: float, y: float) -> None:
    context = require_context()
    context.renderer.text(
        str(value),
        float(x),
        float(y),
        context.state.style,
        context.state.transform.matrix,
    )


def text_batch(items: Sequence[tuple[SupportsText, float, float]]) -> None:
    context = require_context()
    context.renderer.text_batch(
        [(str(value), float(x), float(y)) for value, x, y in items],
        context.state.style,
        context.state.transform.matrix,
    )


def text_size(size: float | None = None) -> float:
    return cast(float, _context_call("text_size", size))


def text_font(font: Font | str | None = None) -> Font:
    return cast(Font, _context_call("text_font", font))


def text_style(style: c.TextStyle | None = None) -> c.TextStyle:
    return cast(c.TextStyle, _context_call("text_style", style))


def text_align(horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
    _context_call("text_align", horizontal, vertical)


def text_leading(value: float | None = None) -> float:
    return cast(float, _context_call("text_leading", value))


def text_width(value: SupportsText) -> float:
    context = require_context()
    return context.renderer.text_width(str(value), context.state.style)


def text_widths(values: Sequence[SupportsText]) -> tuple[float, ...]:
    context = require_context()
    style = context.state.style
    return tuple(context.renderer.text_width(str(value), style) for value in values)


def text_ascent() -> float:
    return cast(float, _context_call("text_ascent"))


def text_descent() -> float:
    return cast(float, _context_call("text_descent"))


def font_ascent(font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_ascent", font))


def font_descent(font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_descent", font))


def font_width(value: SupportsText, font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_width", value, font))


def font_bounds(
    value: SupportsText, x: float = 0.0, y: float = 0.0, font: Font | str | None = None
) -> dict[str, float]:
    return cast(dict[str, float], _context_call("font_bounds", value, x, y, font))


def text_bounds(value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return cast(dict[str, float], _context_call("text_bounds", value, x, y))


def text_direction(value: str | None = None) -> str:
    return cast(str, _context_call("text_direction", value))


def text_wrap(value: str | None = None) -> str:
    return cast(str, _context_call("text_wrap", value))


def text_weight(value: int | None = None) -> int:
    return cast(int, _context_call("text_weight", value))


@overload
def text_property(name: Literal["direction"], value: str | None = None) -> str: ...


@overload
def text_property(name: Literal["wrap"], value: str | None = None) -> str: ...


@overload
def text_property(name: Literal["weight"], value: int | None = None) -> int: ...


def text_property(name: str, value: str | int | None = None) -> str | int:
    return _context_call("text_property", name, value)


def text_properties(
    **properties: Unpack[TextProperties],
) -> dict[str, str | int | float | c.TextStyle]:
    return cast(
        dict[str, str | int | float | c.TextStyle], _context_call("text_properties", **properties)
    )


def describe(description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
    return cast(dict[str, str], _context_call("describe", description, label=label))


def describe_element(name: SupportsText, description: SupportsText) -> dict[str, str]:
    return cast(dict[str, str], _context_call("describe_element", name, description))


def text_output() -> list[dict[str, str]]:
    return cast(list[dict[str, str]], _context_call("text_output"))


def grid_output() -> list[dict[str, str]]:
    return cast(list[dict[str, str]], _context_call("grid_output"))


__all__ = [
    "text",
    "text_batch",
    "text_size",
    "text_font",
    "text_style",
    "text_align",
    "text_leading",
    "text_width",
    "text_widths",
    "text_ascent",
    "text_descent",
    "font_ascent",
    "font_descent",
    "font_width",
    "font_bounds",
    "text_bounds",
    "text_direction",
    "text_wrap",
    "text_weight",
    "text_property",
    "text_properties",
    "describe",
    "describe_element",
    "text_output",
    "grid_output",
]
