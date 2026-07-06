"""Curve drawing and spline helper functions for SketchContext."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from gummysnake import constants as c
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.core.geometry import spline_point as geometry_spline_point
from gummysnake.core.geometry import spline_tangent as geometry_spline_tangent
from gummysnake.exceptions import ArgumentValidationError

if TYPE_CHECKING:
    from gummysnake.context_mixins.shapes import ShapeContextMixin


def spline(
    ctx: ShapeContextMixin,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> None:
    """Draw a Catmull-Rom-style spline segment using the current tightness."""
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


def spline_point(
    ctx: ShapeContextMixin, a: float, b: float, cc: float, d: float, t: float
) -> float:
    """Evaluate a spline coordinate at position t."""
    return geometry_spline_point(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_tangent(
    ctx: ShapeContextMixin, a: float, b: float, cc: float, d: float, t: float
) -> float:
    """Evaluate a spline tangent at position t."""
    return geometry_spline_tangent(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_property(ctx: ShapeContextMixin, name: str, value: float | None = None) -> float:
    """Read or update a named spline drawing property."""
    if name != "tightness":
        raise ArgumentValidationError("Only spline_property('tightness') is supported.")
    if value is not None:
        ctx._spline_tightness = float(value)
    return ctx._spline_tightness


def spline_properties(ctx: ShapeContextMixin, **properties: float) -> dict[str, float]:
    """Update spline drawing properties and return their current values."""
    for name, value in properties.items():
        ctx.spline_property(name, value)
    return {"tightness": ctx._spline_tightness}


def bezier(
    ctx: ShapeContextMixin,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> None:
    """Draw a cubic Bézier curve through the supplied control points."""
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
