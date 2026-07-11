"""Shape capture, contour, and clip helpers for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from gummysnake import constants as c
from gummysnake.exceptions import ArgumentValidationError

if TYPE_CHECKING:
    from gummysnake.context_mixins.shapes import ShapeContextMixin


def _require_shape_active(ctx: ShapeContextMixin, message: str) -> None:
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(message)


def _require_contour_closed(ctx: ShapeContextMixin, message: str) -> None:
    if ctx.state.rust.contour_active:
        raise ArgumentValidationError(message)


def begin_shape(ctx: ShapeContextMixin, kind: c.ShapeKind | None = None) -> None:
    """Begin recording vertices for a shape path."""
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_shape() cannot be nested.")
    ctx.state.rust.begin_shape_capture(None if kind is None else kind.value)


def reset_shape_capture(ctx: ShapeContextMixin) -> None:
    """Clear any active shape capture state."""
    ctx.state.rust.reset_shape_capture()


def active_shape_vertices(ctx: ShapeContextMixin) -> list[tuple[float, float]]:
    """Return vertices currently recorded for the active shape."""
    return [tuple(point) for point in ctx.state.rust.active_vertices()]


@contextmanager
def shape(
    ctx: ShapeContextMixin, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
) -> Generator[None]:
    """Context manager that begins and finalizes a captured shape."""
    ctx.begin_shape(kind)
    completed = False
    try:
        yield
        ctx.end_shape(mode)
        completed = True
    finally:
        if not completed and ctx.state.rust.shape_active:
            ctx._reset_shape_capture()


def vertex(ctx: ShapeContextMixin, x: float, y: float) -> None:
    """Add a straight vertex to the active shape."""
    _require_shape_active(ctx, "vertex() must be called between begin_shape() and end_shape().")
    ctx.state.rust.add_vertex(float(x), float(y))


def bezier_vertex(
    ctx: ShapeContextMixin, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
) -> None:
    """Add a cubic Bézier segment to the active shape."""
    _require_shape_active(
        ctx, "bezier_vertex() must be called between begin_shape() and end_shape()."
    )
    ctx.state.rust.add_cubic_vertex(
        float(x2), float(y2), float(x3), float(y3), float(x4), float(y4)
    )


def quadratic_vertex(ctx: ShapeContextMixin, cx: float, cy: float, x3: float, y3: float) -> None:
    """Add a quadratic Bézier segment to the active shape."""
    _require_shape_active(
        ctx, "quadratic_vertex() must be called between begin_shape() and end_shape()."
    )
    ctx.state.rust.add_quadratic_vertex(float(cx), float(cy), float(x3), float(y3))


def spline_vertex(ctx: ShapeContextMixin, x: float, y: float) -> None:
    """Add a spline-smoothed segment to the active shape."""
    _require_shape_active(
        ctx, "spline_vertex() must be called between begin_shape() and end_shape()."
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
    scale = (1.0 - ctx._spline_tightness) / 2.0
    control1 = (
        p1[0] + (point[0] - p0[0]) * scale / 3.0,
        p1[1] + (point[1] - p0[1]) * scale / 3.0,
    )
    control2 = (
        point[0] - (point[0] - p1[0]) * scale / 3.0,
        point[1] - (point[1] - p1[1]) * scale / 3.0,
    )
    ctx.state.rust.add_cubic_vertex(
        control1[0], control1[1], control2[0], control2[1], point[0], point[1]
    )


def end_shape(ctx: ShapeContextMixin, mode: c.ArcMode = c.OPEN) -> None:
    """Finish the active shape and send it to the renderer."""
    _require_shape_active(ctx, "end_shape() requires begin_shape().")
    _require_contour_closed(ctx, "end_shape() requires end_contour() first.")
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


def begin_contour(ctx: ShapeContextMixin) -> None:
    """Begin an interior contour for the active freeform shape."""
    _require_shape_active(ctx, "begin_contour() requires begin_shape().")
    _require_contour_closed(ctx, "begin_contour() cannot be nested.")
    if ctx.state.rust.shape_kind is not None:
        raise ArgumentValidationError(
            "begin_contour() is supported only for freeform begin_shape() paths."
        )
    if ctx.state.rust.shape_vertex_count() < 3:
        raise ArgumentValidationError(
            "begin_contour() requires at least three outer shape vertices first."
        )
    ctx.state.rust.begin_contour_capture()


def end_contour(ctx: ShapeContextMixin) -> None:
    """Finish the active shape contour."""
    if not ctx.state.rust.shape_active or not ctx.state.rust.contour_active:
        raise ArgumentValidationError("end_contour() requires begin_contour().")
    if ctx.state.rust.contour_vertex_count() < 3:
        raise ArgumentValidationError("end_contour() requires at least three vertices.")
    ctx.state.rust.end_contour_capture()


@contextmanager
def contour(ctx: ShapeContextMixin) -> Generator[None]:
    """Context manager that begins and finalizes a contour."""
    ctx.begin_contour()
    completed = False
    try:
        yield
        ctx.end_contour()
        completed = True
    finally:
        if not completed and ctx.state.rust.contour_active:
            ctx.state.rust.reset_contour_capture()


def begin_clip(ctx: ShapeContextMixin) -> None:
    """Begin recording a shape path to use as a clip mask."""
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_clip() cannot be called inside begin_shape().")
    ctx.begin_shape()


def clip(ctx: ShapeContextMixin) -> None:
    """Finish the active clip path and apply it to future drawing."""
    _require_shape_active(ctx, "clip() requires begin_clip().")
    _require_contour_closed(ctx, "clip() requires end_contour() first.")
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


def end_clip(ctx: ShapeContextMixin) -> None:
    """Remove the current renderer clip path."""
    ctx.renderer.end_clip()


@contextmanager
def clip_path(ctx: ShapeContextMixin) -> Generator[None]:
    """Context manager that records and applies a clip path."""
    ctx.begin_clip()
    completed = False
    try:
        yield
        ctx.clip()
        completed = True
    finally:
        if not completed and ctx.state.rust.shape_active:
            ctx._reset_shape_capture()
