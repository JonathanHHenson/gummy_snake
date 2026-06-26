"""Renderer performance counter helpers."""

from __future__ import annotations

from typing import Any

_PERFORMANCE_COUNTER_KEYS = (
    "gpu_draws",
    "gpu_blend_commands",
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
    "pixel_noop_upload_skips",
    "primitive_batch_records",
    "primitive_batch_flushes",
    "primitive_batch_max_records",
    "primitive_batch_fallbacks",
    "image_batch_records",
    "image_batch_flushes",
    "image_batch_max_records",
    "image_batch_fallbacks",
)
PerformanceCounterValue = int | dict[str, int]
PerformanceCounters = dict[str, PerformanceCounterValue]


class CanvasRendererCounterMixin:
    _canvas: Any | None
    _performance_counters: dict[str, int]

    def _init_performance_counters(self) -> None:
        self._performance_counters = dict.fromkeys(_PERFORMANCE_COUNTER_KEYS, 0)

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
        self._init_performance_counters()
        canvas = self._canvas
        callback = (
            getattr(canvas, "reset_performance_counters", None) if canvas is not None else None
        )
        if callable(callback):
            callback()

    def _count(self, name: str, amount: int = 1) -> None:
        self._performance_counters[name] = int(self._performance_counters.get(name, 0)) + amount

    def _max_count(self, name: str, value: int) -> None:
        self._performance_counters[name] = max(
            int(self._performance_counters.get(name, 0)),
            int(value),
        )
