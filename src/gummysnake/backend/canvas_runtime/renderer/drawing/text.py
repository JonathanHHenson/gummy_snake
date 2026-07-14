"""Text drawing and metrics for the Rust canvas renderer."""

from __future__ import annotations

from typing import cast

from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.command_ingress import pack_text_commands
from gummysnake.backend.canvas_runtime.renderer.renderer_state.payloads import text_metric_key
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererTextMixin:
    def text(self, value: str, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_model_batch()
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
        _renderer(self)._flush_model_batch()
        if not items or style.fill_color is None:
            return
        self._queue_text_batch(items, style, transform)

    def _queue_text_batch(
        self,
        items: list[tuple[str, float, float]],
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        renderer = _renderer(self)
        records, utf8 = pack_text_commands(items)
        if not items:
            return
        renderer._count("gpu_draws", len(items))
        renderer._call(
            "typed text command recording",
            renderer._require_canvas_method(
                "text_batch_packed",
                "typed text command recording",
            ),
            records,
            utf8,
            dict(renderer._style_payload(style)),
            renderer._matrix_payload(transform),
        )

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
        del final
