"""Color parsing and conversion."""

from __future__ import annotations

import colorsys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import cast

from gummysnake import constants as c
from gummysnake.exceptions import ArgumentValidationError

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
        """Return this Color converted to tuple.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[int, int, int, int]`.
        """
        return self.r, self.g, self.b, self.a

    def __iter__(self) -> Iterator[int]:
        """Iterate over this value's public components.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Iterator[int]`.
        """
        return iter(self.to_tuple())

    def with_red(self, red: Number) -> Color:
        """With red for this Color.
        
        Args:
            red: The red value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return Color(_to_u8(float(red)), self.g, self.b, self.a)

    def with_green(self, green: Number) -> Color:
        """With green for this Color.
        
        Args:
            green: The green value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return Color(self.r, _to_u8(float(green)), self.b, self.a)

    def with_blue(self, blue: Number) -> Color:
        """With blue for this Color.
        
        Args:
            blue: The blue value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return Color(self.r, self.g, _to_u8(float(blue)), self.a)

    def with_alpha(self, alpha: Number) -> Color:
        """With alpha for this Color.
        
        Args:
            alpha: The alpha value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Color`.
        """
        return Color(self.r, self.g, self.b, _to_u8(float(alpha)))

    def contrast_ratio(self, other: Color) -> float:
        """Contrast ratio for this Color.
        
        Args:
            other: The other value. Expected type: `Color`.
        
        Returns:
            The return value. Type: `float`.
        """
        first = _relative_luminance(self)
        second = _relative_luminance(other)
        lighter = max(first, second)
        darker = min(first, second)
        return (lighter + 0.05) / (darker + 0.05)

    def to_hex(self, *, include_alpha: bool = False) -> str:
        """Return this Color converted to hex.
        
        Args:
            include_alpha: The include alpha value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `str`.
        """
        channels = (self.r, self.g, self.b, self.a) if include_alpha else (self.r, self.g, self.b)
        return "#" + "".join(f"{channel:02x}" for channel in channels)

    def to_rgb_string(self) -> str:
        """Return this Color converted to rgb string.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        if self.a == 255:
            return f"rgb({self.r}, {self.g}, {self.b})"
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a / 255:g})"

    @classmethod
    def from_args(
        cls,
        args: Iterable[object],
        *,
        mode: c.ColorMode = c.RGB,
        ranges: tuple[Number, Number, Number, Number] = (255, 255, 255, 255),
    ) -> Color:
        """From args for this Color.
        
        Args:
            args: The positional arguments value. Expected type: `Iterable[object]`.
            mode: The mode value. Expected type: `c.ColorMode`. Defaults to `c.RGB`.
            ranges: The ranges value. Expected type: `tuple[Number, Number, Number, Number]`.
                Defaults to `(255, 255, 255, 255)`.
        
        Returns:
            The return value. Type: `Color`.
        """
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


def _relative_luminance(value: Color) -> float:
    def channel(component: int) -> float:
        normalized = component / 255.0
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(value.r) + 0.7152 * channel(value.g) + 0.0722 * channel(value.b)


def lerp_color(start: Color, stop: Color, amount: Number) -> Color:
    """Lerp color using the active color context.
    
    Args:
        start: The start value. Expected type: `Color`.
        stop: The stop value. Expected type: `Color`.
        amount: The amount value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    t = float(amount)
    return Color(
        _to_u8(start.r + (stop.r - start.r) * t),
        _to_u8(start.g + (stop.g - start.g) * t),
        _to_u8(start.b + (stop.b - start.b) * t),
        _to_u8(start.a + (stop.a - start.a) * t),
    )


def red(value: Color) -> int:
    """Return the red component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `int`.
    """
    return value.r


def green(value: Color) -> int:
    """Return the green component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `int`.
    """
    return value.g


def blue(value: Color) -> int:
    """Return the blue component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `int`.
    """
    return value.b


def alpha(value: Color) -> int:
    """Return the alpha component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `int`.
    """
    return value.a


def hue(value: Color) -> float:
    """Return the hue component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `float`.
    """
    h, _l, _s = colorsys.rgb_to_hls(value.r / 255.0, value.g / 255.0, value.b / 255.0)
    return h * 360.0


def saturation(value: Color) -> float:
    """Return the saturation component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `float`.
    """
    _h, s, _v = colorsys.rgb_to_hsv(value.r / 255.0, value.g / 255.0, value.b / 255.0)
    return s * 100.0


def brightness(value: Color) -> float:
    """Return the brightness component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `float`.
    """
    _h, _s, v = colorsys.rgb_to_hsv(value.r / 255.0, value.g / 255.0, value.b / 255.0)
    return v * 100.0


def lightness(value: Color) -> float:
    """Return the lightness component of a color.
    
    Args:
        value: The value value. Expected type: `Color`.
    
    Returns:
        The return value. Type: `float`.
    """
    _h, lightness_value, _s = colorsys.rgb_to_hls(
        value.r / 255.0,
        value.g / 255.0,
        value.b / 255.0,
    )
    return lightness_value * 100.0


def palette_lerp(palette: Iterable[Color], amount: Number) -> Color:
    """Interpolate across a palette and return the sampled color.
    
    Args:
        palette: The palette value. Expected type: `Iterable[Color]`.
        amount: The amount value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `Color`.
    """
    colors = tuple(palette)
    if not colors:
        raise ArgumentValidationError("palette_lerp() requires at least one color.")
    if len(colors) == 1:
        return colors[0]
    t = _clamp(float(amount), 0.0, 1.0) * (len(colors) - 1)
    index = min(len(colors) - 2, int(t))
    local_t = t - index
    return lerp_color(colors[index], colors[index + 1], local_t)


__all__ = [
    "Color",
    "lerp_color",
    "red",
    "green",
    "blue",
    "alpha",
    "hue",
    "saturation",
    "brightness",
    "lightness",
    "palette_lerp",
]
