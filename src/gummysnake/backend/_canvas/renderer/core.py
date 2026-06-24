"""Core canvas renderer state, caches, and bridge helpers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from time import perf_counter
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError, CanvasClosedError

_TEXT_METRIC_CACHE_LIMIT = 256
_STYLE_PAYLOAD_CACHE_LIMIT = 256
_MATRIX_PAYLOAD_CACHE_LIMIT = 256
_IMAGE_VERSION_CACHE_LIMIT = 1024
_NATIVE_EVENT_PUMP_INTERVAL_SECONDS = 1.0 / 60.0
_PERFORMANCE_COUNTER_KEYS = (
    "gpu_draws",
    "gpu_region_effect_passes",
    "cpu_fallbacks",
    "pixel_readbacks",
    "pixel_uploads",
    "image_cache_hits",
    "image_cache_misses",
    "texture_cache_hits",
    "texture_uploads",
    "text_cache_hits",
    "text_cache_misses",
    "text_cache_evictions",
    "text_measurements",
    "bridge_calls",
    "frames_presented",
    "gpu_frames_rendered",
    "event_polls",
    "direct_model_draws",
    "python_face_payloads",
    "direct_shape_finalizations",
    "shape_buffer_extractions",
    "pixel_payload_copies",
    "primitive_batch_records",
    "primitive_batch_flushes",
    "primitive_batch_fallbacks",
    "image_batch_records",
    "image_batch_flushes",
    "image_batch_fallbacks",
)
PerformanceCounterValue = int | dict[str, int]
PerformanceCounters = dict[str, PerformanceCounterValue]
TextMetricKey = tuple[str, str | None, int, int]
MatrixPayload = tuple[float, float, float, float, float, float]
PrimitiveBatchRecord = tuple[object, ...]
ImageBatchRecord = tuple[object, float, float, float, float, tuple[int, int, int, int] | None]


def color_payload(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


def style_payload(style: StyleState) -> dict[str, object]:
    return {
        "fill": color_payload(style.fill_color),
        "stroke": color_payload(style.stroke_color),
        "stroke_weight": float(style.stroke_weight),
        "image_tint": color_payload(style.image_tint),
        "blend_mode": style.blend_mode,
        "erasing": style.erasing,
        "image_sampling": style.image_sampling,
        "text_font_path": str(style.text_font.path) if style.text_font.path is not None else None,
        "text_font_name": style.text_font.name,
        "text_size": float(style.text_size),
        "text_align_x": style.text_align_x,
        "text_align_y": style.text_align_y,
        "text_leading": float(style.text_leading),
        "_style_revision": style.revision,
    }


def matrix_payload(transform: Matrix2D) -> MatrixPayload:
    return transform.as_tuple()


def text_metric_key(kind: str, style: StyleState, value: str | None = None) -> TextMetricKey:
    return (kind, value, id(style), style.revision)


class CanvasRendererCore:
    def __init__(self, canvas_module: object | None = None) -> None:
        self._canvas_module = canvas_module
        self._canvas: Any | None = None
        self.width = 0
        self.height = 0
        self.physical_width = 0
        self.physical_height = 0
        self.pixel_density = 1.0
        self.renderer_mode: c.RendererMode = c.P2D
        self._image_cache_versions: OrderedDict[int, int] = OrderedDict()
        self._text_metric_cache: OrderedDict[TextMetricKey, float] = OrderedDict()
        self._style_payload_cache: dict[int, tuple[StyleState, int, dict[str, object]]] = {}
        self._style_payload_generation = 0
        self._matrix_payload_cache: dict[int, tuple[Matrix2D, MatrixPayload]] = {}
        self._current_style_id: int | None = None
        self._current_style_revision: int | None = None
        self._current_style: StyleState | None = None
        self._rust_style_synced = True
        self._current_matrix_payload: MatrixPayload = matrix_payload(Matrix2D.identity())
        self._rust_transform_synced = True
        self._line_batch: list[tuple[float, float, float, float]] = []
        self._line_batch_style: dict[str, object] | None = None
        self._line_batch_matrix: MatrixPayload | None = None
        self._line_batch_current = False
        self._primitive_batch: list[PrimitiveBatchRecord] = []
        self._primitive_batch_style: dict[str, object] | None = None
        self._primitive_batch_matrix: MatrixPayload | None = None
        self._primitive_batch_current = False
        self._primitive_batch_mode: str | None = None
        self._text_batch: list[tuple[str, float, float]] = []
        self._text_batch_style: dict[str, object] | None = None
        self._text_batch_matrix: MatrixPayload | None = None
        self._text_batch_current = False
        self._image_batch: list[ImageBatchRecord] = []
        self._image_batch_style: dict[str, object] | None = None
        self._image_batch_matrix: MatrixPayload | None = None
        self._skip_canvas_end_frame = False
        self._clip_depth = 0
        self._performance_counters: dict[str, int] = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)
        self._last_native_event_pump = 0.0
        self._abort_frame_on_native_close = False

    def resize(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        *,
        mode: str = "headless",
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        cast(CanvasRendererHost, self)._flush_line_batch()
        canvas_type = self._canvas_type()
        self.renderer_mode = renderer
        try:
            if self._canvas is None:
                self._canvas = canvas_type(width, height, pixel_density, mode, c.P2D)
            else:
                self._canvas.resize(width, height, pixel_density, c.P2D)
            self._sync_dimensions()
            self._rust_transform_synced = True
            self._rust_style_synced = True
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        renderer: c.RendererMode | None = None,
    ) -> None:
        cast(CanvasRendererHost, self)._flush_line_batch()
        renderer_mode = self.renderer_mode if renderer is None else renderer
        try:
            resize_canvas = getattr(self._require_canvas(), "resize_canvas", None)
            if callable(resize_canvas):
                resize_canvas(width, height, pixel_density, c.P2D)
            else:
                self._require_canvas().resize(width, height, pixel_density, c.P2D)
            self.renderer_mode = renderer_mode
            self._sync_dimensions()
            self._rust_transform_synced = True
            self._rust_style_synced = True
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def _style_payload(self, style: StyleState) -> dict[str, object]:
        revision = style.revision
        key = id(style)
        cached = self._style_payload_cache.get(key)
        if cached is not None and cached[0] is style and cached[1] == revision:
            return cached[2]
        payload = style_payload(style)
        self._style_payload_generation += 1
        payload["_style_cache_key"] = self._style_payload_generation
        if len(self._style_payload_cache) >= _STYLE_PAYLOAD_CACHE_LIMIT:
            self._style_payload_cache.clear()
        self._style_payload_cache[key] = (style, revision, payload)
        return payload

    def _matrix_payload(self, transform: Matrix2D) -> MatrixPayload:
        key = id(transform)
        cached = self._matrix_payload_cache.get(key)
        if cached is not None and cached[0] is transform:
            return cached[1]
        payload = matrix_payload(transform)
        if len(self._matrix_payload_cache) >= _MATRIX_PAYLOAD_CACHE_LIMIT:
            self._matrix_payload_cache.clear()
        self._matrix_payload_cache[key] = (transform, payload)
        return payload

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

    def display_density(self) -> float:
        if self._canvas is None:
            return 1.0
        return float(self._call("display-density reporting", self._canvas.display_density))

    def performance_counters(self) -> PerformanceCounters:
        counters: PerformanceCounters = dict(self._performance_counters)
        canvas = self._canvas
        callback = getattr(canvas, "performance_counters", None) if canvas is not None else None
        if callable(callback):
            native = callback()
            if isinstance(native, dict):
                counters["native"] = {
                    str(key): int(value)
                    for key, value in native.items()
                    if isinstance(value, int | float)
                }
        return counters

    def reset_performance_counters(self) -> None:
        self._performance_counters = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)
        canvas = self._canvas
        callback = (
            getattr(canvas, "reset_performance_counters", None) if canvas is not None else None
        )
        if callable(callback):
            callback()

    def _count(self, name: str, amount: int = 1) -> None:
        self._performance_counters[name] = int(self._performance_counters.get(name, 0)) + amount

    def begin_frame(self) -> None:
        self._abort_frame_on_native_close = True
        self._skip_canvas_end_frame = False
        self._pump_native_events_if_due(force=True)
        self._require_canvas().begin_frame()

    def end_frame(self) -> None:
        try:
            cast(CanvasRendererHost, self)._flush_line_batch_only()
            cast(CanvasRendererHost, self)._flush_primitive_batch_only()
            cast(CanvasRendererHost, self)._flush_image_batch()
            cast(CanvasRendererHost, self)._flush_text_batch(final=True)
            self.restore_clip_depth(0)
            if not self._skip_canvas_end_frame:
                self._require_canvas().end_frame()
        finally:
            self._abort_frame_on_native_close = False

    def present(self) -> None:
        cast(CanvasRendererHost, self)._flush_line_batch()
        if self._pump_native_events_if_due(force=True) or self._should_close():
            return
        self._require_canvas().present()
        self._count("frames_presented")

    def close(self) -> None:
        self._abort_frame_on_native_close = False
        cast(CanvasRendererHost, self)._flush_line_batch()
        if self._canvas is not None:
            self._canvas.close()

    def runtime_canvas(self) -> Any:
        """Return the underlying Rust canvas/runtime object for backend event-loop calls."""

        return self._require_canvas()

    def _canvas_type(self) -> type[Any]:
        canvas_type = getattr(self._canvas_module, "Canvas", None)
        if canvas_type is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend found gummysnake.rust._canvas, but the "
                "runtime does not expose Canvas. Rebuild gummy_canvas before running Gummy Snake."
            )
        return canvas_type

    def _sync_dimensions(self) -> None:
        logical_width, logical_height, physical_width, physical_height, pixel_density = (
            self._require_canvas().dimensions()
        )
        self.width = int(logical_width)
        self.height = int(logical_height)
        self.physical_width = int(physical_width)
        self.physical_height = int(physical_height)
        self.pixel_density = float(pixel_density)

    def _require_canvas(self) -> Any:
        if self._canvas is None:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend has not allocated a canvas yet. "
                "Call create_canvas() before drawing."
            )
        return self._canvas

    def _call[T](self, operation: str, callback: Callable[..., T], *args: object) -> T:
        self._count("bridge_calls")
        try:
            if self._clip_depth == 0:
                self._pump_native_events_if_due()
            return callback(*args)
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise BackendCapabilityError(
                f"The 'canvas' backend failed during {operation}: {exc}"
            ) from exc

    def _pump_native_events_if_due(self, *, force: bool = False) -> bool:
        if self._canvas is None:
            return False
        now = perf_counter()
        if not force and now - self._last_native_event_pump < _NATIVE_EVENT_PUMP_INTERVAL_SECONDS:
            return False
        self._last_native_event_pump = now
        pump_native_events = getattr(self._canvas, "pump_native_events", None)
        if not callable(pump_native_events):
            return False
        closed = bool(pump_native_events())
        if not closed:
            self._sync_dimensions()
        if closed and self._abort_frame_on_native_close:
            raise CanvasClosedError("Native canvas window was closed.")
        return closed

    def _should_close(self) -> bool:
        should_close = (
            getattr(self._canvas, "should_close", None) if self._canvas is not None else None
        )
        return bool(should_close()) if callable(should_close) else False

    def clip_depth(self) -> int:
        return self._clip_depth

    def restore_clip_depth(self, depth: int) -> None:
        if depth < 0:
            raise ArgumentValidationError("Clip depth cannot be negative.")
        while self._clip_depth > depth:
            cast(CanvasRendererHost, self).end_clip()
        if self._clip_depth < depth:
            raise ArgumentValidationError("Cannot restore a deeper clip stack than is active.")

    def _require_canvas_method(self, name: str, operation: str) -> Callable[..., Any]:
        callback = getattr(self._require_canvas(), name, None)
        if callable(callback):
            return callback
        raise BackendCapabilityError(
            f"The installed gummysnake.rust._canvas runtime does not expose {name}() for "
            f"{operation}. Rebuild gummy_canvas before using this drawing feature."
        )

    def _cached_text_metric(
        self,
        key: TextMetricKey,
        operation: str,
        callback: Callable[..., Any],
        *args: object,
    ) -> float:
        cached = self._text_metric_cache.get(key)
        if cached is not None:
            self._text_metric_cache.move_to_end(key)
            self._count("text_cache_hits")
            return cached
        self._count("text_cache_misses")
        self._count("text_measurements")
        value = float(self._call(operation, callback, *args))
        self._text_metric_cache[key] = value
        if len(self._text_metric_cache) > _TEXT_METRIC_CACHE_LIMIT:
            self._text_metric_cache.popitem(last=False)
            self._count("text_cache_evictions")
        return value

    def _remember_image_cache_version(self, image_key: int, version: int) -> None:
        self._image_cache_versions[image_key] = version
        self._image_cache_versions.move_to_end(image_key)
        while len(self._image_cache_versions) > _IMAGE_VERSION_CACHE_LIMIT:
            self._image_cache_versions.popitem(last=False)
