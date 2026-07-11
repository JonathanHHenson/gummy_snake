"""Vector math for the software 3D path."""

from __future__ import annotations

from gummysnake.drawing.renderer3d import Vec3
from gummysnake.drawing.renderer3d._math import (
    add as _shared_add,
)
from gummysnake.drawing.renderer3d._math import (
    cross as _shared_cross,
)
from gummysnake.drawing.renderer3d._math import (
    dot as _shared_dot,
)
from gummysnake.drawing.renderer3d._math import (
    normalized_or_none,
)
from gummysnake.drawing.renderer3d._math import (
    subtract as _shared_subtract,
)
from gummysnake.exceptions import ArgumentValidationError


def triangle_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    normalized = normalized_or_none(cross(sub(b, a), sub(c, a)))
    return Vec3(0.0, 0.0, 0.0) if normalized is None else normalized


def face_center(points: list[Vec3]) -> Vec3:
    scale = 1.0 / len(points)
    return Vec3(
        sum(point.x for point in points) * scale,
        sum(point.y for point in points) * scale,
        sum(point.z for point in points) * scale,
    )


def face_normal(points: list[Vec3]) -> Vec3 | None:
    if len(points) < 3:
        return None
    normal = cross(sub(points[1], points[0]), sub(points[2], points[0]))
    if dot(normal, normal) == 0:
        return None
    return normal


def sub(a: Vec3, b: Vec3) -> Vec3:
    return _shared_subtract(a, b)


def add(a: Vec3, b: Vec3) -> Vec3:
    return _shared_add(a, b)


def dot(a: Vec3, b: Vec3) -> float:
    return _shared_dot(a, b)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return _shared_cross(a, b)


def normalize(value: Vec3) -> Vec3:
    normalized = normalized_or_none(value)
    if normalized is None:
        raise ArgumentValidationError("3D vectors must have non-zero length.")
    return normalized
