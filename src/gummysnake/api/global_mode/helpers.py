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
    """Style color args.
    
    Args:
        value: The value value. Expected type: `ColorArgument`.
    
    Returns:
        The return value. Type: `tuple[Color | str | Number, ...]`.
    """
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return cast(tuple[Color | str | Number, ...], tuple(value))
    return cast(tuple[Color | str | Number, ...], (value,))


@overload
def xy(value: CoordinatePair, y: None = None) -> tuple[float, float]:
    """Overload signature for xy().
    
    Args:
        value: The value value. Expected type: `CoordinatePair`.
        y: The y value. Expected type: `None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `tuple[float, float]`.
    """
    ...


@overload
def xy(value: Number, y: Number) -> tuple[float, float]:
    """Overload signature for xy().
    
    Args:
        value: The value value. Expected type: `Number`.
        y: The y value. Expected type: `Number`.
    
    Returns:
        The return value. Type: `tuple[float, float]`.
    """
    ...


def xy(value: CoordinatePair | Number, y: Number | None = None) -> tuple[float, float]:
    """Xy.
    
    Args:
        value: The value value. Expected type: `CoordinatePair | Number`.
        y: The y value. Expected type: `Number | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `tuple[float, float]`.
    """
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
