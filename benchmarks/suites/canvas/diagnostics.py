"""Fail-closed adapters for public Canvas diagnostics.

The adapters consume only public context methods. They preserve stable renderer
counter names, record every public value returned by those methods, and describe
missing Epic 270 evidence explicitly instead of estimating it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from numbers import Real
from typing import Protocol

CANVAS_DIAGNOSTICS_SCHEMA_VERSION = 2
_CANVAS_DIAGNOSTICS_SOURCE = "renderer_performance_counters"
_PRESENT_SEMANTICS = "completed-runtime-present-call-not-physical-scanout"


class DiagnosticsError(RuntimeError):
    """Public diagnostics are absent, malformed, or insufficient for a case."""


class EvidenceStatus(StrEnum):
    """Qualification of one requested diagnostic family."""

    AVAILABLE = "available"
    NOT_PUBLICLY_REPORTED = "not-publicly-reported"
    PHYSICAL_QUALIFICATION_REQUIRED = "physical-qualification-required"


class RendererDiagnosticsSource(Protocol):
    """Public context surface used after a workload has completed."""

    def renderer_performance_counters(self) -> dict[str, object]: ...


class CanvasDiagnosticsSource(RendererDiagnosticsSource, Protocol):
    """Complete public context surface used by the Canvas capture adapter."""

    def performance_diagnostics(self) -> dict[str, object]: ...

    def frame_pacing_diagnostics(self) -> dict[str, object]: ...


class CanvasDiagnosticsResetSource(Protocol):
    """Public context reset surface used between benchmark samples."""

    def reset_performance_diagnostics(self) -> None: ...

    def reset_renderer_performance_counters(self) -> None: ...

    def reset_frame_pacing_diagnostics(self) -> None: ...


@dataclass(frozen=True, slots=True)
class DiagnosticRequirement:
    """Reviewed Epic 270 evidence and the public paths that can prove it."""

    name: str
    category: str
    public_paths: tuple[str, ...] = ()
    physical_qualification: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.category:
            raise ValueError("diagnostic requirements require a name and category")
        if any(not path for path in self.public_paths):
            raise ValueError("diagnostic requirement paths must be non-empty")


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    """Resolved evidence for one reviewed requirement in one snapshot."""

    name: str
    category: str
    status: EvidenceStatus
    public_paths: tuple[str, ...]
    note: str

    def as_record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status.value,
            "public_paths": list(self.public_paths),
            "note": self.note,
        }


# Empty ``public_paths`` are deliberate gap declarations. They are review points
# for runtime work outside this PBI's strict write set, not proposed counter names.
CANVAS_DIAGNOSTIC_REQUIREMENTS = (
    DiagnosticRequirement(
        "command_clone_work",
        "command",
        ("renderer.native.gpu_command_clone_count", "renderer.native.gpu_command_clone_bytes"),
    ),
    DiagnosticRequirement(
        "command_segment_allocations",
        "command",
        ("renderer.native.gpu_command_segment_allocation_count",),
        note="Allocation count is available; executed segment count is not publicly reported.",
    ),
    DiagnosticRequirement(
        "executed_command_segments",
        "command",
        note="No public executed command-segment counter is available.",
    ),
    DiagnosticRequirement(
        "path_bind_groups",
        "command",
        note="No public path bind-group counter is available.",
    ),
    DiagnosticRequirement(
        "atlas_build_details",
        "resource",
        note="Atlas dimensions, build time, source bytes, and temporary bytes are not public.",
    ),
    DiagnosticRequirement(
        "pixel_readback_bytes",
        "resource",
        (
            "renderer.pixel_readback_requested_bytes",
            "renderer.pixel_readback_copied_bytes",
        ),
    ),
    DiagnosticRequirement(
        "effect_passes",
        "command",
        ("renderer.gpu_region_effect_passes",),
    ),
    DiagnosticRequirement(
        "effect_copied_pixels",
        "resource",
        note="No public copied-pixel counter exists for effects.",
    ),
    DiagnosticRequirement(
        "completed_present_calls",
        "present",
        ("renderer.frames_presented",),
        note=_PRESENT_SEMANTICS,
    ),
    DiagnosticRequirement(
        "physical_present_feedback",
        "present",
        physical_qualification=True,
        note="Runtime present completion is not compositor feedback or physical scanout evidence.",
    ),
    DiagnosticRequirement(
        "image_cache_memory",
        "resource",
        (
            "renderer.image_cache_resident_bytes",
            "renderer.image_cache_peak_bytes",
            "renderer.image_cache_evictions",
            "renderer.image_cache_evicted_bytes",
        ),
    ),
    DiagnosticRequirement(
        "texture_memory",
        "resource",
        (
            "renderer.texture_resident_bytes",
            "renderer.texture_peak_bytes",
            "renderer.texture_destructions",
        ),
    ),
    DiagnosticRequirement(
        "image_atlas_memory",
        "resource",
        (
            "renderer.image_atlas_resident_bytes",
            "renderer.image_atlas_peak_bytes",
            "renderer.image_atlas_destructions",
        ),
    ),
    DiagnosticRequirement(
        "cpu_pixel_memory_lifecycle",
        "resource",
        note=(
            "Only cumulative native.pixel_bytes_created is public; "
            "resident/peak/destruction are absent."
        ),
    ),
    DiagnosticRequirement(
        "gpu_target_memory_lifecycle",
        "resource",
        note="GPU target resident/peak/allocation/destruction counters are not public.",
    ),
    DiagnosticRequirement(
        "text_cache_memory_lifecycle",
        "text",
        note=(
            "Text hit/miss/eviction counts are public, but bytes and destruction counts are absent."
        ),
    ),
    DiagnosticRequirement(
        "glyph_buffer_memory_lifecycle",
        "text",
        note="Glyph buffer memory counters are not public.",
    ),
    DiagnosticRequirement(
        "model_memory_lifecycle",
        "resource",
        note="Model resident/peak/allocation/destruction counters are not public.",
    ),
    DiagnosticRequirement(
        "staging_buffer_memory_lifecycle",
        "resource",
        note="Staging-buffer resident/peak/allocation/destruction counters are not public.",
    ),
    DiagnosticRequirement(
        "offscreen_canvas_memory_lifecycle",
        "resource",
        note="Offscreen-canvas resident/peak/allocation/destruction counters are not public.",
    ),
    DiagnosticRequirement(
        "text_cache_activity",
        "text",
        (
            "renderer.text_cache_hits",
            "renderer.text_cache_misses",
            "renderer.text_cache_evictions",
            "renderer.text_measurements",
        ),
    ),
    DiagnosticRequirement(
        "text_shaping_and_rasterization_time",
        "text",
        note="Public shaping/rasterization duration and category-size counters are absent.",
    ),
    DiagnosticRequirement(
        "event_polling",
        "input",
        ("renderer.event_polls",),
    ),
    DiagnosticRequirement(
        "event_poll_timing",
        "input",
        (
            "frame_pacing.event_poll_duration_ms_total",
            "frame_pacing.max_event_poll_duration_ms",
            "frame_pacing.mean_event_poll_duration_ms",
        ),
    ),
    DiagnosticRequirement(
        "event_queue_depth_coalescing_latency",
        "input",
        note="Queue depth, coalescing/drop counts, and callback latency are not public.",
    ),
    DiagnosticRequirement(
        "media_copies_and_texture_identity",
        "media",
        note="Media conversion exposes no public copy/frame or texture-identity counters.",
    ),
    DiagnosticRequirement(
        "resize_and_surface_reconfiguration_time",
        "resize",
        note="Resize allocation and surface-reconfiguration duration counters are not public.",
    ),
)


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    """Immutable, versioned public Canvas diagnostics from one actual run."""

    counters: Mapping[str, object]
    api_counters: Mapping[str, object] = field(default_factory=dict)
    frame_pacing: Mapping[str, object] = field(default_factory=dict)
    api_performance_enabled: bool = False
    execution_class: str = "unspecified"
    physical_desktop_requested: bool = False

    def counter(self, path: str) -> int | float:
        """Return a numeric counter from renderer or frame-pacing diagnostics."""

        if path.startswith("renderer."):
            return counter_at(self.counters, path.removeprefix("renderer."))
        if path.startswith("api."):
            return counter_at(self.api_counters, path.removeprefix("api."))
        if path.startswith("frame_pacing."):
            return counter_at(self.frame_pacing, path.removeprefix("frame_pacing."))
        return counter_at(self.counters, path)

    def evidence(self) -> tuple[DiagnosticEvidence, ...]:
        """Resolve the reviewed requirement inventory against this snapshot."""

        return diagnostic_evidence(self)

    def as_record(self) -> dict[str, object]:
        """Return a deterministic record without renaming stable public counters."""

        renderer = _canonical_counter_mapping(self.counters)
        api = _canonical_counter_mapping(self.api_counters)
        pacing = _canonical_public_mapping(self.frame_pacing)
        return {
            "schema_version": CANVAS_DIAGNOSTICS_SCHEMA_VERSION,
            "source": _CANVAS_DIAGNOSTICS_SOURCE,
            "counters": renderer,
            "api_performance_counters": api,
            "frame_pacing": pacing,
            "counter_groups": _counter_groups(renderer, api, pacing),
            "coverage": [item.as_record() for item in self.evidence()],
            "qualification": {
                "execution_class": self.execution_class,
                "api_performance_diagnostics_enabled": self.api_performance_enabled,
                "physical_desktop_requested": self.physical_desktop_requested,
                "physical_desktop_qualified": False,
                "physical_present_feedback_qualified": False,
                "physical_scanout_qualified": False,
                "present_counter_semantics": _PRESENT_SEMANTICS,
            },
        }


def _canonical_counter_value(value: object) -> int | float | dict[str, object]:
    if isinstance(value, bool):
        raise DiagnosticsError("renderer counters must be numeric, not boolean")
    if isinstance(value, Real):
        return int(value) if isinstance(value, int) else float(value)
    if isinstance(value, Mapping):
        return _canonical_counter_mapping(value)
    raise DiagnosticsError(f"renderer counter has unsupported value type: {type(value).__name__}")


def _canonical_counter_mapping(counters: Mapping[str, object]) -> dict[str, object]:
    if not all(isinstance(key, str) and key for key in counters):
        raise DiagnosticsError("renderer counters must use non-empty string keys")
    return {key: _canonical_counter_value(counters[key]) for key in sorted(counters)}


def _canonical_public_value(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Real):
        return int(value) if isinstance(value, int) else float(value)
    if isinstance(value, Mapping):
        return _canonical_public_mapping(value)
    raise DiagnosticsError(f"public diagnostic has unsupported value type: {type(value).__name__}")


def _canonical_public_mapping(values: Mapping[str, object]) -> dict[str, object]:
    if not all(isinstance(key, str) and key for key in values):
        raise DiagnosticsError("public diagnostics must use non-empty string keys")
    return {key: _canonical_public_value(values[key]) for key in sorted(values)}


def counter_at(counters: Mapping[str, object], path: str) -> int | float:
    """Read one required numeric counter without supplying a substitute value."""

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
    """Validate every required renderer counter before recording a workload."""

    for path in required:
        counter_at(counters, path)


def _capture_mapping(source: object, method_name: str, *, required: bool) -> Mapping[str, object]:
    callback = getattr(source, method_name, None)
    if not callable(callback):
        if required:
            raise DiagnosticsError(f"public diagnostics method unavailable: {method_name}()")
        return {}
    values = callback()
    if not isinstance(values, Mapping):
        raise DiagnosticsError(f"{method_name}() did not return a mapping")
    return values


def capture_renderer_diagnostics(
    source: RendererDiagnosticsSource, *, required: Iterable[str] = ()
) -> DiagnosticsSnapshot:
    """Capture all public renderer counters from a completed workload."""

    counters = _canonical_counter_mapping(
        _capture_mapping(source, "renderer_performance_counters", required=True)
    )
    require_counters(counters, required)
    return DiagnosticsSnapshot(counters)


def capture_canvas_diagnostics(
    source: CanvasDiagnosticsSource,
    *,
    required: Iterable[str] = (),
    execution_class: str = "unspecified",
    physical_desktop_requested: bool = False,
    require_api_performance: bool = True,
    require_frame_pacing: bool = True,
) -> DiagnosticsSnapshot:
    """Capture complete public renderer and frame-pacing diagnostics.

    Hardware/compositor qualification is never inferred from these counters.
    """

    counters = _canonical_counter_mapping(
        _capture_mapping(source, "renderer_performance_counters", required=True)
    )
    require_counters(counters, required)
    api_report = _capture_mapping(
        source, "performance_diagnostics", required=require_api_performance
    )
    api_values = api_report.get("counters", {})
    if not isinstance(api_values, Mapping):
        raise DiagnosticsError("performance_diagnostics() counters did not return a mapping")
    api_counters = _canonical_counter_mapping(api_values)
    api_enabled = api_report.get("enabled", False)
    if not isinstance(api_enabled, bool):
        raise DiagnosticsError("performance_diagnostics() enabled marker must be boolean")
    pacing = _canonical_public_mapping(
        _capture_mapping(source, "frame_pacing_diagnostics", required=require_frame_pacing)
    )
    return DiagnosticsSnapshot(
        counters,
        api_counters=api_counters,
        frame_pacing=pacing,
        api_performance_enabled=api_enabled,
        execution_class=execution_class,
        physical_desktop_requested=physical_desktop_requested,
    )


def reset_canvas_diagnostics(
    source: CanvasDiagnosticsResetSource,
    *,
    cold: bool = False,
    require_api_performance: bool = True,
    require_frame_pacing: bool = True,
) -> None:
    """Reset public activity counters while retaining semantic caches.

    There is no public benchmark-safe API that clears every Canvas semantic cache.
    Cold-state requests therefore fail instead of reconstructing or reaching into
    private runtime objects.
    """

    if cold:
        raise DiagnosticsError(
            "cold Canvas diagnostic reset is unsupported by the public API; "
            "use a fresh worker process"
        )
    callbacks: tuple[tuple[str, bool], ...] = (
        ("reset_performance_diagnostics", require_api_performance),
        ("reset_renderer_performance_counters", True),
        ("reset_frame_pacing_diagnostics", require_frame_pacing),
    )
    for method_name, required in callbacks:
        callback = getattr(source, method_name, None)
        if not callable(callback):
            if required:
                raise DiagnosticsError(f"public diagnostics reset unavailable: {method_name}()")
            continue
        callback()


def diagnostic_evidence(snapshot: DiagnosticsSnapshot) -> tuple[DiagnosticEvidence, ...]:
    """Resolve every reviewed diagnostic requirement without synthetic values."""

    result: list[DiagnosticEvidence] = []
    for requirement in CANVAS_DIAGNOSTIC_REQUIREMENTS:
        available: list[str] = []
        for path in requirement.public_paths:
            try:
                snapshot.counter(path)
            except DiagnosticsError:
                break
            available.append(path)
        if requirement.physical_qualification:
            status = EvidenceStatus.PHYSICAL_QUALIFICATION_REQUIRED
        elif requirement.public_paths and len(available) == len(requirement.public_paths):
            status = EvidenceStatus.AVAILABLE
        else:
            status = EvidenceStatus.NOT_PUBLICLY_REPORTED
        result.append(
            DiagnosticEvidence(
                requirement.name,
                requirement.category,
                status,
                tuple(available),
                requirement.note,
            )
        )
    return tuple(result)


def _flatten_numeric(values: Mapping[str, object], prefix: str) -> dict[str, int | float]:
    flattened: dict[str, int | float] = {}
    for name, value in values.items():
        path = f"{prefix}.{name}"
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, Real):
            flattened[path] = int(value) if isinstance(value, int) else float(value)
        elif isinstance(value, Mapping):
            flattened.update(_flatten_numeric(value, path))
    return flattened


def _counter_groups(
    renderer: Mapping[str, object],
    api: Mapping[str, object],
    pacing: Mapping[str, object],
) -> dict[str, dict[str, int | float]]:
    """Index all relevant public counters by non-exclusive diagnostic category."""

    flattened = {
        **_flatten_numeric(renderer, "renderer"),
        **_flatten_numeric(api, "api"),
        **_flatten_numeric(pacing, "frame_pacing"),
    }
    predicates: dict[str, Callable[[str], bool]] = {
        "command": lambda path: any(
            token in path
            for token in (
                "command",
                "draw",
                "primitive",
                "shape",
                "batch",
                "effect",
                "encode",
                "clone",
                "bind_group",
                "staged_",
            )
        ),
        "resource": lambda path: any(
            token in path
            for token in (
                "bytes",
                "cache",
                "texture",
                "atlas",
                "pixel",
                "buffer",
                "allocation",
                "destruction",
                "eviction",
                "upload",
                "resident",
                "peak",
                "model",
                "offscreen",
                "staging",
            )
        ),
        "present": lambda path: "present" in path or "frames_rendered" in path,
        "input": lambda path: any(token in path for token in ("event", "input", "queue")),
        "media": lambda path: "media" in path,
        "text": lambda path: any(token in path for token in ("text", "glyph", "shap")),
        "resize": lambda path: any(token in path for token in ("resize", "reconfig", "surface")),
    }
    return {
        category: {path: flattened[path] for path in sorted(flattened) if predicate(path)}
        for category, predicate in predicates.items()
    }


__all__ = [
    "CANVAS_DIAGNOSTICS_SCHEMA_VERSION",
    "CANVAS_DIAGNOSTIC_REQUIREMENTS",
    "CanvasDiagnosticsResetSource",
    "CanvasDiagnosticsSource",
    "DiagnosticEvidence",
    "DiagnosticRequirement",
    "DiagnosticsError",
    "DiagnosticsSnapshot",
    "EvidenceStatus",
    "RendererDiagnosticsSource",
    "capture_canvas_diagnostics",
    "capture_renderer_diagnostics",
    "counter_at",
    "diagnostic_evidence",
    "require_counters",
    "reset_canvas_diagnostics",
]
