"""Path, captured-shape, and clip helpers for canvas renderer primitives."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost, _renderer
from gummysnake.backend.canvas_runtime.renderer.command_ingress import pack_path
from gummysnake.core.state_facades import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError


class CapturedShapeState(Protocol):
    def shape_vertices(self) -> Iterable[Iterable[float]]: ...
    def shape_contours(self) -> Iterable[Iterable[tuple[float, float]]]: ...
    def reset_shape_capture(self) -> None: ...


def captured_point(point: Iterable[float]) -> tuple[float, float]:
    x, y = tuple(point)[:2]
    return float(x), float(y)


def polygon(
    self: CanvasRendererHost,
    points: list[tuple[float, float]],
    style: StyleState,
    transform: Matrix2D,
    *,
    close: bool = True,
) -> None:
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    point_records, contour_records = pack_path(points)
    if _renderer(self)._can_use_current_state(style, transform):
        current = _renderer(self)._require_canvas_method(
            "polygon_current_packed",
            "typed current-state path drawing",
        )
        _renderer(self)._call(
            "typed polygon drawing",
            current,
            point_records,
            contour_records,
            close,
        )
        return
    _renderer(self)._call(
        "typed polygon drawing",
        _renderer(self)._require_canvas_method("polygon_packed", "typed path drawing"),
        point_records,
        contour_records,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
        close,
    )


def complex_polygon(
    self: CanvasRendererHost,
    outer: list[tuple[float, float]],
    contours: list[list[tuple[float, float]]],
    style: StyleState,
    transform: Matrix2D,
    *,
    close: bool = True,
) -> None:
    _renderer(self)._flush_line_batch()
    _renderer(self)._count("gpu_draws")
    point_records, contour_records = pack_path(outer, contours)
    if _renderer(self)._can_use_current_state(style, transform):
        current = _renderer(self)._require_canvas_method(
            "polygon_current_packed",
            "typed current-state contour drawing",
        )
        _renderer(self)._call(
            "typed complex polygon drawing",
            current,
            point_records,
            contour_records,
            close,
        )
        return
    _renderer(self)._call(
        "typed complex polygon drawing",
        _renderer(self)._require_canvas_method("polygon_packed", "typed contour drawing"),
        point_records,
        contour_records,
        _renderer(self)._style_payload(style),
        _renderer(self)._matrix_payload(transform),
        close,
    )


def draw_captured_shape(
    self: CanvasRendererHost,
    state: CapturedShapeState,
    style: StyleState,
    transform: Matrix2D,
    *,
    close: bool = True,
) -> None:
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
    outer = [captured_point(point) for point in state.shape_vertices()]
    contours = [list(contour) for contour in state.shape_contours()]
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
    state.reset_shape_capture()


def begin_clip(
    self: CanvasRendererHost,
    outer: list[tuple[float, float]],
    contours: list[list[tuple[float, float]]],
    transform: Matrix2D,
) -> None:
    _renderer(self)._flush_line_batch()
    point_records, contour_records = pack_path(outer, contours)
    if getattr(_renderer(self), "_rust_transform_synced", True) and (
        _renderer(self)._current_matrix_payload == _renderer(self)._matrix_payload(transform)
    ):
        current = _renderer(self)._require_canvas_method(
            "begin_clip_current_packed",
            "typed current-state path clipping",
        )
        _renderer(self)._call(
            "typed clip creation",
            current,
            point_records,
            contour_records,
        )
        _renderer(self)._clip_depth += 1
        return
    _renderer(self)._call(
        "typed clip creation",
        _renderer(self)._require_canvas_method("begin_clip_packed", "typed path clipping"),
        point_records,
        contour_records,
        _renderer(self)._matrix_payload(transform),
    )
    _renderer(self)._clip_depth += 1


def begin_clip_captured_shape(
    self: CanvasRendererHost, state: CapturedShapeState, transform: Matrix2D
) -> None:
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
    self.begin_clip(
        [captured_point(point) for point in state.shape_vertices()],
        [list(contour) for contour in state.shape_contours()],
        transform,
    )
    state.reset_shape_capture()


def end_clip(self: CanvasRendererHost) -> None:
    _renderer(self)._flush_line_batch()
    if _renderer(self)._clip_depth <= 0:
        raise ArgumentValidationError("end_clip() called without matching begin_clip().")
    _renderer(self)._call(
        "clip restoration",
        _renderer(self)._require_canvas_method("end_clip", "path clipping"),
    )
    _renderer(self)._clip_depth -= 1
