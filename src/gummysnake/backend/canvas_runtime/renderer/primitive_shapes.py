"""Primitive drawing call helpers for the Rust canvas renderer."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    _PRIMITIVE_ELLIPSE,
    _PRIMITIVE_LINE,
    _PRIMITIVE_RECT,
    _PRIMITIVE_TRIANGLE,
)
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


def background(self: object, color: Color) -> None:
    """Background.
    
    Args:
        color: The color value. Expected type: `Color`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    _renderer(self)._call(
        "background drawing", _renderer(self)._require_canvas().background, color.to_tuple()
    )


def clear(self: object) -> None:
    """Clear.
    
    Args:
        None.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    _renderer(self)._call("canvas clearing", _renderer(self)._require_canvas().clear)


def point(self: object, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
    """Point.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    current = (
        getattr(_renderer(self)._require_canvas(), "point_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._call("point drawing", current, x, y)
        return
    _renderer(self)._call(
        "point drawing",
        _renderer(self)._require_canvas().point,
        x,
        y,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
    )


def line(
    self: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Line.
    
    Args:
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    if self._queue_primitive_batch(
        _PRIMITIVE_LINE,
        (x1, y1, x2, y2, 0.0, 0.0),
        style,
        transform,
    ):
        return
    renderer = _renderer(self)
    renderer._flush_image_batch()
    batch_lines_current = (
        getattr(renderer._require_canvas(), "batch_lines_current", None)
        if renderer._can_use_current_state(style, transform)
        else None
    )
    line_batch = renderer._line_batch_state
    if callable(batch_lines_current):
        if line_batch.has_records() and not line_batch.matches_current():
            renderer._flush_line_batch()
        line_batch.append_current((x1, y1, x2, y2))
        return
    style_payload = renderer._style_payload(style)
    matrix_payload = renderer._matrix_payload(transform)
    if line_batch.has_records() and not line_batch.matches_style(style_payload, matrix_payload):
        renderer._flush_line_batch()
    renderer._line_batch_state.append_styled((x1, y1, x2, y2), style_payload, matrix_payload)


def rect(
    self: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Rect.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    if self._queue_primitive_batch(
        _PRIMITIVE_RECT,
        (x, y, width, height, 0.0, 0.0),
        style,
        transform,
    ):
        return
    _renderer(self)._flush_line_batch()
    current = (
        getattr(_renderer(self)._require_canvas(), "rect_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call("rectangle drawing", current, x, y, width, height)
        return
    callback = getattr(_renderer(self)._require_canvas(), "rect", None)
    if callable(callback):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "rectangle drawing",
            callback,
            x,
            y,
            width,
            height,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )
        return
    self.polygon(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)], style, transform
    )


def triangle(
    self: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Triangle.
    
    Args:
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    if self._queue_primitive_batch(
        _PRIMITIVE_TRIANGLE,
        (x1, y1, x2, y2, x3, y3),
        style,
        transform,
    ):
        return
    _renderer(self)._flush_line_batch()
    current = (
        getattr(_renderer(self)._require_canvas(), "triangle_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call("triangle drawing", current, x1, y1, x2, y2, x3, y3)
        return
    callback = getattr(_renderer(self)._require_canvas(), "triangle", None)
    if callable(callback):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "triangle drawing",
            callback,
            x1,
            y1,
            x2,
            y2,
            x3,
            y3,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )
        return
    self.polygon([(x1, y1), (x2, y2), (x3, y3)], style, transform, close=True)


def quad(
    self: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Quad.
    
    Args:
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
        x4: The x4 value. Expected type: `float`.
        y4: The y4 value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    current = (
        getattr(_renderer(self)._require_canvas(), "quad_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call("quadrilateral drawing", current, x1, y1, x2, y2, x3, y3, x4, y4)
        return
    callback = getattr(_renderer(self)._require_canvas(), "quad", None)
    if callable(callback):
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "quadrilateral drawing",
            callback,
            x1,
            y1,
            x2,
            y2,
            x3,
            y3,
            x4,
            y4,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )
        return
    self.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)], style, transform, close=True)


def ellipse(
    self: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Ellipse.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    if self._queue_primitive_batch(
        _PRIMITIVE_ELLIPSE,
        (x, y, width, height, 0.0, 0.0),
        style,
        transform,
    ):
        return
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    current = (
        getattr(_renderer(self)._require_canvas(), "ellipse_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._call("ellipse drawing", current, x, y, width, height)
        return
    _renderer(self)._call(
        "ellipse drawing",
        _renderer(self)._require_canvas().ellipse,
        x,
        y,
        width,
        height,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
    )


def arc(
    self: object,
    x: float,
    y: float,
    width: float,
    height: float,
    start: float,
    stop: float,
    mode: c.ArcMode,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    """Arc.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        start: The start value. Expected type: `float`.
        stop: The stop value. Expected type: `float`.
        mode: The mode value. Expected type: `c.ArcMode`.
        style: The style value. Expected type: `StyleState`.
        transform: The transform value. Expected type: `Matrix2D`.
    
    Returns:
        None.
    """
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    current = (
        getattr(_renderer(self)._require_canvas(), "arc_current", None)
        if _renderer(self)._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _renderer(self)._call("arc drawing", current, x, y, width, height, start, stop, mode)
        return
    _renderer(self)._call(
        "arc drawing",
        _renderer(self)._require_canvas().arc,
        x,
        y,
        width,
        height,
        start,
        stop,
        mode,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
    )
