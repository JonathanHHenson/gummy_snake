# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Primitive drawing methods for the Rust canvas renderer."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


class CanvasRendererPrimitivesMixin:
    def background(self, color: Color) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call("background drawing", self._require_canvas().background, color.to_tuple())

    def clear(self) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call("canvas clearing", self._require_canvas().clear)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "point drawing",
            self._require_canvas().point,
            x,
            y,
            self._style_payload(style),
            self._matrix_payload(transform),
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
        style_payload = self._style_payload(style)
        matrix_payload = self._matrix_payload(transform)
        if self._line_batch and (
            self._line_batch_style is not style_payload
            or self._line_batch_matrix is not matrix_payload
        ):
            self._flush_line_batch()
        self._line_batch.append((x1, y1, x2, y2))
        self._line_batch_style = style_payload
        self._line_batch_matrix = matrix_payload

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "polygon drawing",
            self._require_canvas().polygon,
            points,
            self._style_payload(style),
            self._matrix_payload(transform),
            close,
        )

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "rect", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
                "rectangle drawing",
                callback,
                x,
                y,
                width,
                height,
                self._style_payload(style),
                self._matrix_payload(transform),
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
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "triangle", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
                "triangle drawing",
                callback,
                x1,
                y1,
                x2,
                y2,
                x3,
                y3,
                self._style_payload(style),
                self._matrix_payload(transform),
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
        self._flush_line_batch()
        callback = getattr(self._require_canvas(), "quad", None)
        if callable(callback):
            self._count("gpu_draws")
            self._call(
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
                self._style_payload(style),
                self._matrix_payload(transform),
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
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "ellipse drawing",
            self._require_canvas().ellipse,
            x,
            y,
            width,
            height,
            self._style_payload(style),
            self._matrix_payload(transform),
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
        self._flush_line_batch()
        self._count("gpu_draws")
        self._call(
            "arc drawing",
            self._require_canvas().arc,
            x,
            y,
            width,
            height,
            start,
            stop,
            mode,
            self._style_payload(style),
            self._matrix_payload(transform),
        )

    def _flush_line_batch(self) -> None:
        if not self._line_batch:
            return
        lines = self._line_batch
        style = self._line_batch_style
        matrix = self._line_batch_matrix
        self._line_batch = []
        self._line_batch_style = None
        self._line_batch_matrix = None
        if style is None or matrix is None:
            return
        canvas = self._require_canvas()
        batch_lines = getattr(canvas, "batch_lines", None)
        if callable(batch_lines):
            self._count("gpu_draws", len(lines))
            self._call("batched line drawing", batch_lines, lines, style, matrix)
            return
        for x1, y1, x2, y2 in lines:
            self._count("gpu_draws")
            self._call("line drawing", canvas.line, x1, y1, x2, y2, style, matrix)
