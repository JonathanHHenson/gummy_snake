"""Primitive drawing methods for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake import constants as c
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererPrimitivesMixin:
    def background(self, color: Color) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "background drawing", _renderer(self)._require_canvas().background, color.to_tuple()
        )

    def clear(self) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call("canvas clearing", _renderer(self)._require_canvas().clear)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "point drawing",
            _renderer(self)._require_canvas().point,
            x,
            y,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        style_payload = _renderer(self)._style_payload(style)
        matrix_payload = _renderer(self)._matrix_payload(transform)
        if _renderer(self)._line_batch and (
            _renderer(self)._line_batch_style is not style_payload
            or _renderer(self)._line_batch_matrix is not matrix_payload
        ):
            _renderer(self)._flush_line_batch()
        _renderer(self)._line_batch.append((x1, y1, x2, y2))
        _renderer(self)._line_batch_style = style_payload
        _renderer(self)._line_batch_matrix = matrix_payload

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "polygon drawing",
            _renderer(self)._require_canvas().polygon,
            points,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            close,
        )

    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "complex polygon drawing",
            _renderer(self)._require_canvas_method("complex_polygon", "contour drawing"),
            outer,
            contours,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            close,
        )

    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._call(
            "clip creation",
            _renderer(self)._require_canvas_method("begin_clip", "path clipping"),
            outer,
            contours,
            _renderer(self)._matrix_payload(transform),
        )
        _renderer(self)._clip_depth += 1

    def end_clip(self) -> None:
        _renderer(self)._flush_line_batch()
        if _renderer(self)._clip_depth <= 0:
            from gummysnake.exceptions import ArgumentValidationError

            raise ArgumentValidationError("end_clip() called without matching begin_clip().")
        _renderer(self)._call(
            "clip restoration",
            _renderer(self)._require_canvas_method("end_clip", "path clipping"),
        )
        _renderer(self)._clip_depth -= 1

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
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
        _renderer(self)._flush_line_batch()
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
        _renderer(self)._flush_line_batch()
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
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
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
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
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

    def _flush_line_batch(self) -> None:
        if not _renderer(self)._line_batch:
            return
        lines = _renderer(self)._line_batch
        style = _renderer(self)._line_batch_style
        matrix = _renderer(self)._line_batch_matrix
        _renderer(self)._line_batch = []
        _renderer(self)._line_batch_style = None
        _renderer(self)._line_batch_matrix = None
        if style is None or matrix is None:
            return
        canvas = _renderer(self)._require_canvas()
        batch_lines = getattr(canvas, "batch_lines", None)
        if callable(batch_lines):
            _renderer(self)._count("gpu_draws", len(lines))
            _renderer(self)._call("batched line drawing", batch_lines, lines, style, matrix)
            return
        for x1, y1, x2, y2 in lines:
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call("line drawing", canvas.line, x1, y1, x2, y2, style, matrix)
