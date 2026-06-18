"""Color parsing and conversion."""

from __future__ import annotations

import colorsys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from p5 import constants as c
from p5.exceptions import ArgumentValidationError

Number = int | float

_NAMED_COLORS: dict[str, tuple[int, int, int, int]] = {
    "black": (0, 0, 0, 255),
    "white": (255, 255, 255, 255),
    "red": (255, 0, 0, 255),
    "green": (0, 128, 0, 255),
    "blue": (0, 0, 255, 255),
    "yellow": (255, 255, 0, 255),
    "cyan": (0, 255, 255, 255),
    "magenta": (255, 0, 255, 255),
    "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255),
    "orange": (255, 165, 0, 255),
    "purple": (128, 0, 128, 255),
    "transparent": (0, 0, 0, 0),
}


def _clamp(value: float, low: float = 0.0, high: float = 255.0) -> float:
    return max(low, min(high, value))


def _to_u8(value: float) -> int:
    return int(round(_clamp(value)))


def _scale(value: Number, maximum: Number) -> float:
    if maximum == 0:
        raise ArgumentValidationError("Color mode ranges must be greater than zero.")
    return _clamp(float(value) / float(maximum), 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class Color:
    """RGBA color stored internally as 8-bit channels."""

    r: int
    g: int
    b: int
    a: int = 255

    def __post_init__(self) -> None:
        for channel_name in ("r", "g", "b", "a"):
            value = getattr(self, channel_name)
            if not 0 <= value <= 255:
                raise ArgumentValidationError(
                    f"Color channel {channel_name!r} must be between 0 and 255, got {value!r}."
                )

    def to_tuple(self) -> tuple[int, int, int, int]:
        return self.r, self.g, self.b, self.a

    def __iter__(self):
        return iter(self.to_tuple())

    def with_alpha(self, alpha: Number) -> Color:
        return Color(self.r, self.g, self.b, _to_u8(float(alpha)))

    @classmethod
    def from_args(
        cls,
        args: Iterable[object],
        *,
        mode: str = c.RGB,
        ranges: tuple[Number, Number, Number, Number] = (255, 255, 255, 255),
    ) -> Color:
        values = tuple(args)
        if len(values) == 1 and isinstance(values[0], Color):
            return values[0]
        if len(values) == 1 and isinstance(values[0], str):
            return cls(*_parse_color_string(values[0]))
        if not values:
            raise ArgumentValidationError("color() requires at least one argument.")
        if not all(isinstance(value, int | float) for value in values):
            raise ArgumentValidationError(
                "Color arguments must be numbers, Color objects, or strings."
            )
        numeric_values = cast(tuple[Number, ...], values)
        if len(numeric_values) == 1:
            gray = _to_u8(_scale(numeric_values[0], ranges[0]) * 255)
            return cls(gray, gray, gray, 255)
        if len(numeric_values) == 2:
            gray = _to_u8(_scale(numeric_values[0], ranges[0]) * 255)
            alpha = _to_u8(_scale(numeric_values[1], ranges[3]) * 255)
            return cls(gray, gray, gray, alpha)
        if len(numeric_values) not in (3, 4):
            raise ArgumentValidationError(
                "Color requires 1, 2, 3, or 4 numeric arguments; a Color; or a color string."
            )

        alpha = (
            _to_u8(_scale(numeric_values[3], ranges[3]) * 255) if len(numeric_values) == 4 else 255
        )
        first = _scale(numeric_values[0], ranges[0])
        second = _scale(numeric_values[1], ranges[1])
        third = _scale(numeric_values[2], ranges[2])

        if mode == c.RGB:
            return cls(_to_u8(first * 255), _to_u8(second * 255), _to_u8(third * 255), alpha)
        if mode == c.HSB:
            r, g, b = colorsys.hsv_to_rgb(first, second, third)
            return cls(_to_u8(r * 255), _to_u8(g * 255), _to_u8(b * 255), alpha)
        if mode == c.HSL:
            r, g, b = colorsys.hls_to_rgb(first, third, second)
            return cls(_to_u8(r * 255), _to_u8(g * 255), _to_u8(b * 255), alpha)
        raise ArgumentValidationError(f"Unsupported color mode {mode!r}.")


def _parse_color_string(value: str) -> tuple[int, int, int, int]:
    normalized = value.strip().lower()
    if normalized in _NAMED_COLORS:
        return _NAMED_COLORS[normalized]
    if normalized.startswith("#"):
        hex_value = normalized[1:]
        if len(hex_value) in {3, 4}:
            parts = [int(component * 2, 16) for component in hex_value]
        elif len(hex_value) in {6, 8}:
            parts = [int(hex_value[index : index + 2], 16) for index in range(0, len(hex_value), 2)]
        else:
            raise ArgumentValidationError(f"Unknown color string {value!r}.")
        if len(parts) == 3:
            parts.append(255)
        return cast(tuple[int, int, int, int], tuple(parts))
    raise ArgumentValidationError(f"Unknown color string {value!r}.")


def lerp_color(start: Color, stop: Color, amount: Number) -> Color:
    t = float(amount)
    return Color(
        _to_u8(start.r + (stop.r - start.r) * t),
        _to_u8(start.g + (stop.g - start.g) * t),
        _to_u8(start.b + (stop.b - start.b) * t),
        _to_u8(start.a + (stop.a - start.a) * t),
    )


def red(value: Color) -> int:
    return value.r


def green(value: Color) -> int:
    return value.g


def blue(value: Color) -> int:
    return value.b


def alpha(value: Color) -> int:
    return value.a
