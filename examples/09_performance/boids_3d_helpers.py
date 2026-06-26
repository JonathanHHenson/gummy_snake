from __future__ import annotations

import math


def length(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def limit_vector(
    x: float,
    y: float,
    z: float,
    maximum: float,
) -> tuple[float, float, float]:
    vector_length = length(x, y, z)
    if vector_length <= maximum or vector_length <= 1e-9:
        return (x, y, z)
    scale = maximum / vector_length
    return (x * scale, y * scale, z * scale)


def set_magnitude(
    x: float,
    y: float,
    z: float,
    magnitude: float,
) -> tuple[float, float, float]:
    vector_length = length(x, y, z)
    if vector_length <= 1e-9:
        return (magnitude, 0.0, 0.0)
    scale = magnitude / vector_length
    return (x * scale, y * scale, z * scale)


def cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    ax, ay, az = left
    bx, by, bz = right
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
