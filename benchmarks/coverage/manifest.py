"""Catalog-derived, auditable coverage for executed benchmark cases.

The catalog remains the single source of truth.  A checked manifest is only a
reviewable snapshot of that catalog projection and cannot declare future or
inferred benchmark coverage.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks.schema.catalog import Catalog, MetricSpec, Workload, load_catalog

MANIFEST_SCHEMA_VERSION = 1


class CoverageManifestError(ValueError):
    """A checked coverage manifest is invalid or no longer matches its catalog."""


@dataclass(frozen=True, slots=True)
class MetricIdentity:
    """The versioned primary metric identity for an executed case."""

    id: str
    version: int

    @classmethod
    def from_metric(cls, metric: MetricSpec) -> MetricIdentity:
        return cls(id=metric.id, version=metric.version)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    """One exact benchmark case declared by a parsed static catalog."""

    workload_id: str
    workload_version: int
    case_id: str
    route: str
    runtime_parameters: Mapping[str, object]
    correctness_label: str
    sampling_profile: str
    capabilities: tuple[str, ...]
    required_counters: tuple[str, ...]
    metric_identity: MetricIdentity
    definition_digest: str

    @property
    def key(self) -> tuple[str, int, str, str, str]:
        """Stable exact-case identity used for checked-manifest comparisons."""

        return (
            self.workload_id,
            self.workload_version,
            self.case_id,
            self.route,
            self.definition_digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "workload_id": self.workload_id,
            "workload_version": self.workload_version,
            "case_id": self.case_id,
            "route": self.route,
            "runtime_parameters": _runtime_parameters(self.runtime_parameters),
            "correctness_label": self.correctness_label,
            "sampling_profile": self.sampling_profile,
            "capabilities": list(self.capabilities),
            "required_counters": list(self.required_counters),
            "metric_identity": self.metric_identity.to_dict(),
            "definition_digest": self.definition_digest,
        }


@dataclass(frozen=True, slots=True)
class CoverageManifest:
    """Deterministic projection of the executed cases in one catalog."""

    catalog_digest: str
    entries: tuple[CoverageEntry, ...]
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise CoverageManifestError("unsupported coverage manifest schema version")
        if not self.catalog_digest.startswith("sha256:"):
            raise CoverageManifestError("coverage manifest requires a catalog digest")
        keys = [entry.key for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise CoverageManifestError("coverage manifest contains duplicate exact-case entries")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "catalog_digest": self.catalog_digest,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _runtime_parameters(parameters: Mapping[str, object]) -> dict[str, object]:
    """Copy runtime values in a stable key order without deriving any new values."""

    return {key: parameters[key] for key in sorted(parameters)}


def _required_counters(parameters: Mapping[str, object]) -> tuple[str, ...]:
    """Read the dispatcher counter contract directly from runtime parameters."""

    raw = parameters.get("required_counters", ())
    if not isinstance(raw, (list, tuple)) or not all(isinstance(counter, str) for counter in raw):
        raise CoverageManifestError(
            "runtime parameter required_counters must be a list or tuple of counter names"
        )
    return tuple(raw)


def _entry(workload: Workload) -> CoverageEntry:
    parameters = _runtime_parameters(workload.parameters)
    return CoverageEntry(
        workload_id=workload.id,
        workload_version=workload.version,
        case_id=workload.case_id,
        route=workload.execution_class.value,
        runtime_parameters=parameters,
        correctness_label=workload.correctness,
        sampling_profile=workload.sampling_profile,
        capabilities=tuple(workload.capabilities),
        required_counters=_required_counters(parameters),
        metric_identity=MetricIdentity.from_metric(workload.primary_metric),
        definition_digest=workload.definition_digest,
    )


def _entry_sort_key(entry: CoverageEntry) -> tuple[str, int, str, str, str]:
    return entry.key


def build_manifest(catalog: Catalog) -> CoverageManifest:
    """Project exactly the parsed catalog workloads into deterministic coverage entries."""

    return CoverageManifest(
        catalog_digest=catalog.digest,
        entries=tuple(
            sorted((_entry(workload) for workload in catalog.workloads), key=_entry_sort_key)
        ),
    )


def load_manifest(catalog_path: Path) -> CoverageManifest:
    """Load a static catalog and project its executed workload declarations."""

    return build_manifest(load_catalog(catalog_path))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise CoverageManifestError(f"{label} must be an object with string keys")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CoverageManifestError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CoverageManifestError(f"{label} must be a positive integer")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise CoverageManifestError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _entry_from_dict(raw: Mapping[str, object]) -> CoverageEntry:
    metric = _mapping(raw.get("metric_identity"), "metric_identity")
    return CoverageEntry(
        workload_id=_string(raw.get("workload_id"), "workload_id"),
        workload_version=_positive_int(raw.get("workload_version"), "workload_version"),
        case_id=_string(raw.get("case_id"), "case_id"),
        route=_string(raw.get("route"), "route"),
        runtime_parameters=_runtime_parameters(
            _mapping(raw.get("runtime_parameters"), "runtime_parameters")
        ),
        correctness_label=_string(raw.get("correctness_label"), "correctness_label"),
        sampling_profile=_string(raw.get("sampling_profile"), "sampling_profile"),
        capabilities=_strings(raw.get("capabilities"), "capabilities"),
        required_counters=_strings(raw.get("required_counters"), "required_counters"),
        metric_identity=MetricIdentity(
            id=_string(metric.get("id"), "metric_identity.id"),
            version=_positive_int(metric.get("version"), "metric_identity.version"),
        ),
        definition_digest=_string(raw.get("definition_digest"), "definition_digest"),
    )


def manifest_from_dict(raw: Mapping[str, object]) -> CoverageManifest:
    """Parse a checked JSON manifest without depending on a TOML or CLI package."""

    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise CoverageManifestError("entries must be a list")
    return CoverageManifest(
        schema_version=_positive_int(raw.get("schema_version"), "schema_version"),
        catalog_digest=_string(raw.get("catalog_digest"), "catalog_digest"),
        entries=tuple(_entry_from_dict(_mapping(entry, "entry")) for entry in entries_raw),
    )


def load_checked_manifest(path: Path) -> CoverageManifest:
    """Load a reviewable checked manifest stored as standard-library JSON."""

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageManifestError(
            f"cannot load checked coverage manifest {path}: {error}"
        ) from error
    return manifest_from_dict(_mapping(raw, "coverage manifest"))


def _describe(entry: CoverageEntry) -> str:
    return ":".join((entry.workload_id, str(entry.workload_version), entry.case_id, entry.route))


def assert_checked_manifest(catalog: Catalog, checked: CoverageManifest) -> None:
    """Reject a checked snapshot that omits, retains, or changes executed cases."""

    actual = build_manifest(catalog)
    actual_by_key = {entry.key: entry for entry in actual.entries}
    checked_by_key = {entry.key: entry for entry in checked.entries}

    omitted = sorted(
        _describe(entry) for key, entry in actual_by_key.items() if key not in checked_by_key
    )
    stale = sorted(
        _describe(entry) for key, entry in checked_by_key.items() if key not in actual_by_key
    )
    changed = sorted(
        _describe(entry)
        for key, entry in actual_by_key.items()
        if key in checked_by_key and entry != checked_by_key[key]
    )
    if checked.catalog_digest != actual.catalog_digest:
        changed.append("catalog digest")
    if omitted or stale or changed:
        details: list[str] = []
        if omitted:
            details.append(f"omitted catalog cases: {', '.join(omitted)}")
        if stale:
            details.append(f"stale checked cases: {', '.join(stale)}")
        if changed:
            details.append(f"changed entries: {', '.join(changed)}")
        raise CoverageManifestError(
            "checked coverage manifest does not match catalog; " + "; ".join(details)
        )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "CoverageEntry",
    "CoverageManifest",
    "CoverageManifestError",
    "MetricIdentity",
    "assert_checked_manifest",
    "build_manifest",
    "load_checked_manifest",
    "load_manifest",
    "manifest_from_dict",
]
