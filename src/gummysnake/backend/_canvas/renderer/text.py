"""Text drawing and metrics for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.backend._canvas.renderer.core import text_metric_key
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererTextMixin:
    def text(self, value: str, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        _renderer(self)._flush_line_batch()
        if style.fill_color is None:
            return
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "text drawing",
            _renderer(self)._require_canvas().text,
            value,
            x,
            y,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )

    def text_width(self, value: str, style: StyleState) -> float:
        _renderer(self)._flush_line_batch()
        return _renderer(self)._cached_text_metric(
            text_metric_key("width", style, value),
            "text measurement",
            _renderer(self)._require_canvas().text_width,
            value,
            _renderer(self)._style_payload(style),
        )

    def text_ascent(self, style: StyleState) -> float:
        _renderer(self)._flush_line_batch()
        return _renderer(self)._cached_text_metric(
            text_metric_key("ascent", style),
            "text ascent measurement",
            _renderer(self)._require_canvas().text_ascent,
            _renderer(self)._style_payload(style),
        )

    def text_descent(self, style: StyleState) -> float:
        _renderer(self)._flush_line_batch()
        return _renderer(self)._cached_text_metric(
            text_metric_key("descent", style),
            "text descent measurement",
            _renderer(self)._require_canvas().text_descent,
            _renderer(self)._style_payload(style),
        )
