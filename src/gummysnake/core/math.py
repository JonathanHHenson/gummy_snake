"""Gummy Snake-style numeric helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence

from gummysnake import constants as c

Number = int | float

_angle_mode = c.RADIANS


def set_angle_mode(mode: c.AngleMode) -> None:
    global _angle_mode
    if mode not in {c.RADIANS, c.DEGREES}:
        msg = f"Unsupported angle mode {mode!r}."
        raise ValueError(msg)
    _angle_mode = mode


def get_angle_mode() -> c.AngleMode:
    return _angle_mode


def _to_radians(value: Number) -> float:
    return math.radians(float(value)) if _angle_mode == c.DEGREES else float(value)


def _from_radians(value: float) -> float:
    return math.degrees(value) if _angle_mode == c.DEGREES else value


def map_value(
    value: Number,
    start1: Number,
    stop1: Number,
    start2: Number,
    stop2: Number,
    within_bounds: bool = False,
) -> float:
    if stop1 == start1:
        msg = "map_value() input range cannot be zero."
        raise ValueError(msg)
    result = float(start2) + (float(stop2) - float(start2)) * (
        (float(value) - float(start1)) / (float(stop1) - float(start1))
    )
    if within_bounds:
        lower = min(float(start2), float(stop2))
        upper = max(float(start2), float(stop2))
        return constrain(result, lower, upper)
    return result


def constrain(value: Number, low: Number, high: Number) -> float:
    return max(float(low), min(float(high), float(value)))


def norm(value: Number, start: Number, stop: Number) -> float:
    return map_value(value, start, stop, 0, 1)


def lerp(start: Number, stop: Number, amount: Number) -> float:
    return float(start) + (float(stop) - float(start)) * float(amount)


def dist(*values: Number) -> float:
    if len(values) == 4:
        x1, y1, x2, y2 = values
        return math.hypot(float(x2) - float(x1), float(y2) - float(y1))
    if len(values) == 6:
        x1, y1, z1, x2, y2, z2 = values
        return math.sqrt(
            (float(x2) - float(x1)) ** 2
            + (float(y2) - float(y1)) ** 2
            + (float(z2) - float(z1)) ** 2
        )
    msg = "dist() requires either 4 values for 2D or 6 values for 3D distance."
    raise TypeError(msg)


def mag(*values: Number) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in values))


def radians(degrees: Number) -> float:
    return math.radians(float(degrees))


def degrees(radians_value: Number) -> float:
    return math.degrees(float(radians_value))


def sin(angle: Number) -> float:
    return math.sin(_to_radians(angle))


def cos(angle: Number) -> float:
    return math.cos(_to_radians(angle))


def tan(angle: Number) -> float:
    return math.tan(_to_radians(angle))


def asin(value: Number) -> float:
    return _from_radians(math.asin(float(value)))


def acos(value: Number) -> float:
    return _from_radians(math.acos(float(value)))


def atan(value: Number) -> float:
    return _from_radians(math.atan(float(value)))


def atan2(y: Number, x: Number) -> float:
    return _from_radians(math.atan2(float(y), float(x)))


def sq(value: Number) -> float:
    return float(value) * float(value)


def fract(value: Number) -> float:
    return float(value) - math.floor(float(value))


def min_value(values: Sequence[Number] | Number, *rest: Number) -> float:
    items = (values, *rest) if isinstance(values, int | float) else tuple(values)
    return float(min(items))


def max_value(values: Sequence[Number] | Number, *rest: Number) -> float:
    items = (values, *rest) if isinstance(values, int | float) else tuple(values)
    return float(max(items))


__all__ = [
    "map_value",
    "constrain",
    "norm",
    "lerp",
    "dist",
    "mag",
    "radians",
    "degrees",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "atan2",
    "sq",
    "fract",
    "min_value",
    "max_value",
    "set_angle_mode",
    "get_angle_mode",
]
