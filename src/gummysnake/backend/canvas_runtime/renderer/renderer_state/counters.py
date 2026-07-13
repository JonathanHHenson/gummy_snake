"""Renderer performance counter helpers."""

from __future__ import annotations

from typing import Any

_PERFORMANCE_COUNTER_KEYS = (
    "gpu_draws",
    "gpu_blend_commands",
    "gpu_region_effect_passes",
    "cpu_fallbacks",
    "pixel_readbacks",
    "pixel_readback_requested_bytes",
    "pixel_readback_copied_bytes",
    "pixel_uploads",
    "image_cache_hits",
    "image_cache_misses",
    "image_source_clones_avoided",
    "image_source_clone_bytes_avoided",
    "image_cache_resident_bytes",
    "image_cache_peak_bytes",
    "image_cache_evictions",
    "image_cache_evicted_bytes",
    "texture_cache_hits",
    "texture_uploads",
    "texture_upload_bytes",
    "texture_dirty_uploads",
    "texture_resident_bytes",
    "texture_peak_bytes",
    "texture_cache_evictions",
    "texture_destructions",
    "image_atlas_resident_bytes",
    "image_atlas_peak_bytes",
    "image_atlas_evictions",
    "image_atlas_destructions",
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
    "model_batch_records",
    "model_batch_flushes",
    "model_batch_max_records",
    "model_batch_fallbacks",
    "packed_primitive_records",
    "packed_primitive_bytes",
)
NativePerformanceCounterValue = int | float
PerformanceCounterValue = int | float | dict[str, NativePerformanceCounterValue]
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
                native_counters = {
                    str(key): value
                    for key, value in native.items()
                    if isinstance(value, int | float)
                }
                counters["native"] = native_counters
                promoted_native_keys = (
                    "packed_primitive_records",
                    "packed_primitive_bytes",
                    "pixel_readback_requested_bytes",
                    "pixel_readback_copied_bytes",
                    "image_cache_hits",
                    "image_cache_misses",
                    "image_source_clones_avoided",
                    "image_source_clone_bytes_avoided",
                    "image_cache_resident_bytes",
                    "image_cache_peak_bytes",
                    "image_cache_evictions",
                    "image_cache_evicted_bytes",
                    "texture_cache_hits",
                    "texture_uploads",
                    "texture_upload_bytes",
                    "texture_dirty_uploads",
                    "texture_resident_bytes",
                    "texture_peak_bytes",
                    "texture_cache_evictions",
                    "texture_destructions",
                    "image_atlas_resident_bytes",
                    "image_atlas_peak_bytes",
                    "image_atlas_evictions",
                    "image_atlas_destructions",
                )
                for key in promoted_native_keys:
                    value = native_counters.get(key)
                    if isinstance(value, int | float):
                        counters[key] = value
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
