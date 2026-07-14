"""Private math helpers for the fast drawing facade."""

from __future__ import annotations

import math
from collections.abc import Sequence

from gummysnake.drawing.software3d.payloads import Matrix4Payload


def _mat4_multiply(left: Matrix4Payload, right: Matrix4Payload) -> Matrix4Payload:
    """Multiply two column-major 4x4 matrices without Python loop overhead."""

    l0, l1, l2, l3 = left[0], left[1], left[2], left[3]
    l4, l5, l6, l7 = left[4], left[5], left[6], left[7]
    l8, l9, l10, l11 = left[8], left[9], left[10], left[11]
    l12, l13, l14, l15 = left[12], left[13], left[14], left[15]
    r0, r1, r2, r3 = right[0], right[1], right[2], right[3]
    r4, r5, r6, r7 = right[4], right[5], right[6], right[7]
    r8, r9, r10, r11 = right[8], right[9], right[10], right[11]
    r12, r13, r14, r15 = right[12], right[13], right[14], right[15]
    return (
        l0 * r0 + l4 * r1 + l8 * r2 + l12 * r3,
        l1 * r0 + l5 * r1 + l9 * r2 + l13 * r3,
        l2 * r0 + l6 * r1 + l10 * r2 + l14 * r3,
        l3 * r0 + l7 * r1 + l11 * r2 + l15 * r3,
        l0 * r4 + l4 * r5 + l8 * r6 + l12 * r7,
        l1 * r4 + l5 * r5 + l9 * r6 + l13 * r7,
        l2 * r4 + l6 * r5 + l10 * r6 + l14 * r7,
        l3 * r4 + l7 * r5 + l11 * r6 + l15 * r7,
        l0 * r8 + l4 * r9 + l8 * r10 + l12 * r11,
        l1 * r8 + l5 * r9 + l9 * r10 + l13 * r11,
        l2 * r8 + l6 * r9 + l10 * r10 + l14 * r11,
        l3 * r8 + l7 * r9 + l11 * r10 + l15 * r11,
        l0 * r12 + l4 * r13 + l8 * r14 + l12 * r15,
        l1 * r12 + l5 * r13 + l9 * r14 + l13 * r15,
        l2 * r12 + l6 * r13 + l10 * r14 + l14 * r15,
        l3 * r12 + l7 * r13 + l11 * r14 + l15 * r15,
    )


def _mat4_post_translate(matrix: Matrix4Payload, x: float, y: float, z: float) -> Matrix4Payload:
    """Return ``matrix * translation(x, y, z)`` for column-major matrices."""

    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    m4, m5, m6, m7 = matrix[4], matrix[5], matrix[6], matrix[7]
    m8, m9, m10, m11 = matrix[8], matrix[9], matrix[10], matrix[11]
    m12, m13, m14, m15 = matrix[12], matrix[13], matrix[14], matrix[15]
    return (
        m0,
        m1,
        m2,
        m3,
        m4,
        m5,
        m6,
        m7,
        m8,
        m9,
        m10,
        m11,
        m0 * x + m4 * y + m8 * z + m12,
        m1 * x + m5 * y + m9 * z + m13,
        m2 * x + m6 * y + m10 * z + m14,
        m3 * x + m7 * y + m11 * z + m15,
    )


def _mat4_post_scale(matrix: Matrix4Payload, x: float, y: float, z: float) -> Matrix4Payload:
    """Return ``matrix * scale(x, y, z)`` for column-major matrices."""

    return (
        matrix[0] * x,
        matrix[1] * x,
        matrix[2] * x,
        matrix[3] * x,
        matrix[4] * y,
        matrix[5] * y,
        matrix[6] * y,
        matrix[7] * y,
        matrix[8] * z,
        matrix[9] * z,
        matrix[10] * z,
        matrix[11] * z,
        matrix[12],
        matrix[13],
        matrix[14],
        matrix[15],
    )


def _mat4_post_rotate_x(matrix: Matrix4Payload, angle: float) -> Matrix4Payload:
    """Return ``matrix * rotate_x(angle)`` for column-major matrices."""

    cosine = math.cos(angle)
    sine = math.sin(angle)
    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    m4, m5, m6, m7 = matrix[4], matrix[5], matrix[6], matrix[7]
    m8, m9, m10, m11 = matrix[8], matrix[9], matrix[10], matrix[11]
    return (
        m0,
        m1,
        m2,
        m3,
        m4 * cosine + m8 * sine,
        m5 * cosine + m9 * sine,
        m6 * cosine + m10 * sine,
        m7 * cosine + m11 * sine,
        m8 * cosine - m4 * sine,
        m9 * cosine - m5 * sine,
        m10 * cosine - m6 * sine,
        m11 * cosine - m7 * sine,
        matrix[12],
        matrix[13],
        matrix[14],
        matrix[15],
    )


def _mat4_post_rotate_y(matrix: Matrix4Payload, angle: float) -> Matrix4Payload:
    """Return ``matrix * rotate_y(angle)`` for column-major matrices."""

    cosine = math.cos(angle)
    sine = math.sin(angle)
    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    m8, m9, m10, m11 = matrix[8], matrix[9], matrix[10], matrix[11]
    return (
        m0 * cosine - m8 * sine,
        m1 * cosine - m9 * sine,
        m2 * cosine - m10 * sine,
        m3 * cosine - m11 * sine,
        matrix[4],
        matrix[5],
        matrix[6],
        matrix[7],
        m0 * sine + m8 * cosine,
        m1 * sine + m9 * cosine,
        m2 * sine + m10 * cosine,
        m3 * sine + m11 * cosine,
        matrix[12],
        matrix[13],
        matrix[14],
        matrix[15],
    )


def _mat4_post_rotate_z(matrix: Matrix4Payload, angle: float) -> Matrix4Payload:
    """Return ``matrix * rotate_z(angle)`` for column-major matrices."""

    cosine = math.cos(angle)
    sine = math.sin(angle)
    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    m4, m5, m6, m7 = matrix[4], matrix[5], matrix[6], matrix[7]
    return (
        m0 * cosine + m4 * sine,
        m1 * cosine + m5 * sine,
        m2 * cosine + m6 * sine,
        m3 * cosine + m7 * sine,
        m4 * cosine - m0 * sine,
        m5 * cosine - m1 * sine,
        m6 * cosine - m2 * sine,
        m7 * cosine - m3 * sine,
        matrix[8],
        matrix[9],
        matrix[10],
        matrix[11],
        matrix[12],
        matrix[13],
        matrix[14],
        matrix[15],
    )


def _mat4_translation_quaternion(
    tx: float,
    ty: float,
    tz: float,
    w: float,
    x: float,
    y: float,
    z: float,
) -> Matrix4Payload:
    """Build a translation-plus-normalized-quaternion matrix in column-major order."""

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
        tx,
        ty,
        tz,
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
    inverse_length = 1.0 / length
    return _mat4_translation_quaternion(
        0.0,
        0.0,
        0.0,
        w * inverse_length,
        x * inverse_length,
        y * inverse_length,
        z * inverse_length,
    )


def _sequence3(value: Sequence[float], *, name: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values.")
    return (float(value[0]), float(value[1]), float(value[2]))


def _sequence4(value: Sequence[float], *, name: str) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError(f"{name} must contain exactly four values.")
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
