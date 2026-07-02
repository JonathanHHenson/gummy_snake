"""Curve drawing and spline helper functions for SketchContext."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.core.geometry import spline_point as geometry_spline_point
from gummysnake.core.geometry import spline_tangent as geometry_spline_tangent
from gummysnake.exceptions import ArgumentValidationError


def spline(
    ctx: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> None:
    """Spline.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
        x4: The x4 value. Expected type: `float`.
        y4: The y4 value. Expected type: `float`.

    Returns:
        None.
    """
    p0 = (float(x1), float(y1))
    p1 = (float(x2), float(y2))
    p2 = (float(x3), float(y3))
    p3 = (float(x4), float(y4))
    scale = (1.0 - ctx._spline_tightness) / 2.0
    control1 = (p1[0] + (p2[0] - p0[0]) * scale / 3.0, p1[1] + (p2[1] - p0[1]) * scale / 3.0)
    control2 = (p2[0] - (p3[0] - p1[0]) * scale / 3.0, p2[1] - (p3[1] - p1[1]) * scale / 3.0)
    previous_fill = ctx.state.style.fill_color
    ctx.state.style.fill_color = None
    cast(SketchContextHost, ctx)._mark_style_changed()
    try:
        ctx.begin_shape()
        ctx.vertex(*p1)
        ctx.bezier_vertex(control1[0], control1[1], control2[0], control2[1], p2[0], p2[1])
        ctx.end_shape(c.OPEN)
    finally:
        ctx.state.style.fill_color = previous_fill
        cast(SketchContextHost, ctx)._mark_style_changed()


def spline_point(ctx: Any, a: float, b: float, cc: float, d: float, t: float) -> float:
    """Spline point.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        cc: The cc value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.

    Returns:
        The return value. Type: `float`.
    """
    return geometry_spline_point(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_tangent(ctx: Any, a: float, b: float, cc: float, d: float, t: float) -> float:
    """Spline tangent.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        cc: The cc value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.

    Returns:
        The return value. Type: `float`.
    """
    return geometry_spline_tangent(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_property(ctx: Any, name: str, value: float | None = None) -> float:
    """Spline property.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        name: The name value. Expected type: `str`.
        value: The value value. Expected type: `float | None`. Defaults to `None`.

    Returns:
        The return value. Type: `float`.
    """
    if name != "tightness":
        raise ArgumentValidationError("Only spline_property('tightness') is supported.")
    if value is not None:
        ctx._spline_tightness = float(value)
    return ctx._spline_tightness


def spline_properties(ctx: Any, **properties: float) -> dict[str, float]:
    """Spline properties.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        **properties: Additional keyword arguments. Expected type: `float`.

    Returns:
        The return value. Type: `dict[str, float]`.
    """
    for name, value in properties.items():
        ctx.spline_property(name, value)
    return {"tightness": ctx._spline_tightness}


def bezier(
    ctx: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> None:
    """Bezier.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
        x4: The x4 value. Expected type: `float`.
        y4: The y4 value. Expected type: `float`.

    Returns:
        None.
    """
    p0 = (float(x1), float(y1))
    p1 = (float(x2), float(y2))
    p2 = (float(x3), float(y3))
    p3 = (float(x4), float(y4))
    previous_fill = ctx.state.style.fill_color
    ctx.state.style.fill_color = None
    cast(SketchContextHost, ctx)._mark_style_changed()
    try:
        ctx.begin_shape()
        ctx.vertex(*p0)
        ctx.bezier_vertex(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
        ctx.end_shape(c.OPEN)
    finally:
        ctx.state.style.fill_color = previous_fill
        cast(SketchContextHost, ctx)._mark_style_changed()
