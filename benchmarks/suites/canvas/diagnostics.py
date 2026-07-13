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

CANVAS_DIAGNOSTICS_SCHEMA_VERSION = 1
_CANVAS_DIAGNOSTICS_SOURCE = "renderer_performance_counters"


class DiagnosticsError(RuntimeError):
    """Public diagnostics are absent, malformed, or insufficient for a case."""


class RendererDiagnosticsSource(Protocol):
    """Public context surface used after a workload has completed."""

    def renderer_performance_counters(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    """Immutable, versioned public renderer diagnostics from one actual run.

    ``counters`` is deliberately preserved as the public renderer payload.  The
    versioned :meth:`as_record` wrapper is the benchmark persistence contract, so
    adding a benchmark field never mutates or renames a public renderer counter.
    """

    counters: Mapping[str, object]

    def counter(self, path: str) -> int | float:
        """Return a numeric counter at a dotted public diagnostics path."""

        return counter_at(self.counters, path)

    def as_record(self) -> dict[str, object]:
        """Return the stable benchmark record derived only from public counters."""

        return {
            "schema_version": CANVAS_DIAGNOSTICS_SCHEMA_VERSION,
            "source": _CANVAS_DIAGNOSTICS_SOURCE,
            "counters": _canonical_counter_mapping(self.counters),
        }


def _canonical_counter_value(value: object) -> int | float | dict[str, object]:
    """Validate and recursively copy public numeric counter values.

    Renderer counters are numeric scalars or nested numeric groups.  Rejecting
    every other value prevents benchmark records from silently serializing Python
    objects, clocks, or implementation-private handles.
    """

    if isinstance(value, bool):
        raise DiagnosticsError("renderer counters must be numeric, not boolean")
    if isinstance(value, Real):
        return int(value) if isinstance(value, int) else float(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) and key for key in value):
            raise DiagnosticsError("renderer counter mappings must use non-empty string keys")
        return {key: _canonical_counter_value(value[key]) for key in sorted(value)}
    raise DiagnosticsError(f"renderer counter has unsupported value type: {type(value).__name__}")


def _canonical_counter_mapping(counters: Mapping[str, object]) -> dict[str, object]:
    if not all(isinstance(key, str) and key for key in counters):
        raise DiagnosticsError("renderer counters must use non-empty string keys")
    return {key: _canonical_counter_value(counters[key]) for key in sorted(counters)}


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
    snapshot = DiagnosticsSnapshot(_canonical_counter_mapping(counters))
    require_counters(snapshot.counters, required)
    return snapshot


__all__ = [
    "CANVAS_DIAGNOSTICS_SCHEMA_VERSION",
    "DiagnosticsError",
    "DiagnosticsSnapshot",
    "RendererDiagnosticsSource",
    "capture_renderer_diagnostics",
    "counter_at",
    "require_counters",
]
