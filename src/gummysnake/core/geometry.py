"""Geometry and curve helpers."""

from __future__ import annotations

from collections.abc import Iterable

from gummysnake import constants as c


def resolve_rect(
    mode: c.ShapeMode,
    x: float,
    y: float,
    w: float,
    h: float,
) -> tuple[float, float, float, float]:
    from gummysnake.constants import CENTER, CORNER, CORNERS, RADIUS

    if mode == CORNER:
        return x, y, w, h
    if mode == CORNERS:
        return min(x, w), min(y, h), abs(w - x), abs(h - y)
    if mode == CENTER:
        return x - w / 2, y - h / 2, w, h
    if mode == RADIUS:
        return x - w, y - h, w * 2, h * 2
    msg = f"Unsupported rectangle mode {mode!r}."
    raise ValueError(msg)


def resolve_ellipse(
    mode: c.ShapeMode,
    x: float,
    y: float,
    w: float,
    h: float,
) -> tuple[float, float, float, float]:
    return resolve_rect(mode, x, y, w, h)


def bezier_point(a: float, b: float, c: float, d: float, t: float) -> float:
    mt = 1.0 - t
    return mt**3 * a + 3 * mt**2 * t * b + 3 * mt * t**2 * c + t**3 * d


def bezier_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    mt = 1.0 - t
    return 3 * mt**2 * (b - a) + 6 * mt * t * (c - b) + 3 * t**2 * (d - c)


def quadratic_point(a: float, b: float, c: float, t: float) -> float:
    mt = 1.0 - t
    return mt**2 * a + 2 * mt * t * b + t**2 * c


def spline_point(a: float, b: float, c: float, d: float, t: float, tightness: float = 0.0) -> float:
    s = (1.0 - tightness) / 2.0
    t2 = t * t
    t3 = t2 * t
    return (
        (2.0 * t3 - 3.0 * t2 + 1.0) * b
        + (t3 - 2.0 * t2 + t) * (c - a) * s
        + (-2.0 * t3 + 3.0 * t2) * c
        + (t3 - t2) * (d - b) * s
    )


def spline_tangent(
    a: float, b: float, c: float, d: float, t: float, tightness: float = 0.0
) -> float:
    s = (1.0 - tightness) / 2.0
    t2 = t * t
    return (
        (6.0 * t2 - 6.0 * t) * b
        + (3.0 * t2 - 4.0 * t + 1.0) * (c - a) * s
        + (-6.0 * t2 + 6.0 * t) * c
        + (3.0 * t2 - 2.0 * t) * (d - b) * s
    )


def flatten_spline(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    *,
    tightness: float = 0.0,
    steps: int = 24,
) -> list[tuple[float, float]]:
    return [
        (
            spline_point(p0[0], p1[0], p2[0], p3[0], index / steps, tightness),
            spline_point(p0[1], p1[1], p2[1], p3[1], index / steps, tightness),
        )
        for index in range(1, steps + 1)
    ]


def flatten_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    *,
    steps: int = 24,
) -> list[tuple[float, float]]:
    return [
        (
            bezier_point(p0[0], p1[0], p2[0], p3[0], index / steps),
            bezier_point(p0[1], p1[1], p2[1], p3[1], index / steps),
        )
        for index in range(1, steps + 1)
    ]


def flatten_quadratic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    *,
    steps: int = 24,
) -> list[tuple[float, float]]:
    return [
        (
            quadratic_point(p0[0], p1[0], p2[0], index / steps),
            quadratic_point(p0[1], p1[1], p2[1], index / steps),
        )
        for index in range(1, steps + 1)
    ]


def as_points(values: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in values]
