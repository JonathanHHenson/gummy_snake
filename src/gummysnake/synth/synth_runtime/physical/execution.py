"""Public worker configuration and diagnostics for Rust synth execution."""

from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from gummysnake.exceptions import ArgumentValidationError

WorkerCount = Literal[1, 2, 4, 8, "auto"]


class SynthRuntimeDiagnostics(TypedDict):
    """Snapshot of process-wide Rust synth execution counters and limits."""

    configured_worker_count: int | None
    worker_mode: str
    worker_count: int
    worker_pool_capacity: int
    worker_pool_initializations: int
    gil_released_calls: int
    gil_released_render_calls: int
    gil_released_compile_calls: int
    gil_released_decode_calls: int
    gil_released_wav_write_calls: int
    parallel_regions: int
    parallel_tasks: int
    parallel_events: int
    serial_events: int
    parallel_scratch_peak_bytes: int
    parallel_scratch_limit_bytes: int
    parallel_min_scratch_bytes: int
    sample_source_cache_hits: int
    sample_source_cache_misses: int
    sample_source_cache_evictions: int
    sample_source_cache_bytes: int
    sample_source_cache_entries: int
    sample_source_cache_budget_bytes: int
    sample_resample_cache_hits: int
    sample_resample_cache_misses: int
    sample_resample_cache_evictions: int
    sample_resample_cache_bytes: int
    sample_resample_cache_entries: int
    sample_resample_cache_budget_bytes: int
    sample_cache_stale_invalidations: int
    sample_cache_lock_contentions: int


def configure_workers(worker_count: WorkerCount = "auto") -> int:
    """Select the bounded Rust synth worker count and return the resolved count.

    The selection changes performance only. Offline PCM and WAV bytes retain the
    same deterministic reduction order for every supported worker count.
    """

    if isinstance(worker_count, bool) or worker_count not in {1, 2, 4, 8, "auto"}:
        raise ArgumentValidationError("Synth worker count must be one of 1, 2, 4, 8, or 'auto'.")
    runtime = _require_execution_runtime()
    return int(runtime.synth_set_worker_count(worker_count))


def synth_diagnostics() -> SynthRuntimeDiagnostics:
    """Return process-wide GIL-release, worker, task, and scratch diagnostics."""

    runtime = _require_execution_runtime()
    return cast(SynthRuntimeDiagnostics, dict(runtime.synth_diagnostics()))


def reset_synth_diagnostics() -> None:
    """Reset synth counters while preserving worker configuration and the pool."""

    runtime = _require_execution_runtime()
    runtime.synth_reset_diagnostics()


def _require_execution_runtime() -> Any:
    from gummysnake.synth.synth_runtime.physical.rendering import _require_synth_runtime

    return _require_synth_runtime()


__all__ = [
    "SynthRuntimeDiagnostics",
    "WorkerCount",
    "configure_workers",
    "reset_synth_diagnostics",
    "synth_diagnostics",
]
