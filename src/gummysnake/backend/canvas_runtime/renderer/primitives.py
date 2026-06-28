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
        """Background.
        
        Args:
            color: The color value. Expected type: `Color`.
        
        Returns:
            None.
        """
        _background(self, color)

    def clear(self) -> None:
        """Clear.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _clear(self)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        """Point.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        _point(self, x, y, style, transform)

    def line(
        self,
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
        _line(self, x1, y1, x2, y2, style, transform)

    def polygon(
        self,
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
        _polygon(self, points, style, transform, close=close)

    def complex_polygon(
        self,
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
        _complex_polygon(self, outer, contours, style, transform, close=close)

    def draw_captured_shape(
        self, state: object, style: StyleState, transform: Matrix2D, *, close: bool = True
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
        _draw_captured_shape(self, state, style, transform, close=close)

    def begin_clip(
        self,
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
        _begin_clip(self, outer, contours, transform)

    def begin_clip_captured_shape(self, state: object, transform: Matrix2D) -> None:
        """Begin clip captured shape.
        
        Args:
            state: The state value. Expected type: `object`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            None.
        """
        _begin_clip_captured_shape(self, state, transform)

    def end_clip(self) -> None:
        """End clip.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _end_clip(self)

    def rect(
        self,
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
        _rect(self, x, y, width, height, style, transform)

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
        _triangle(self, x1, y1, x2, y2, x3, y3, style, transform)

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
        _quad(self, x1, y1, x2, y2, x3, y3, x4, y4, style, transform)

    def ellipse(
        self,
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
        _ellipse(self, x, y, width, height, style, transform)

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
        _arc(self, x, y, width, height, start, stop, mode, style, transform)

    def _flush_line_batch(self) -> None:
        _flush_line_batch_impl(self)

    def queue_fill_primitive_fast_path(
        self,
        kind: int,
        coords: tuple[float, ...],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        """Queue fill primitive fast path.
        
        Args:
            kind: The kind value. Expected type: `int`.
            coords: The coords value. Expected type: `tuple[float, ...]`.
            style: The style value. Expected type: `StyleState`.
            transform: The transform value. Expected type: `Matrix2D`.
        
        Returns:
            The return value. Type: `bool`.
        """
        return _queue_fill_primitive_fast_path_impl(self, kind, coords, style, transform)

    def _queue_primitive_batch(
        self,
        kind: int,
        coords: tuple[float, float, float, float, float, float],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        return _queue_primitive_batch_impl(self, kind, coords, style, transform)

    def _flush_batches_before_primitive_batch(self) -> None:
        _flush_batches_before_primitive_batch_impl(self)

    def _flush_line_batch_only(self) -> None:
        _flush_line_batch_only_impl(self)

    def _flush_primitive_batch_only(self) -> None:
        _flush_primitive_batch_only_impl(self)
