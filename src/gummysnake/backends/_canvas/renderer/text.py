# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Text drawing and metrics for the Rust canvas renderer."""

from __future__ import annotations

from gummysnake.backends._canvas.renderer.core import text_metric_key
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


class CanvasRendererTextMixin:
    def text(self, value: str, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        self._flush_line_batch()
        if style.fill_color is None:
            return
        self._count("gpu_draws")
        self._call(
            "text drawing",
            self._require_canvas().text,
            value,
            x,
            y,
            self._style_payload(style),
            self._matrix_payload(transform),
        )

    def text_width(self, value: str, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            text_metric_key("width", style, value),
            "text measurement",
            self._require_canvas().text_width,
            value,
            self._style_payload(style),
        )

    def text_ascent(self, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            text_metric_key("ascent", style),
            "text ascent measurement",
            self._require_canvas().text_ascent,
            self._style_payload(style),
        )

    def text_descent(self, style: StyleState) -> float:
        self._flush_line_batch()
        return self._cached_text_metric(
            text_metric_key("descent", style),
            "text descent measurement",
            self._require_canvas().text_descent,
            self._style_payload(style),
        )
