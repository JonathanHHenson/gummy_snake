"""Global-mode text, font metric, and accessibility wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.text import Font


class SupportsText(Protocol):
    """A value that can be shown as text by calling ``str(value)``."""

    def __str__(self) -> str: ...


class TextProperties(TypedDict, total=False):
    """Optional text layout properties accepted by ``text_properties()``."""

    direction: str
    wrap: str
    weight: int


def text(value: SupportsText, x: float, y: float) -> None:
    """Draw text at a position in the current sketch.

    Args:
        value: Text-like value to draw. It is converted with ``str()``.
        x: Horizontal coordinate for the text anchor.
        y: Vertical coordinate for the text anchor.
    """

    context = require_context()
    context.renderer.text(
        str(value),
        float(x),
        float(y),
        context.state.style,
        context.state.transform.matrix,
    )


def text_batch(items: Sequence[tuple[SupportsText, float, float]]) -> None:
    """Draw many text labels with the current text style and transform.

    Args:
        items: Sequence of ``(value, x, y)`` triples to draw.
    """

    context = require_context()
    context.renderer.text_batch(
        [(str(value), float(x), float(y)) for value, x, y in items],
        context.state.style,
        context.state.transform.matrix,
    )


def text_size(size: float | None = None) -> float:
    """Set or read the current text size.

    Args:
        size: New text size in logical pixels. Omit to leave it unchanged.

    Returns:
        The current text size.
    """

    return cast(float, _context_call("text_size", size))


def text_font(font: Font | str | None = None) -> Font:
    """Set or read the current font.

    Args:
        font: ``Font`` object or font name. Omit to leave the font unchanged.

    Returns:
        The current ``Font``.
    """

    return cast(Font, _context_call("text_font", font))


def text_style(style: c.TextStyle | None = None) -> c.TextStyle:
    """Set or read whether text is normal, italic, bold, or bold italic.

    Args:
        style: Text style such as ``NORMAL``, ``ITALIC``, ``BOLD``, or
            ``BOLDITALIC``. Omit to leave it unchanged.

    Returns:
        The current text style.
    """

    return cast(c.TextStyle, _context_call("text_style", style))


def text_align(horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
    """Set horizontal and optional vertical text alignment.

    Args:
        horizontal: Horizontal alignment such as ``LEFT``, ``CENTER``, or ``RIGHT``.
        vertical: Optional vertical alignment such as ``TOP``, ``CENTER``,
            ``BOTTOM``, or ``BASELINE``.
    """

    _context_call("text_align", horizontal, vertical)


def text_leading(value: float | None = None) -> float:
    """Set or read the line spacing used for multiline text.

    Args:
        value: New line spacing in logical pixels. Omit to leave it unchanged.

    Returns:
        The current text leading value.
    """

    return cast(float, _context_call("text_leading", value))


def text_width(value: SupportsText) -> float:
    """Measure how wide text would be with the current text style.

    Args:
        value: Text-like value to measure. It is converted with ``str()``.

    Returns:
        The measured width in logical pixels.
    """

    context = require_context()
    return context.renderer.text_width(str(value), context.state.style)


def text_widths(values: Sequence[SupportsText]) -> tuple[float, ...]:
    """Measure several text values with the current text style.

    Args:
        values: Text-like values to measure.

    Returns:
        Widths in logical pixels, in the same order as ``values``.
    """

    context = require_context()
    style = context.state.style
    return tuple(context.renderer.text_width(str(value), style) for value in values)


def text_ascent() -> float:
    """Measure how far the current font rises above the baseline.

    Returns:
        The current text ascent in logical pixels.
    """

    return cast(float, _context_call("text_ascent"))


def text_descent() -> float:
    """Measure how far the current font extends below the baseline.

    Returns:
        The current text descent in logical pixels.
    """

    return cast(float, _context_call("text_descent"))


def font_ascent(font: Font | str | None = None) -> float:
    """Measure ascent for a font without keeping it as the current font.

    Args:
        font: ``Font`` object or font name to measure. Omit to use the current font.

    Returns:
        The font ascent in logical pixels.
    """

    return cast(float, _context_call("font_ascent", font))


def font_descent(font: Font | str | None = None) -> float:
    """Measure descent for a font without keeping it as the current font.

    Args:
        font: ``Font`` object or font name to measure. Omit to use the current font.

    Returns:
        The font descent in logical pixels.
    """

    return cast(float, _context_call("font_descent", font))


def font_width(value: SupportsText, font: Font | str | None = None) -> float:
    """Measure text width using a font without keeping it as the current font.

    Args:
        value: Text-like value to measure. It is converted with ``str()``.
        font: ``Font`` object or font name to measure. Omit to use the current font.

    Returns:
        The measured width in logical pixels.
    """

    return cast(float, _context_call("font_width", value, font))


def font_bounds(
    value: SupportsText, x: float = 0.0, y: float = 0.0, font: Font | str | None = None
) -> dict[str, float]:
    """Measure a text bounding box using a font.

    Args:
        value: Text-like value to measure. It is converted with ``str()``.
        x: Horizontal coordinate for the text anchor.
        y: Vertical coordinate for the text anchor.
        font: ``Font`` object or font name to measure. Omit to use the current font.

    Returns:
        A dictionary with ``x``, ``y``, ``width``, and ``height`` values.
    """

    return cast(dict[str, float], _context_call("font_bounds", value, x, y, font))


def text_bounds(value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    """Measure a text bounding box with the current text style.

    Args:
        value: Text-like value to measure. It is converted with ``str()``.
        x: Horizontal coordinate for the text anchor.
        y: Vertical coordinate for the text anchor.

    Returns:
        A dictionary with ``x``, ``y``, ``width``, and ``height`` values.
    """

    return cast(dict[str, float], _context_call("text_bounds", value, x, y))


def text_direction(value: str | None = None) -> str:
    """Set or read the current text direction.

    Args:
        value: ``"ltr"`` or ``"rtl"``. Omit to leave the direction unchanged.

    Returns:
        The current text direction.
    """

    return cast(str, _context_call("text_direction", value))


def text_wrap(value: str | None = None) -> str:
    """Set or read how long text is wrapped.

    Args:
        value: ``"word"`` to wrap at words or ``"char"`` to wrap at characters.
            Omit to leave wrapping unchanged.

    Returns:
        The current text wrap mode.
    """

    return cast(str, _context_call("text_wrap", value))


def text_weight(value: int | None = None) -> int:
    """Set or read the current text weight.

    Args:
        value: Positive font weight, such as ``400`` for regular or ``700`` for bold.
            Omit to leave the weight unchanged.

    Returns:
        The current text weight.
    """

    return cast(int, _context_call("text_weight", value))


@overload
def text_property(name: Literal["direction"], value: str | None = None) -> str:
    """Set or read the text direction property."""

    ...


@overload
def text_property(name: Literal["wrap"], value: str | None = None) -> str:
    """Set or read the text wrap property."""

    ...


@overload
def text_property(name: Literal["weight"], value: int | None = None) -> int:
    """Set or read the text weight property."""

    ...


def text_property(name: str, value: str | int | None = None) -> str | int:
    """Set or read one text property by name.

    Args:
        name: Property name: ``"direction"``, ``"wrap"``, or ``"weight"``.
        value: New property value. Omit to read the current value.

    Returns:
        The current value for the requested property.
    """

    return cast(str | int, _context_call("text_property", name, value))


def text_properties(
    **properties: Unpack[TextProperties],
) -> dict[str, str | int | float | c.TextStyle]:
    """Set several text properties and return the current text settings.

    Args:
        **properties: Optional settings such as ``direction="rtl"``,
            ``wrap="char"``, or ``weight=700``.

    Returns:
        Current text direction, wrap, weight, size, style, and leading values.
    """

    return cast(
        dict[str, str | int | float | c.TextStyle], _context_call("text_properties", **properties)
    )


def describe(description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
    """Record an accessibility description for the canvas or a named area.

    Args:
        description: Human-readable description to expose.
        label: Label that identifies what the description belongs to.

    Returns:
        The stored entry with ``"label"`` and ``"description"`` keys.
    """

    return cast(dict[str, str], _context_call("describe", description, label=label))


def describe_element(name: SupportsText, description: SupportsText) -> dict[str, str]:
    """Record an accessibility description for a named sketch element.

    Args:
        name: Element label.
        description: Human-readable description to expose.

    Returns:
        The stored entry with ``"label"`` and ``"description"`` keys.
    """

    return cast(dict[str, str], _context_call("describe_element", name, description))


def text_output() -> list[dict[str, str]]:
    """Return recorded accessibility text descriptions.

    Returns:
        A list of description dictionaries.
    """

    return cast(list[dict[str, str]], _context_call("text_output"))


def grid_output() -> list[dict[str, str]]:
    """Return recorded accessibility descriptions for grid-style output.

    Returns:
        A list of description dictionaries.
    """

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
