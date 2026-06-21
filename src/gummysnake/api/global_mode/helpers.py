"""Shared helpers for global-mode API wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

_UNSET = object()


def style_color_args(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return (value,)


def xy(value: object, y: float | None = None) -> tuple[float, float]:
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
