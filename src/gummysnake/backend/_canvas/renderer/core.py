# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Core canvas renderer state, caches, and bridge helpers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError

_TEXT_METRIC_CACHE_LIMIT = 256
_STYLE_PAYLOAD_CACHE_LIMIT = 256
_MATRIX_PAYLOAD_CACHE_LIMIT = 256
_IMAGE_VERSION_CACHE_LIMIT = 1024
_PERFORMANCE_COUNTER_KEYS = (
    "gpu_draws",
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
)
PerformanceCounterValue = int | dict[str, int]
PerformanceCounters = dict[str, PerformanceCounterValue]
TextMetricKey = tuple[str, str | None, tuple[tuple[str, Hashable], ...]]
MatrixPayload = tuple[float, float, float, float, float, float]


def color_payload(color: Color | None) -> tuple[int, int, int, int] | None:
    return None if color is None else color.to_tuple()


def style_payload(style: StyleState) -> dict[str, object]:
    return {
        "fill": color_payload(style.fill_color),
        "stroke": color_payload(style.stroke_color),
        "stroke_weight": float(style.stroke_weight),
        "blend_mode": style.blend_mode,
        "erasing": style.erasing,
        "image_sampling": style.image_sampling,
        "text_font_path": str(style.text_font.path) if style.text_font.path is not None else None,
        "text_font_name": style.text_font.name,
        "text_size": float(style.text_size),
        "text_align_x": style.text_align_x,
        "text_align_y": style.text_align_y,
        "text_leading": float(style.text_leading),
    }


def matrix_payload(transform: Matrix2D) -> MatrixPayload:
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)


def text_metric_key(kind: str, style: StyleState, value: str | None = None) -> TextMetricKey:
    payload = style_payload(style)
    return (
        kind,
        value,
        tuple(
            sorted(
                (payload_key, cast(Hashable, payload_value))
                for payload_key, payload_value in payload.items()
            )
        ),
    )


class CanvasRendererCore:
    def __init__(self, canvas_module: object | None = None) -> None:
        self._canvas_module = canvas_module
        self._canvas: Any | None = None
        self.width = 0
        self.height = 0
        self.physical_width = 0
        self.physical_height = 0
        self.pixel_density = 1.0
        self._image_cache_versions: OrderedDict[int, int] = OrderedDict()
        self._text_metric_cache: OrderedDict[TextMetricKey, float] = OrderedDict()
        self._style_payload_cache: dict[int, tuple[StyleState, int, dict[str, object]]] = {}
        self._matrix_payload_cache: dict[int, tuple[Matrix2D, MatrixPayload]] = {}
        self._line_batch: list[tuple[float, float, float, float]] = []
        self._line_batch_style: dict[str, object] | None = None
        self._line_batch_matrix: MatrixPayload | None = None
        self._performance_counters: dict[str, int] = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)

    def resize(
        self, width: int, height: int, pixel_density: float = 1.0, *, mode: str = "headless"
    ) -> None:
        self._flush_line_batch()
        canvas_type = self._canvas_type()
        try:
            if self._canvas is None:
                self._canvas = canvas_type(width, height, pixel_density, mode, c.P2D)
            else:
                self._canvas.resize(width, height, pixel_density, c.P2D)
            self._sync_dimensions()
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def _style_payload(self, style: StyleState) -> dict[str, object]:
        revision = style.revision
        key = id(style)
        cached = self._style_payload_cache.get(key)
        if cached is not None and cached[0] is style and cached[1] == revision:
            return cached[2]
        payload = style_payload(style)
        if len(self._style_payload_cache) >= _STYLE_PAYLOAD_CACHE_LIMIT:
            self._style_payload_cache.clear()
        self._style_payload_cache[key] = (style, revision, payload)
        return payload

    def _matrix_payload(self, transform: Matrix2D) -> MatrixPayload:
        key = id(transform)
        cached = self._matrix_payload_cache.get(key)
        if cached is not None and cached[0] == transform:
            return cached[1]
        payload = matrix_payload(transform)
        if len(self._matrix_payload_cache) >= _MATRIX_PAYLOAD_CACHE_LIMIT:
            self._matrix_payload_cache.clear()
        self._matrix_payload_cache[key] = (transform, payload)
        return payload

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
        self._require_canvas().begin_frame()

    def end_frame(self) -> None:
        self._flush_line_batch()
        self._require_canvas().end_frame()

    def present(self) -> None:
        self._flush_line_batch()
        self._require_canvas().present()
        self._count("frames_presented")

    def close(self) -> None:
        self._flush_line_batch()
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
                "extension does not expose Canvas. Rebuild gummy_canvas before running Gummy Snake."
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

    def _call(self, operation: str, callback: Callable[..., Any], *args: object) -> Any:
        self._count("bridge_calls")
        try:
            return callback(*args)
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise BackendCapabilityError(
                f"The 'canvas' backend failed during {operation}: {exc}"
            ) from exc

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
