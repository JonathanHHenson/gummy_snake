"""Shape capture, contour, and clip helpers for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from gummysnake import constants as c
from gummysnake.core.geometry import flatten_cubic, flatten_quadratic, flatten_spline
from gummysnake.exceptions import ArgumentValidationError


def begin_shape(ctx: Any, kind: c.ShapeKind | None = None) -> None:
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_shape() cannot be nested.")
    ctx.state.rust.begin_shape_capture(None if kind is None else kind.value)


def reset_shape_capture(ctx: Any) -> None:
    ctx.state.rust.reset_shape_capture()


def active_shape_vertices(ctx: Any) -> list[tuple[float, float]]:
    return [tuple(point) for point in ctx.state.rust.active_vertices()]


def extend_shape_vertices(ctx: Any, vertices: list[tuple[float, float]]) -> None:
    ctx.state.rust.extend_vertices(vertices)


@contextmanager
def shape(
    ctx: Any, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
) -> Generator[None]:
    ctx.begin_shape(kind)
    completed = False
    try:
        yield
        ctx.end_shape(mode)
        completed = True
    finally:
        if not completed and ctx.state.rust.shape_active:
            ctx._reset_shape_capture()


def vertex(ctx: Any, x: float, y: float) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(
            "vertex() must be called between begin_shape() and end_shape()."
        )
    ctx.state.rust.add_vertex(float(x), float(y))


def bezier_vertex(
    ctx: Any, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
) -> None:
    vertices = ctx._active_shape_vertices()
    if not vertices:
        raise ArgumentValidationError("bezier_vertex() requires an initial vertex().")
    p0 = vertices[-1]
    ctx._extend_shape_vertices(flatten_cubic(p0, (x2, y2), (x3, y3), (x4, y4)))


def quadratic_vertex(ctx: Any, cx: float, cy: float, x3: float, y3: float) -> None:
    vertices = ctx._active_shape_vertices()
    if not vertices:
        raise ArgumentValidationError("quadratic_vertex() requires an initial vertex().")
    p0 = vertices[-1]
    ctx._extend_shape_vertices(flatten_quadratic(p0, (cx, cy), (x3, y3)))


def spline_vertex(ctx: Any, x: float, y: float) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(
            "spline_vertex() must be called between begin_shape() and end_shape()."
        )
    vertices = ctx._active_shape_vertices()
    point = (float(x), float(y))
    if not vertices:
        ctx.state.rust.add_vertex(*point)
        return
    if len(vertices) == 1:
        ctx.state.rust.add_vertex(*point)
        return
    p0 = vertices[-2]
    p1 = vertices[-1]
    ctx._extend_shape_vertices(
        flatten_spline(p0, p1, point, point, tightness=ctx._spline_tightness)
    )


def end_shape(ctx: Any, mode: c.ArcMode = c.OPEN) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError("end_shape() requires begin_shape().")
    if ctx.state.rust.contour_active:
        raise ArgumentValidationError("end_shape() requires end_contour() first.")
    draw_captured = getattr(ctx.renderer, "draw_captured_shape", None)
    if callable(draw_captured):
        draw_captured(
            ctx.state.rust,
            ctx.state.style,
            ctx.state.transform.matrix,
            close=mode == c.CLOSE,
        )
        return
    contours = [list(contour) for contour in ctx.state.rust.shape_contours()]
    vertices = [tuple(point) for point in ctx.state.rust.shape_vertices()]
    try:
        if contours:
            ctx.renderer.complex_polygon(
                vertices,
                contours,
                ctx.state.style,
                ctx.state.transform.matrix,
                close=mode == c.CLOSE,
            )
        else:
            ctx.renderer.polygon(
                vertices,
                ctx.state.style,
                ctx.state.transform.matrix,
                close=mode == c.CLOSE,
            )
    finally:
        ctx._reset_shape_capture()


def begin_contour(ctx: Any) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_contour() requires begin_shape().")
    if ctx.state.rust.contour_active:
        raise ArgumentValidationError("begin_contour() cannot be nested.")
    if ctx.state.rust.shape_kind is not None:
        raise ArgumentValidationError(
            "begin_contour() is supported only for freeform begin_shape() paths."
        )
    if ctx.state.rust.shape_vertex_count() < 3:
        raise ArgumentValidationError(
            "begin_contour() requires at least three outer shape vertices first."
        )
    ctx.state.rust.begin_contour_capture()


def end_contour(ctx: Any) -> None:
    if not ctx.state.rust.shape_active or not ctx.state.rust.contour_active:
        raise ArgumentValidationError("end_contour() requires begin_contour().")
    if ctx.state.rust.contour_vertex_count() < 3:
        raise ArgumentValidationError("end_contour() requires at least three vertices.")
    ctx.state.rust.end_contour_capture()


@contextmanager
def contour(ctx: Any) -> Generator[None]:
    ctx.begin_contour()
    completed = False
    try:
        yield
        ctx.end_contour()
        completed = True
    finally:
        if not completed and ctx.state.rust.contour_active:
            ctx.state.rust.reset_contour_capture()


def begin_clip(ctx: Any) -> None:
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_clip() cannot be called inside begin_shape().")
    ctx.begin_shape()


def clip(ctx: Any) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError("clip() requires begin_clip().")
    if ctx.state.rust.contour_active:
        raise ArgumentValidationError("clip() requires end_contour() first.")
    begin_clip_captured = getattr(ctx.renderer, "begin_clip_captured_shape", None)
    if callable(begin_clip_captured):
        begin_clip_captured(ctx.state.rust, ctx.state.transform.matrix)
        return
    try:
        ctx.renderer.begin_clip(
            [tuple(point) for point in ctx.state.rust.shape_vertices()],
            [list(contour) for contour in ctx.state.rust.shape_contours()],
            ctx.state.transform.matrix,
        )
    finally:
        ctx._reset_shape_capture()


def end_clip(ctx: Any) -> None:
    ctx.renderer.end_clip()


@contextmanager
def clip_path(ctx: Any) -> Generator[None]:
    ctx.begin_clip()
    completed = False
    try:
        yield
        ctx.clip()
        completed = True
    finally:
        if not completed and ctx.state.rust.shape_active:
            ctx._reset_shape_capture()
