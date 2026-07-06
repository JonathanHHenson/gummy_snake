"""Primitive drawing methods for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    _PRIMITIVE_ELLIPSE as _PRIMITIVE_ELLIPSE,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    _PRIMITIVE_LINE as _PRIMITIVE_LINE,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    _PRIMITIVE_RECT as _PRIMITIVE_RECT,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    _PRIMITIVE_TRIANGLE as _PRIMITIVE_TRIANGLE,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    flush_batches_before_primitive_batch as _flush_batches_before_primitive_batch_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    flush_line_batch as _flush_line_batch_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    flush_line_batch_only as _flush_line_batch_only_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    flush_primitive_batch_only as _flush_primitive_batch_only_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    queue_fill_primitive_fast_path as _queue_fill_primitive_fast_path_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    queue_primitive_batch as _queue_primitive_batch_impl,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import (
    CapturedShapeState,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import begin_clip as _begin_clip
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import (
    begin_clip_captured_shape as _begin_clip_captured_shape,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import (
    complex_polygon as _complex_polygon,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import (
    draw_captured_shape as _draw_captured_shape,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import end_clip as _end_clip
from gummysnake.backend.canvas_runtime.renderer.primitive_paths import polygon as _polygon
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import arc as _arc
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import background as _background
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import clear as _clear
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import ellipse as _ellipse
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import line as _line
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import point as _point
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import quad as _quad
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import rect as _rect
from gummysnake.backend.canvas_runtime.renderer.primitive_shapes import triangle as _triangle
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererPrimitivesMixin:
    def background(self, color: Color) -> None:
        _background(_renderer(self), color)

    def clear(self) -> None:
        _clear(_renderer(self))

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        _point(_renderer(self), x, y, style, transform)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _line(_renderer(self), x1, y1, x2, y2, style, transform)

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _polygon(_renderer(self), points, style, transform, close=close)

    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _complex_polygon(_renderer(self), outer, contours, style, transform, close=close)

    def draw_captured_shape(
        self,
        state: CapturedShapeState,
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _draw_captured_shape(_renderer(self), state, style, transform, close=close)

    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        transform: Matrix2D,
    ) -> None:
        _begin_clip(_renderer(self), outer, contours, transform)

    def begin_clip_captured_shape(self, state: CapturedShapeState, transform: Matrix2D) -> None:
        _begin_clip_captured_shape(_renderer(self), state, transform)

    def end_clip(self) -> None:
        _end_clip(_renderer(self))

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _rect(_renderer(self), x, y, width, height, style, transform)

    def triangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _triangle(_renderer(self), x1, y1, x2, y2, x3, y3, style, transform)

    def quad(
        self,
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
        _quad(_renderer(self), x1, y1, x2, y2, x3, y3, x4, y4, style, transform)

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _ellipse(_renderer(self), x, y, width, height, style, transform)

    def arc(
        self,
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
        _arc(_renderer(self), x, y, width, height, start, stop, mode, style, transform)

    def _flush_line_batch(self) -> None:
        _flush_line_batch_impl(_renderer(self))

    def queue_fill_primitive_fast_path(
        self,
        kind: int,
        coords: tuple[float, ...],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        return _queue_fill_primitive_fast_path_impl(_renderer(self), kind, coords, style, transform)

    def _queue_primitive_batch(
        self,
        kind: int,
        coords: tuple[float, float, float, float, float, float],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        return _queue_primitive_batch_impl(_renderer(self), kind, coords, style, transform)

    def _flush_batches_before_primitive_batch(self) -> None:
        _flush_batches_before_primitive_batch_impl(_renderer(self))

    def _flush_line_batch_only(self) -> None:
        _flush_line_batch_only_impl(_renderer(self))

    def _flush_primitive_batch_only(self) -> None:
        _flush_primitive_batch_only_impl(_renderer(self))
