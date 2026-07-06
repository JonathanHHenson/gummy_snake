"""Private math helpers for the fast drawing facade."""

from __future__ import annotations

import math
from collections.abc import Sequence

from gummysnake.drawing.software3d.payloads import Matrix4Payload


def _mat4_multiply(left: Matrix4Payload, right: Matrix4Payload) -> Matrix4Payload:
    values = [0.0] * 16
    for column in range(4):
        for row in range(4):
            values[column * 4 + row] = sum(
                left[k * 4 + row] * right[column * 4 + k] for k in range(4)
            )
    return tuple(values)


def _mat4_is_translation(matrix: Matrix4Payload) -> bool:
    return (
        matrix[:12] == (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        and matrix[15] == 1.0
    )


def _mat4_translation_then_rotation(
    translation: Matrix4Payload, rotation: Matrix4Payload
) -> Matrix4Payload:
    return (
        rotation[0],
        rotation[1],
        rotation[2],
        0.0,
        rotation[4],
        rotation[5],
        rotation[6],
        0.0,
        rotation[8],
        rotation[9],
        rotation[10],
        0.0,
        translation[12],
        translation[13],
        translation[14],
        1.0,
    )


def _mat4_translation(x: float, y: float, z: float) -> Matrix4Payload:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        float(x),
        float(y),
        float(z),
        1.0,
    )


def _mat4_scale(x: float, y: float, z: float) -> Matrix4Payload:
    return (
        float(x),
        0.0,
        0.0,
        0.0,
        0.0,
        float(y),
        0.0,
        0.0,
        0.0,
        0.0,
        float(z),
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _mat4_axis_angle(angle: float, x: float, y: float, z: float) -> Matrix4Payload:
    axis_length = math.sqrt(x * x + y * y + z * z)
    if axis_length <= 1.0e-12:
        raise ValueError("rotate() axis must be non-zero.")
    x /= axis_length
    y /= axis_length
    z /= axis_length
    cosine = math.cos(angle)
    sine = math.sin(angle)
    one_minus_cosine = 1.0 - cosine
    return (
        cosine + x * x * one_minus_cosine,
        y * x * one_minus_cosine + z * sine,
        z * x * one_minus_cosine - y * sine,
        0.0,
        x * y * one_minus_cosine - z * sine,
        cosine + y * y * one_minus_cosine,
        z * y * one_minus_cosine + x * sine,
        0.0,
        x * z * one_minus_cosine + y * sine,
        y * z * one_minus_cosine - x * sine,
        cosine + z * z * one_minus_cosine,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _mat4_quaternion(w: float, x: float, y: float, z: float) -> Matrix4Payload:
    length = math.sqrt(w * w + x * x + y * y + z * z)
    if length <= 1.0e-12:
        raise ValueError("rotate_quaternion() requires a non-zero quaternion.")
    w /= length
    x /= length
    y /= length
    z /= length
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return (
        1.0 - 2.0 * (yy + zz),
        2.0 * (xy + wz),
        2.0 * (xz - wy),
        0.0,
        2.0 * (xy - wz),
        1.0 - 2.0 * (xx + zz),
        2.0 * (yz + wx),
        0.0,
        2.0 * (xz + wy),
        2.0 * (yz - wx),
        1.0 - 2.0 * (xx + yy),
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _sequence3(value: Sequence[float], *, name: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values.")
    return (float(value[0]), float(value[1]), float(value[2]))


def _sequence4(value: Sequence[float], *, name: str) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError(f"{name} must contain exactly four values.")
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))

