"""Path, captured-shape, and clip helpers for canvas renderer primitives."""

from __future__ import annotations

from typing import Any, cast

from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


def polygon(
    self: object,
    points: list[tuple[float, float]],
    style: StyleState,
    transform: Matrix2D,
    *,
    close: bool = True,
) -> None:
    """Polygon.
    
    Args:
        points: The points value. Expected type: `list[tuple[float, float]]`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
        close: The close value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    current = (
        getattr(_renderer(self)._require_canvas(), "polygon_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._call("polygon drawing", current, points, close)
        return
    _renderer(self)._call(
        "polygon drawing",
        _renderer(self)._require_canvas().polygon,
        points,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
        close,
    )


def complex_polygon(
    self: object,
    outer: list[tuple[float, float]],
    contours: list[list[tuple[float, float]]],
    style: StyleState,
    transform: Matrix2D,
    *,
    close: bool = True,
) -> None:
    """Complex polygon.
    
    Args:
        outer: The outer value. Expected type: `list[tuple[float, float]]`.
        contours: The contours value. Expected type: `list[list[tuple[float, float]]]`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
        close: The close value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    current = (
        getattr(_renderer(self)._require_canvas(), "complex_polygon_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._call("complex polygon drawing", current, outer, contours, close)
        return
    _renderer(self)._call(
        "complex polygon drawing",
        _renderer(self)._require_canvas_method("complex_polygon", "contour drawing"),
        outer,
        contours,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
        close,
    )


def draw_captured_shape(
    self: Any, state: object, style: StyleState, transform: Matrix2D, *, close: bool = True
) -> None:
    """Draw captured shape.
    
    Args:
        state: The state value. Expected type: `object`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
        close: The close value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    draw = (
        getattr(_renderer(self)._require_canvas(), "draw_captured_shape_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(draw):
        _renderer(self)._count("direct_shape_finalizations")
        _renderer(self)._call("captured shape drawing", draw, state, close)
        return
    draw_explicit = getattr(_renderer(self)._require_canvas(), "draw_captured_shape", None)
    if callable(draw_explicit):
        _renderer(self)._count("direct_shape_finalizations")
        _renderer(self)._call(
            "captured shape drawing",
            draw_explicit,
            state,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            close,
        )
        return
    _renderer(self)._count("shape_buffer_extractions")
    state_obj = cast(Any, state)
    outer = [tuple(point) for point in state_obj.shape_vertices()]
    contours = [list(contour) for contour in state_obj.shape_contours()]
    if contours:
        self.complex_polygon(
            outer,
            contours,
            style,
            transform,
            close=close,
        )
    else:
        self.polygon(outer, style, transform, close=close)
    reset = getattr(state_obj, "reset_shape_capture", None)
    if callable(reset):
        reset()


def begin_clip(
    self: object,
    outer: list[tuple[float, float]],
    contours: list[list[tuple[float, float]]],
    transform: Matrix2D,
) -> None:
    """Begin clip.
    
    Args:
        outer: The outer value. Expected type: `list[tuple[float, float]]`.
        contours: The contours value. Expected type: `list[list[tuple[float, float]]]`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    current = (
        getattr(_renderer(self)._require_canvas(), "begin_clip_current", None)
        if getattr(_renderer(self), "_rust_transform_synced", True)
        and (_renderer(self)._current_matrix_payload == _renderer(self)._matrix_payload(transform))
        else None
    )
    if callable(current):
        _renderer(self)._call("clip creation", current, outer, contours)
        _renderer(self)._clip_depth += 1
        return
    _renderer(self)._call(
        "clip creation",
        _renderer(self)._require_canvas_method("begin_clip", "path clipping"),
        outer,
        contours,
        _renderer(self)._matrix_payload(transform),
    )
    _renderer(self)._clip_depth += 1


def begin_clip_captured_shape(self: Any, state: object, transform: Matrix2D) -> None:
    """Begin clip captured shape.
    
    Args:
        state: The state value. Expected type: `object`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    current = (
        getattr(_renderer(self)._require_canvas(), "begin_clip_captured_current", None)
        if getattr(_renderer(self), "_rust_transform_synced", True)
        and (_renderer(self)._current_matrix_payload == _renderer(self)._matrix_payload(transform))
        else None
    )
    if callable(current):
        _renderer(self)._count("direct_shape_finalizations")
        _renderer(self)._call("captured clip creation", current, state)
        _renderer(self)._clip_depth += 1
        return
    begin_explicit = getattr(_renderer(self)._require_canvas(), "begin_clip_captured", None)
    if callable(begin_explicit):
        _renderer(self)._count("direct_shape_finalizations")
        _renderer(self)._call(
            "captured clip creation",
            begin_explicit,
            state,
            _renderer(self)._matrix_payload(transform),
        )
        _renderer(self)._clip_depth += 1
        return
    _renderer(self)._count("shape_buffer_extractions")
    state_obj = cast(Any, state)
    self.begin_clip(
        [tuple(point) for point in state_obj.shape_vertices()],
        [list(contour) for contour in state_obj.shape_contours()],
        transform,
    )
    reset = getattr(state_obj, "reset_shape_capture", None)
    if callable(reset):
        reset()


def end_clip(self: object) -> None:
    """End clip.
    
    Args:
        None.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    if _renderer(self)._clip_depth <= 0:
        raise ArgumentValidationError("end_clip() called without matching begin_clip().")
    _renderer(self)._call(
        "clip restoration",
        _renderer(self)._require_canvas_method("end_clip", "path clipping"),
    )
    _renderer(self)._clip_depth -= 1
