"""Immutable fingerprint, provenance, result, and revocation record types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from .canonical import content_hash

_PRIVATE_OR_CANDIDATE_TOKENS = frozenset(
    {
        "hostname",
        "serial",
        "uuid",
        "volume_id",
        "subject_commit",
        "source_digest",
        "tree_digest",
        "package_version",
        "wheel_hash",
        "artifact_hash",
        "free_memory",
        "temperature",
        "current_frequency",
        "load",
    }
)


class RecordError(ValueError):
    """A record is malformed or violates immutable comparison semantics."""


def _validate_stable_mapping(value: Mapping[str, object], prefix: str = "") -> None:
    for key, item in value.items():
        lowered = key.lower()
        if lowered in _PRIVATE_OR_CANDIDATE_TOKENS:
            raise RecordError(f"comparison fingerprint must exclude {prefix}{key}")
        if isinstance(item, Mapping):
            _validate_stable_mapping(item, f"{prefix}{key}.")


@dataclass(frozen=True, slots=True)
class ComparisonFingerprint:
    """Stable environment identity, intentionally separate from candidate provenance."""

    stable: Mapping[str, object]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise RecordError("unsupported fingerprint schema version")
        if not self.stable:
            raise RecordError("comparison fingerprint must not be empty")
        _validate_stable_mapping(self.stable)

    @property
    def id(self) -> str:
        return content_hash(
            {"schema_version": self.schema_version, "stable": dict(self.stable)}
        ).split(":", 1)[1]

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "stable": dict(self.stable), "id": self.id}


@dataclass(frozen=True, slots=True)
class Provenance:
    subject_commit: str
    source_digest: str
    tree_digest: str
    wheel_hash: str
    lockfile_hash: str
    build: Mapping[str, object]
    runtime: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.subject_commit or not self.source_digest or not self.tree_digest:
            raise RecordError("provenance requires subject commit and source/tree digests")
        if not self.wheel_hash or not self.lockfile_hash:
            raise RecordError("provenance requires wheel and lockfile hashes")

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_commit": self.subject_commit,
            "source_digest": self.source_digest,
            "tree_digest": self.tree_digest,
            "wheel_hash": self.wheel_hash,
            "lockfile_hash": self.lockfile_hash,
            "build": dict(self.build),
            "runtime": dict(self.runtime),
        }


@dataclass(frozen=True, slots=True)
class MetricResult:
    benchmark_key: tuple[str, int, str, str, str, int, int]
    raw_blocks_ns: tuple[tuple[int, ...], ...]
    work_per_block: int
    estimate: Decimal
    unit: str
    direction: str
    transform: str
    denominator: Decimal | None
    correctness_passed: bool = True

    def __post_init__(self) -> None:
        if not self.raw_blocks_ns or any(not blocks for blocks in self.raw_blocks_ns):
            raise RecordError("metric result requires non-empty blocks for every worker process")
        if any(value < 0 for blocks in self.raw_blocks_ns for value in blocks):
            raise RecordError("raw samples must be integer non-negative nanoseconds")
        if self.work_per_block <= 0:
            raise RecordError("work_per_block must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_key": list(self.benchmark_key),
            "raw_blocks_ns": [list(blocks) for blocks in self.raw_blocks_ns],
            "work_per_block": self.work_per_block,
            "estimate": self.estimate,
            "unit": self.unit,
            "direction": self.direction,
            "transform": self.transform,
            "denominator": self.denominator,
            "correctness_passed": self.correctness_passed,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    """Append-only suite record, whose id is a hash of all non-id content."""

    fingerprint: ComparisonFingerprint
    provenance: Provenance
    suite_id: str
    suite_version: int
    catalog_digest: str
    metrics: tuple[MetricResult, ...]
    run_conditions: Mapping[str, object]
    schema_version: int = 1
    record_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.suite_version < 1:
            raise RecordError("unsupported record schema or suite version")
        if not self.suite_id or not self.catalog_digest or not self.metrics:
            raise RecordError("record requires suite identity, catalog digest, and metrics")
        if self.provenance.subject_commit != self.provenance.subject_commit.strip():
            raise RecordError("subject commit must be normalized")
        object.__setattr__(self, "record_id", content_hash(self.payload()))

    @property
    def primary_key(self) -> tuple[str, str, str, int]:
        return (
            self.provenance.subject_commit,
            self.fingerprint.id,
            self.suite_id,
            self.suite_version,
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint.to_dict(),
            "provenance": self.provenance.to_dict(),
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "catalog_digest": self.catalog_digest,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "run_conditions": dict(self.run_conditions),
        }

    def to_dict(self) -> dict[str, object]:
        data = self.payload()
        data["record_id"] = self.record_id
        return data


@dataclass(frozen=True, slots=True)
class Revocation:
    record_id: str
    reason: str
    approval: Mapping[str, object]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.record_id.startswith("sha256:") or not self.reason or not self.approval:
            raise RecordError("revocation requires record id, reason, and approval metadata")

    @property
    def id(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "reason": self.reason,
            "approval": dict(self.approval),
        }
