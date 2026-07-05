"""Shared helpers for global-mode API wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto
from typing import Literal, Protocol, cast, overload

from gummysnake.core.color import Color

Number = int | float


class _Unset(Enum):
    TOKEN = auto()


class PointLike(Protocol):
    """Public PointLike value."""

    x: float
    y: float


_UNSET = _Unset.TOKEN

type ColorArgument = Color | str | Number | Sequence[Number]
type CoordinatePair = Sequence[Number] | PointLike
type ScaleArgument = Number | Sequence[Number]
type Unset = Literal[_Unset.TOKEN]


def style_color_args(value: ColorArgument) -> tuple[Color | str | Number, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return cast(tuple[Color | str | Number, ...], tuple(value))
    return cast(tuple[Color | str | Number, ...], (value,))


@overload
def xy(value: CoordinatePair, y: None = None) -> tuple[float, float]: ...


@overload
def xy(value: Number, y: Number) -> tuple[float, float]: ...


def xy(value: CoordinatePair | Number, y: Number | None = None) -> tuple[float, float]:
    if y is not None:
        return float(cast(float, value)), float(y)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) != 2:
            raise ValueError("Expected a 2-item coordinate sequence.")
        return float(value[0]), float(value[1])
    x = getattr(value, "x", None)
    point_y = getattr(value, "y", None)
    if x is not None and point_y is not None:
        return float(x), float(point_y)
    raise TypeError("Expected a vector-like object, 2-item sequence, or x/y pair.")
