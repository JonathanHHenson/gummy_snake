"""Shape capture, contour, and clip helpers for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from gummysnake import constants as c
from gummysnake.exceptions import ArgumentValidationError


def begin_shape(ctx: Any, kind: c.ShapeKind | None = None) -> None:
    """Begin shape.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.

    Returns:
        None.
    """
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_shape() cannot be nested.")
    ctx.state.rust.begin_shape_capture(None if kind is None else kind.value)


def reset_shape_capture(ctx: Any) -> None:
    """Reset shape capture.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    ctx.state.rust.reset_shape_capture()


def active_shape_vertices(ctx: Any) -> list[tuple[float, float]]:
    """Active shape vertices.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        The return value. Type: `list[tuple[float, float]]`.
    """
    return [tuple(point) for point in ctx.state.rust.active_vertices()]


def extend_shape_vertices(ctx: Any, vertices: list[tuple[float, float]]) -> None:
    """Extend shape vertices.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        vertices: The vertices value. Expected type: `list[tuple[float, float]]`.

    Returns:
        None.
    """
    ctx.state.rust.extend_vertices(vertices)


@contextmanager
def shape(
    ctx: Any, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
) -> Generator[None]:
    """Shape.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
        kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.

    Returns:
        The return value. Type: `Generator[None]`.
    """
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
    """Vertex.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.

    Returns:
        None.
    """
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(
            "vertex() must be called between begin_shape() and end_shape()."
        )
    ctx.state.rust.add_vertex(float(x), float(y))


def bezier_vertex(
    ctx: Any, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
) -> None:
    """Bezier vertex.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
        x4: The x4 value. Expected type: `float`.
        y4: The y4 value. Expected type: `float`.

    Returns:
        None.
    """
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(
            "bezier_vertex() must be called between begin_shape() and end_shape()."
        )
    ctx.state.rust.add_cubic_vertex(
        float(x2), float(y2), float(x3), float(y3), float(x4), float(y4)
    )


def quadratic_vertex(ctx: Any, cx: float, cy: float, x3: float, y3: float) -> None:
    """Quadratic vertex.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        cx: The cx value. Expected type: `float`.
        cy: The cy value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.

    Returns:
        None.
    """
    if not ctx.state.rust.shape_active:
        raise ArgumentValidationError(
            "quadratic_vertex() must be called between begin_shape() and end_shape()."
        )
    ctx.state.rust.add_quadratic_vertex(float(cx), float(cy), float(x3), float(y3))


def spline_vertex(ctx: Any, x: float, y: float) -> None:
    """Spline vertex.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.

    Returns:
        None.
    """
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


def end_shape(ctx: Any, mode: c.ArcMode = c.OPEN) -> None:
    """End shape.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.

    Returns:
        None.
    """
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
    """Begin contour.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
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
    """End contour.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    if not ctx.state.rust.shape_active or not ctx.state.rust.contour_active:
        raise ArgumentValidationError("end_contour() requires begin_contour().")
    if ctx.state.rust.contour_vertex_count() < 3:
        raise ArgumentValidationError("end_contour() requires at least three vertices.")
    ctx.state.rust.end_contour_capture()


@contextmanager
def contour(ctx: Any) -> Generator[None]:
    """Contour.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        The return value. Type: `Generator[None]`.
    """
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
    """Begin clip.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    if ctx.state.rust.shape_active:
        raise ArgumentValidationError("begin_clip() cannot be called inside begin_shape().")
    ctx.begin_shape()


def clip(ctx: Any) -> None:
    """Clip.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
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
    """End clip.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    ctx.renderer.end_clip()


@contextmanager
def clip_path(ctx: Any) -> Generator[None]:
    """Clip path.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        The return value. Type: `Generator[None]`.
    """
    ctx.begin_clip()
    completed = False
    try:
        yield
        ctx.clip()
        completed = True
    finally:
        if not completed and ctx.state.rust.shape_active:
            ctx._reset_shape_capture()
