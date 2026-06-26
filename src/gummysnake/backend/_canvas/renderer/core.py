"""Core canvas renderer state and current-style/transform synchronization."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.backend._canvas.renderer.batch_state import LineBatchState, PrimitiveBatchState
from gummysnake.backend._canvas.renderer.bridge import CanvasRendererBridgeMixin
from gummysnake.backend._canvas.renderer.counters import (
    CanvasRendererCounterMixin,
    PerformanceCounters,
)
from gummysnake.backend._canvas.renderer.lifecycle import CanvasRendererLifecycleMixin
from gummysnake.backend._canvas.renderer.payloads import (
    CanvasRendererPayloadCacheMixin,
    MatrixPayload,
    TextMetricKey,
    color_payload,
    matrix_payload,
    style_payload,
    text_metric_key,
)
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

PrimitiveBatchRecord = tuple[object, ...]
ImageBatchRecord = tuple[
    object,
    float,
    float,
    float,
    float,
    tuple[int, int, int, int] | None,
    MatrixPayload,
]

__all__ = [
    "CanvasRendererCore",
    "ImageBatchRecord",
    "MatrixPayload",
    "PerformanceCounters",
    "PrimitiveBatchRecord",
    "TextMetricKey",
    "color_payload",
    "matrix_payload",
    "style_payload",
    "text_metric_key",
]


class CanvasRendererCore(
    CanvasRendererLifecycleMixin,
    CanvasRendererBridgeMixin,
    CanvasRendererCounterMixin,
    CanvasRendererPayloadCacheMixin,
):
    def __init__(self, canvas_module: object | None = None) -> None:
        self._canvas_module = canvas_module
        self._canvas: Any | None = None
        self.width = 0
        self.height = 0
        self.physical_width = 0
        self.physical_height = 0
        self.pixel_density = 1.0
        self.renderer_mode: c.RendererMode = c.P2D
        self._init_payload_caches()
        self._current_style_id: int | None = None
        self._current_style_revision: int | None = None
        self._current_style: StyleState | None = None
        self._rust_style_synced = True
        self._current_matrix_payload: MatrixPayload = matrix_payload(Matrix2D.identity())
        self._rust_transform_synced = True
        self._line_batch_state = LineBatchState()
        self._primitive_batch_state = PrimitiveBatchState()
        self._text_batch: list[tuple[str, float, float]] = []
        self._text_batch_style: dict[str, object] | None = None
        self._text_batch_matrix: MatrixPayload | None = None
        self._image_batch: list[ImageBatchRecord] = []
        self._image_batch_style: dict[str, object] | None = None
        self._image_batch_matrix: MatrixPayload | None = None
        self._skip_canvas_end_frame = False
        self._last_pixel_bytes: bytes | None = None
        self._clip_depth = 0
        self._init_performance_counters()
        self._last_native_event_pump = 0.0
        self._abort_frame_on_native_close = False

    def set_current_style(self, style: StyleState) -> None:
        host = cast(CanvasRendererHost, self)
        host._flush_line_batch_only()
        host._flush_text_batch()
        self._current_style_id = id(style)
        self._current_style_revision = style.revision
        self._current_style = style
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_style_synced = False
            return
        callback = getattr(self._require_canvas(), "set_current_style", None)
        if callable(callback):
            self._call("current style update", callback, self._style_payload(style))
            self._rust_style_synced = True

    def set_current_matrix(self, transform: Matrix2D) -> None:
        self.remember_current_matrix(transform)
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "set_current_matrix", None)
        if callable(callback):
            self._call("current matrix update", callback, self._matrix_payload(transform))
            self._rust_transform_synced = True

    def push_canvas_state(self) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_style_synced = False
            self._rust_transform_synced = False
            return
        if not self._rust_style_synced and self._current_style is not None:
            callback = getattr(self._require_canvas(), "set_current_style", None)
            if callable(callback):
                self._call(
                    "current style update",
                    callback,
                    self._style_payload(self._current_style),
                )
                self._rust_style_synced = True
        if not self._rust_transform_synced:
            callback = getattr(self._require_canvas(), "set_current_matrix", None)
            if callable(callback):
                self._call("current matrix update", callback, self._current_matrix_payload)
                self._rust_transform_synced = True
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "push_canvas_state", None)
        if callable(callback):
            self._call("canvas state push", callback)

    def pop_canvas_state(self) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_style_synced = False
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "pop_canvas_state", None)
        if callable(callback):
            self._call("canvas state pop", callback)
            self._rust_transform_synced = True
            self._rust_style_synced = True

    def translate(self, x: float, y: float) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "translate", None)
        if callable(callback):
            self._call("canvas translation", callback, float(x), float(y))
            self._rust_transform_synced = True

    def rotate(self, angle: float) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "rotate", None)
        if callable(callback):
            self._call("canvas rotation", callback, float(angle))
            self._rust_transform_synced = True

    def scale(self, x: float, y: float | None = None) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "scale", None)
        if callable(callback):
            self._call("canvas scale", callback, float(x), None if y is None else float(y))
            self._rust_transform_synced = True

    def shear_x(self, angle: float) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "shear_x", None)
        if callable(callback):
            self._call("canvas x shear", callback, float(angle))
            self._rust_transform_synced = True

    def shear_y(self, angle: float) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "shear_y", None)
        if callable(callback):
            self._call("canvas y shear", callback, float(angle))
            self._rust_transform_synced = True

    def apply_matrix(self, transform: Matrix2D) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "apply_matrix", None)
        if callable(callback):
            self._call("canvas matrix application", callback, self._matrix_payload(transform))
            self._rust_transform_synced = True

    def reset_matrix(self) -> None:
        if self._canvas is None:
            return
        if self.renderer_mode == c.P2D:
            self._rust_transform_synced = False
            return
        cast(CanvasRendererHost, self)._flush_line_batch()
        callback = getattr(self._require_canvas(), "reset_matrix", None)
        if callable(callback):
            self._call("canvas matrix reset", callback)
            self._rust_transform_synced = True

    def _can_use_current_state(self, style: StyleState, transform: Matrix2D) -> bool:
        return (
            self._rust_style_synced
            and self._rust_transform_synced
            and self._current_style_id == id(style)
            and self._current_style_revision == style.revision
            and self._current_matrix_payload == self._matrix_payload(transform)
        )

    def remember_current_matrix(self, transform: Matrix2D) -> None:
        self._current_matrix_payload = self._matrix_payload(transform)
