"""Private, exception-neutral vector operations shared by Python 3D helpers."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d.types import Vec3


def add(a: Vec3, b: Vec3) -> Vec3:
    """Return the component-wise vector sum."""
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def subtract(a: Vec3, b: Vec3) -> Vec3:
    """Return the component-wise vector difference."""
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def dot(a: Vec3, b: Vec3) -> float:
    """Return the vector dot product."""
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: Vec3, b: Vec3) -> Vec3:
    """Return the vector cross product."""
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def length(value: Vec3) -> float:
    """Return the Euclidean vector length."""
    return math.sqrt(dot(value, value))


def normalized_or_none(value: Vec3) -> Vec3 | None:
    """Normalize ``value`` or return ``None`` for a zero-length vector.

    Callers own their public exception or default-vector contract.
    """
    value_length = length(value)
    if value_length == 0.0:
        return None
    return Vec3(value.x / value_length, value.y / value_length, value.z / value_length)
