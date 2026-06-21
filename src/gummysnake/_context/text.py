# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Text and accessibility methods for SketchContext."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.assets.text import Font
from gummysnake.exceptions import ArgumentValidationError


class TextContextMixin:
    renderer: Any
    state: Any
    _text_direction: str
    _text_wrap: str
    _text_weight: int
    _accessibility_descriptions: list[dict[str, str]]

    def text(self, value: object, x: float, y: float) -> None:
        self.renderer.text(
            str(value), float(x), float(y), self.state.style, self.state.transform.matrix
        )

    def text_size(self, size: float | None = None) -> float:
        if size is not None:
            if size <= 0:
                raise ArgumentValidationError("text_size() must be positive.")
            self.state.style.text_size = float(size)
            self._mark_style_changed()
        return self.state.style.text_size

    def text_font(self, font: Font | str | None = None) -> Font:
        if font is not None:
            if isinstance(font, str):
                font = Font(name=font)
            self.state.style.text_font = font
            self._mark_style_changed()
        return self.state.style.text_font

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        if style is not None:
            if style not in {c.NORMAL, c.ITALIC, c.BOLD, c.BOLDITALIC}:
                raise ArgumentValidationError(f"Unsupported text style {style!r}.")
            self.state.style.text_style = style
            self._mark_style_changed()
        return self.state.style.text_style

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        if horizontal not in {c.LEFT, c.CENTER, c.RIGHT}:
            raise ArgumentValidationError(f"Unsupported horizontal text alignment {horizontal!r}.")
        if vertical is not None and vertical not in {c.TOP, c.CENTER, c.BOTTOM, c.BASELINE}:
            raise ArgumentValidationError(f"Unsupported vertical text alignment {vertical!r}.")
        self.state.style.text_align_x = horizontal
        self._mark_style_changed()
        if vertical is not None:
            self.state.style.text_align_y = vertical
            self._mark_style_changed()

    def text_leading(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_leading() must be positive.")
            self.state.style.text_leading = float(value)
            self._mark_style_changed()
        return self.state.style.text_leading

    def text_width(self, value: object) -> float:
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
        self._mark_style_changed()
        return value

    def font_descent(self, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        value = self.text_descent()
        self.state.style.text_font = previous
        self._mark_style_changed()
        return value

    def font_width(self, value: object, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        width = self.text_width(value)
        self.state.style.text_font = previous
        self._mark_style_changed()
        return width

    def text_bounds(self, value: object, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        width = self.text_width(value)
        ascent = self.text_ascent()
        descent = self.text_descent()
        return {"x": float(x), "y": float(y) - ascent, "width": width, "height": ascent + descent}

    def font_bounds(
        self, value: object, x: float = 0.0, y: float = 0.0, font: Font | str | None = None
    ) -> dict[str, float]:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        bounds = self.text_bounds(value, x, y)
        self.state.style.text_font = previous
        self._mark_style_changed()
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
                self._mark_style_changed()
        return self._text_weight

    def text_property(self, name: str, value: object | None = None) -> object:
        if name == "direction":
            return self.text_direction(None if value is None else str(value))
        if name == "wrap":
            return self.text_wrap(None if value is None else str(value))
        if name == "weight":
            return self.text_weight(None if value is None else int(cast(Any, value)))
        raise ArgumentValidationError("Unsupported text property.")

    def text_properties(self, **properties: object) -> dict[str, object]:
        for name, value in properties.items():
            self.text_property(name, value)
        return {
            "direction": self._text_direction,
            "wrap": self._text_wrap,
            "weight": self._text_weight,
            "size": self.state.style.text_size,
            "style": self.state.style.text_style,
            "leading": self.state.style.text_leading,
        }

    def describe(self, description: object, *, label: str = "canvas") -> dict[str, str]:
        entry = {"label": str(label), "description": str(description)}
        self._accessibility_descriptions.append(entry)
        return entry

    def describe_element(self, name: object, description: object) -> dict[str, str]:
        return self.describe(description, label=str(name))

    def text_output(self) -> list[dict[str, str]]:
        return list(self._accessibility_descriptions)

    def grid_output(self) -> list[dict[str, str]]:
        return self.text_output()
