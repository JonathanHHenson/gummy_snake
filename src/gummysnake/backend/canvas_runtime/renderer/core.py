"""Core canvas renderer state and current-style/transform synchronization."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.bridge import CanvasRendererBridgeMixin
from gummysnake.backend.canvas_runtime.renderer.lifecycle import CanvasRendererLifecycleMixin
from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
    LineBatchState,
    ModelBatchState,
    PrimitiveBatchState,
)
from gummysnake.backend.canvas_runtime.renderer.renderer_state.counters import (
    CanvasRendererCounterMixin,
    PerformanceCounters,
)
from gummysnake.backend.canvas_runtime.renderer.renderer_state.payloads import (
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
    """Public CanvasRendererCore value for Gummy Snake canvas runtime features."""

    def __init__(self, canvas_module: object | None = None) -> None:
        """Create the core Rust canvas renderer bridge state."""
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
        self._model_batch_state = ModelBatchState()
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
        """Record the active drawing style and sync it to Rust when needed.

        Args:
            style: Current Python style state that future draw calls should use.
        """

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
        """Record the active transform matrix and sync it to Rust when needed.

        Args:
            transform: Current Python transform matrix for future draw calls.
        """

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
        """Push the current style and transform state onto the Rust canvas stack."""

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
        """Pop the most recently pushed style and transform state from Rust."""

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
        """Move the Rust canvas coordinate system by a logical offset.

        Args:
            x: Horizontal offset in logical canvas units.
            y: Vertical offset in logical canvas units.
        """

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
        """Rotate the Rust canvas coordinate system.

        Args:
            angle: Rotation angle in radians.
        """

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
        """Scale the Rust canvas coordinate system.

        Args:
            x: Horizontal scale factor, or the uniform factor when ``y`` is omitted.
            y: Optional vertical scale factor.
        """

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
        """Shear the Rust canvas coordinate system along the x-axis.

        Args:
            angle: Shear angle in radians.
        """

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
        """Shear the Rust canvas coordinate system along the y-axis.

        Args:
            angle: Shear angle in radians.
        """

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
        """Apply an additional transform matrix to the Rust canvas state.

        Args:
            transform: Matrix to combine with the current Rust transform.
        """

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
        """Reset the Rust canvas transform to the identity matrix."""

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
        """Cache the Python transform payload without forcing an immediate Rust call.

        Args:
            transform: Matrix that should be considered current by later draw calls.
        """

        self._current_matrix_payload = self._matrix_payload(transform)
