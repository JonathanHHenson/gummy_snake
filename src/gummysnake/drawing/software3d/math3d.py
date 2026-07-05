"""Vector math for the software 3D path."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d import Vec3
from gummysnake.exceptions import ArgumentValidationError


def triangle_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b.x - a.x, b.y - a.y, b.z - a.z
    vx, vy, vz = c.x - a.x, c.y - a.y, c.z - a.z
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return Vec3(0.0, 0.0, 0.0)
    return Vec3(nx / length, ny / length, nz / length)


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
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def normalize(value: Vec3) -> Vec3:
    length = math.sqrt(dot(value, value))
    if length == 0:
        raise ArgumentValidationError("3D vectors must have non-zero length.")
    return Vec3(value.x / length, value.y / length, value.z / length)
