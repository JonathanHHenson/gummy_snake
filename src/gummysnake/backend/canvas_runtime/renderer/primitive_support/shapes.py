"""Primitive drawing call helpers for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.primitive_support.batches import (
    _PRIMITIVE_ELLIPSE,
    _PRIMITIVE_LINE,
    _PRIMITIVE_RECT,
    _PRIMITIVE_TRIANGLE,
)
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import BackendCapabilityError


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


def background(self: CanvasRendererHost, color: Color) -> None:
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    _renderer(self)._call(
        "background drawing", _renderer(self)._require_canvas().background, color.to_tuple()
    )


def clear(self: CanvasRendererHost) -> None:
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    _renderer(self)._call("canvas clearing", _renderer(self)._require_canvas().clear)


def point(
    self: CanvasRendererHost, x: float, y: float, style: StyleState, transform: Matrix2D
) -> None:
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
    self: CanvasRendererHost,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
    if not self._queue_primitive_batch(
        _PRIMITIVE_LINE,
        (x1, y1, x2, y2, 0.0, 0.0),
        style,
        transform,
    ):
        raise BackendCapabilityError(
            "The installed canvas runtime does not expose typed Rust line recording. "
            "No Python line queue or per-line fallback is enabled."
        )


def rect(
    self: CanvasRendererHost,
    x: float,
    y: float,
    width: float,
    height: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
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
    self: CanvasRendererHost,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
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
    self: CanvasRendererHost,
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
    self: CanvasRendererHost,
    x: float,
    y: float,
    width: float,
    height: float,
    style: StyleState,
    transform: Matrix2D,
) -> None:
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
    self: CanvasRendererHost,
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
