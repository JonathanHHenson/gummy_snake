"""Renderer payload conversion and cache helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from gummysnake.backend._canvas.renderer.caches import LruCache
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

_TEXT_METRIC_CACHE_LIMIT = 256
_STYLE_PAYLOAD_CACHE_LIMIT = 256
_MATRIX_PAYLOAD_CACHE_LIMIT = 256

TextMetricKey = tuple[str, str | None, int, int]
MatrixPayload = tuple[float, float, float, float, float, float]


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


class _PayloadCacheHost(Protocol):
    def _count(self, name: str, amount: int = 1) -> None: ...

    def _call[T](self, operation: str, callback: Callable[..., T], *args: object) -> T: ...


class CanvasRendererPayloadCacheMixin:
    _text_metric_cache: LruCache[TextMetricKey, float]
    _style_payload_cache: dict[int, tuple[StyleState, int, dict[str, object]]]
    _style_payload_generation: int
    _matrix_payload_cache: dict[int, tuple[Matrix2D, MatrixPayload]]

    def _init_payload_caches(self) -> None:
        self._text_metric_cache = LruCache[TextMetricKey, float](_TEXT_METRIC_CACHE_LIMIT)
        self._style_payload_cache = {}
        self._style_payload_generation = 0
        self._matrix_payload_cache = {}

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

    def _cached_text_metric(
        self,
        key: TextMetricKey,
        operation: str,
        callback: Callable[..., Any],
        *args: object,
    ) -> float:
        host = cast(_PayloadCacheHost, self)
        cached = self._text_metric_cache.get(key)
        if cached is not None:
            host._count("text_cache_hits")
            return cached
        host._count("text_cache_misses")
        host._count("text_measurements")
        value = float(host._call(operation, callback, *args))
        if self._text_metric_cache.set(key, value):
            host._count("text_cache_evictions")
        return value
