"""Curve drawing and spline helper functions for SketchContext."""

from __future__ import annotations

from typing import Any, cast

from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.core.geometry import flatten_cubic, flatten_spline
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
    p0 = (float(x1), float(y1))
    p1 = (float(x2), float(y2))
    p2 = (float(x3), float(y3))
    p3 = (float(x4), float(y4))
    previous_fill = ctx.state.style.fill_color
    ctx.state.style.fill_color = None
    cast(SketchContextHost, ctx)._mark_style_changed()
    ctx.renderer.polygon(
        [p1, *flatten_spline(p0, p1, p2, p3, tightness=ctx._spline_tightness)],
        ctx.state.style,
        ctx.state.transform.matrix,
        close=False,
    )
    ctx.state.style.fill_color = previous_fill
    cast(SketchContextHost, ctx)._mark_style_changed()


def spline_point(ctx: Any, a: float, b: float, cc: float, d: float, t: float) -> float:
    return geometry_spline_point(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_tangent(ctx: Any, a: float, b: float, cc: float, d: float, t: float) -> float:
    return geometry_spline_tangent(
        float(a), float(b), float(cc), float(d), float(t), ctx._spline_tightness
    )


def spline_property(ctx: Any, name: str, value: float | None = None) -> float:
    if name != "tightness":
        raise ArgumentValidationError("Only spline_property('tightness') is supported.")
    if value is not None:
        ctx._spline_tightness = float(value)
    return ctx._spline_tightness


def spline_properties(ctx: Any, **properties: float) -> dict[str, float]:
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
    p0 = (float(x1), float(y1))
    p1 = (float(x2), float(y2))
    p2 = (float(x3), float(y3))
    p3 = (float(x4), float(y4))
    previous_fill = ctx.state.style.fill_color
    ctx.state.style.fill_color = None
    cast(SketchContextHost, ctx)._mark_style_changed()
    ctx.renderer.polygon(
        [p0, *flatten_cubic(p0, p1, p2, p3)],
        ctx.state.style,
        ctx.state.transform.matrix,
        close=False,
    )
    ctx.state.style.fill_color = previous_fill
    cast(SketchContextHost, ctx)._mark_style_changed()
