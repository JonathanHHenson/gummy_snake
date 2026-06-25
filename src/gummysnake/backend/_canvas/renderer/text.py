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
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        if style.fill_color is None:
            return
        self._queue_text_batch([(value, x, y)], style, transform)

    def text_batch(
        self,
        items: list[tuple[str, float, float]],
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        if not items or style.fill_color is None:
            return
        self._queue_text_batch(items, style, transform)

    def _queue_text_batch(
        self,
        items: list[tuple[str, float, float]],
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        style_payload = dict(_renderer(self)._style_payload(style))
        matrix_payload = _renderer(self)._matrix_payload(transform)
        if _renderer(self)._text_batch and (
            _renderer(self)._text_batch_style != style_payload
            or _renderer(self)._text_batch_matrix != matrix_payload
        ):
            _renderer(self)._flush_text_batch()
        _renderer(self)._text_batch.extend(items)
        _renderer(self)._text_batch_style = style_payload
        _renderer(self)._text_batch_matrix = matrix_payload

    def text_width(self, value: str, style: StyleState) -> float:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_image_batch()
        renderer = _renderer(self)
        current = (
            getattr(renderer._require_canvas(), "text_width_current", None)
            if getattr(renderer, "_rust_style_synced", True)
            and getattr(renderer, "_current_style_id", None) == id(style)
            and getattr(renderer, "_current_style_revision", None) == style.revision
            else None
        )
        if callable(current):
            return _renderer(self)._cached_text_metric(
                text_metric_key("width", style, value),
                "text measurement",
                current,
                value,
            )
        return _renderer(self)._cached_text_metric(
            text_metric_key("width", style, value),
            "text measurement",
            _renderer(self)._require_canvas().text_width,
            value,
            _renderer(self)._style_payload(style),
        )

    def text_ascent(self, style: StyleState) -> float:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_image_batch()
        renderer = _renderer(self)
        current = (
            getattr(renderer._require_canvas(), "text_ascent_current", None)
            if getattr(renderer, "_rust_style_synced", True)
            and getattr(renderer, "_current_style_id", None) == id(style)
            and getattr(renderer, "_current_style_revision", None) == style.revision
            else None
        )
        if callable(current):
            return _renderer(self)._cached_text_metric(
                text_metric_key("ascent", style),
                "text ascent measurement",
                current,
            )
        return _renderer(self)._cached_text_metric(
            text_metric_key("ascent", style),
            "text ascent measurement",
            _renderer(self)._require_canvas().text_ascent,
            _renderer(self)._style_payload(style),
        )

    def text_descent(self, style: StyleState) -> float:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_image_batch()
        renderer = _renderer(self)
        current = (
            getattr(renderer._require_canvas(), "text_descent_current", None)
            if getattr(renderer, "_rust_style_synced", True)
            and getattr(renderer, "_current_style_id", None) == id(style)
            and getattr(renderer, "_current_style_revision", None) == style.revision
            else None
        )
        if callable(current):
            return _renderer(self)._cached_text_metric(
                text_metric_key("descent", style),
                "text descent measurement",
                current,
            )
        return _renderer(self)._cached_text_metric(
            text_metric_key("descent", style),
            "text descent measurement",
            _renderer(self)._require_canvas().text_descent,
            _renderer(self)._style_payload(style),
        )

    def _flush_text_batch(self, *, final: bool = False) -> None:
        if not _renderer(self)._text_batch:
            return
        items = _renderer(self)._text_batch
        style = _renderer(self)._text_batch_style
        matrix = _renderer(self)._text_batch_matrix
        _renderer(self)._text_batch = []
        _renderer(self)._text_batch_style = None
        _renderer(self)._text_batch_matrix = None
        canvas = _renderer(self)._require_canvas()
        _renderer(self)._count("gpu_draws", len(items))
        if style is None or matrix is None:
            return
        batch = getattr(canvas, "text_batch_frame" if final else "text_batch", None)
        if callable(batch):
            reused = _renderer(self)._call("batched text drawing", batch, items, style, matrix)
            if final and reused is True:
                _renderer(self)._skip_canvas_end_frame = True
            return
        for value, x, y in items:
            _renderer(self)._call("text drawing", canvas.text, value, x, y, style, matrix)
