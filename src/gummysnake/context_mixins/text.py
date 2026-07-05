"""Text and accessibility methods for SketchContext."""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.assets.text import Font
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.exceptions import ArgumentValidationError


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class TextProperties(TypedDict, total=False):
    direction: str
    wrap: str
    weight: int


class TextContextMixin:
    renderer: Any
    state: Any
    _text_direction: str
    _text_wrap: str
    _text_weight: int
    _accessibility_descriptions: list[dict[str, str]]

    def text(self, value: SupportsText, x: float, y: float) -> None:
        self.renderer.text(
            str(value), float(x), float(y), self.state.style, self.state.transform.matrix
        )

    def text_size(self, size: float | None = None) -> float:
        if size is not None:
            if size <= 0:
                raise ArgumentValidationError("text_size() must be positive.")
            self.state.style.text_size = float(size)
            cast(SketchContextHost, self)._mark_style_changed()
        return self.state.style.text_size

    def text_font(self, font: Font | str | None = None) -> Font:
        if font is not None:
            if isinstance(font, str):
                font = Font(name=font)
            self.state.style.text_font = font
            cast(SketchContextHost, self)._mark_style_changed()
        return self.state.style.text_font

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        if style is not None:
            if style not in {c.NORMAL, c.ITALIC, c.BOLD, c.BOLDITALIC}:
                raise ArgumentValidationError(f"Unsupported text style {style!r}.")
            self.state.style.text_style = style
            cast(SketchContextHost, self)._mark_style_changed()
        return self.state.style.text_style

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        if horizontal not in {c.LEFT, c.CENTER, c.RIGHT}:
            raise ArgumentValidationError(f"Unsupported horizontal text alignment {horizontal!r}.")
        if vertical is not None and vertical not in {c.TOP, c.CENTER, c.BOTTOM, c.BASELINE}:
            raise ArgumentValidationError(f"Unsupported vertical text alignment {vertical!r}.")
        self.state.style.text_align_x = horizontal
        cast(SketchContextHost, self)._mark_style_changed()
        if vertical is not None:
            self.state.style.text_align_y = vertical
            cast(SketchContextHost, self)._mark_style_changed()

    def text_leading(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_leading() must be positive.")
            self.state.style.text_leading = float(value)
            cast(SketchContextHost, self)._mark_style_changed()
        return self.state.style.text_leading

    def text_width(self, value: SupportsText) -> float:
        return self.renderer.text_width(str(value), self.state.style)

    def text_ascent(self) -> float:
        return self.renderer.text_ascent(self.state.style)

    def text_descent(self) -> float:
        return self.renderer.text_descent(self.state.style)

    def font_ascent(self, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        value = self.text_ascent()
        self.state.style.text_font = previous
        cast(SketchContextHost, self)._mark_style_changed()
        return value

    def font_descent(self, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        value = self.text_descent()
        self.state.style.text_font = previous
        cast(SketchContextHost, self)._mark_style_changed()
        return value

    def font_width(self, value: SupportsText, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        width = self.text_width(value)
        self.state.style.text_font = previous
        cast(SketchContextHost, self)._mark_style_changed()
        return width

    def text_bounds(self, value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        width = self.text_width(value)
        ascent = self.text_ascent()
        descent = self.text_descent()
        return {"x": float(x), "y": float(y) - ascent, "width": width, "height": ascent + descent}

    def font_bounds(
        self,
        value: SupportsText,
        x: float = 0.0,
        y: float = 0.0,
        font: Font | str | None = None,
    ) -> dict[str, float]:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        bounds = self.text_bounds(value, x, y)
        self.state.style.text_font = previous
        cast(SketchContextHost, self)._mark_style_changed()
        return bounds

    def text_direction(self, value: str | None = None) -> str:
        if value is not None:
            if value not in {"ltr", "rtl"}:
                raise ArgumentValidationError("text_direction() supports 'ltr' and 'rtl'.")
            self._text_direction = value
        return self._text_direction

    def text_wrap(self, value: str | None = None) -> str:
        if value is not None:
            if value not in {"word", "char"}:
                raise ArgumentValidationError("text_wrap() supports 'word' and 'char'.")
            self._text_wrap = value
        return self._text_wrap

    def text_weight(self, value: int | None = None) -> int:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_weight() must be positive.")
            self._text_weight = int(value)
            if self._text_weight >= 600 and self.state.style.text_style == c.NORMAL:
                self.state.style.text_style = c.BOLD
                cast(SketchContextHost, self)._mark_style_changed()
        return self._text_weight

    @overload
    def text_property(self, name: Literal["direction"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["wrap"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["weight"], value: int | None = None) -> int: ...

    def text_property(self, name: str, value: str | int | None = None) -> str | int:
        if name == "direction":
            return self.text_direction(None if value is None else str(value))
        if name == "wrap":
            return self.text_wrap(None if value is None else str(value))
        if name == "weight":
            return self.text_weight(None if value is None else int(value))
        raise ArgumentValidationError("Unsupported text property.")

    def text_properties(
        self, **properties: Unpack[TextProperties]
    ) -> dict[str, str | int | float | c.TextStyle]:
        for name, value in properties.items():
            if name == "direction":
                self.text_property("direction", cast(str, value))
            elif name == "wrap":
                self.text_property("wrap", cast(str, value))
            elif name == "weight":
                self.text_property("weight", cast(int, value))
        return {
            "direction": self._text_direction,
            "wrap": self._text_wrap,
            "weight": self._text_weight,
            "size": self.state.style.text_size,
            "style": self.state.style.text_style,
            "leading": self.state.style.text_leading,
        }

    def describe(self, description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
        label_text = str(label).strip()
        description_text = str(description).strip()
        if not label_text:
            raise ArgumentValidationError("describe() label cannot be empty.")
        if not description_text:
            raise ArgumentValidationError("describe() description cannot be empty.")

        entry = {"label": label_text, "description": description_text}
        for index, existing in enumerate(self._accessibility_descriptions):
            if existing["label"] == label_text:
                self._accessibility_descriptions[index] = entry
                return entry
        self._accessibility_descriptions.append(entry)
        return entry

    def describe_element(self, name: SupportsText, description: SupportsText) -> dict[str, str]:
        return self.describe(description, label=str(name))

    def text_output(self) -> list[dict[str, str]]:
        return list(self._accessibility_descriptions)

    def grid_output(self) -> list[dict[str, str]]:
        return self.text_output()
