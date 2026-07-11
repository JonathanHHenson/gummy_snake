"""Fail-closed adapter for public Canvas renderer diagnostics.

This module intentionally reads only ``renderer_performance_counters()`` exposed
by the returned public sketch context. It does not infer missing counters or
manufacture benchmark-only values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from typing import Protocol


class DiagnosticsError(RuntimeError):
    """Public diagnostics are absent, malformed, or insufficient for a case."""


class RendererDiagnosticsSource(Protocol):
    """Public context surface used after a workload has completed."""

    def renderer_performance_counters(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    """Immutable diagnostics captured from one actual renderer run."""

    counters: Mapping[str, object]

    def counter(self, path: str) -> int | float:
        """Return a numeric counter at a dotted public diagnostics path."""

        return counter_at(self.counters, path)


def counter_at(counters: Mapping[str, object], path: str) -> int | float:
    """Read one required counter without supplying a substitute value."""

    if not path or path.startswith(".") or path.endswith("."):
        raise DiagnosticsError("required counter path must be a non-empty dotted name")
    current: object = counters
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise DiagnosticsError(f"required renderer counter unavailable: {path}")
        current = current[part]
    if isinstance(current, bool) or not isinstance(current, Real):
        raise DiagnosticsError(f"renderer counter is not numeric: {path}")
    return int(current) if isinstance(current, int) else float(current)


def require_counters(counters: Mapping[str, object], required: Iterable[str]) -> None:
    """Validate every required counter and fail before recording a workload."""

    for path in required:
        counter_at(counters, path)


def capture_renderer_diagnostics(
    source: RendererDiagnosticsSource, *, required: Iterable[str] = ()
) -> DiagnosticsSnapshot:
    """Capture production counters from a completed workload.

    A missing diagnostics method, non-mapping payload, or missing required value
    is an explicit failure. No renderer API is added and no synthetic fallback is
    provided.
    """

    counters = source.renderer_performance_counters()
    if not isinstance(counters, Mapping):
        raise DiagnosticsError("renderer_performance_counters() did not return a mapping")
    snapshot = DiagnosticsSnapshot(dict(counters))
    require_counters(snapshot.counters, required)
    return snapshot


__all__ = [
    "DiagnosticsError",
    "DiagnosticsSnapshot",
    "RendererDiagnosticsSource",
    "capture_renderer_diagnostics",
    "counter_at",
    "require_counters",
]
