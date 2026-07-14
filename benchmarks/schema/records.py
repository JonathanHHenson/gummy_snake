"""Strict fingerprint, provenance, result, and benchmark record schemas."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from .canonical import CanonicalJsonError, canonical_json, canonical_json_loads, content_hash

FINGERPRINT_SCHEMA_VERSION = 1
RECORD_SCHEMA_VERSION = 1

_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_DIGEST_COMPAT = re.compile(r"^sha256:[a-zA-Z0-9._-]+$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{7,64}$")
_ARCHITECTURE_KEYS = frozenset({"architecture", "hardware_architecture", "process_architecture"})
_ARCHITECTURE_ALIASES = {
    "aarch64": "arm64",
    "arm64e": "arm64",
    "armv8": "arm64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86-64": "x86_64",
    "x86_64h": "x86_64",
    "i386": "x86",
    "i486": "x86",
    "i586": "x86",
    "i686": "x86",
}
_OS_ALIASES = {
    "darwin": "macos",
    "mac": "macos",
    "macosx": "macos",
    "osx": "macos",
    "gnu/linux": "linux",
    "windows_nt": "windows",
    "win32": "windows",
}
_FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "hostname",
        "host_name",
        "serial",
        "serial_number",
        "uuid",
        "machine_id",
        "mac_address",
        "device_id",
        "volume_id",
        "volume_uuid",
        "subject_commit",
        "source_digest",
        "tree_digest",
        "package_version",
        "package_source_version",
        "wheel_hash",
        "artifact_hash",
        "lockfile_hash",
        "free_memory",
        "available_memory",
        "temperature",
        "current_frequency",
        "current_load",
        "load_average",
        "load",
        "process_id",
        "timestamp",
    }
)
_PRIVATE_SUFFIXES = (
    "_hostname",
    "_serial",
    "_serial_number",
    "_uuid",
    "_machine_id",
    "_mac_address",
    "_device_id",
    "_volume_id",
    "_volume_uuid",
)
_CANDIDATE_SUFFIXES = (
    "_source_digest",
    "_tree_digest",
    "_wheel_hash",
    "_artifact_hash",
    "_package_version",
)


class RecordError(ValueError):
    """A record is malformed or violates immutable comparison semantics."""


def _strict_keys(
    raw: Mapping[str, object], *, allowed: frozenset[str], required: frozenset[str], label: str
) -> None:
    unknown = sorted(set(raw) - allowed)
    missing = sorted(required - set(raw))
    if unknown:
        raise RecordError(f"{label} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise RecordError(f"{label} is missing required field(s): {', '.join(missing)}")


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise RecordError(f"{label} must match {_ID.pattern}")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RecordError(f"{label} must be a positive integer")
    return value


def _non_negative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecordError(f"{label} must be a non-negative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RecordError(f"{label} must be a non-empty normalized string")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise RecordError(f"{label} must be an integer or decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise RecordError(f"{label} is not a decimal") from error
    if not result.is_finite():
        raise RecordError(f"{label} must be finite")
    return result


def _digest(value: object, label: str, *, strict: bool = False) -> str:
    pattern = _DIGEST if strict else _DIGEST_COMPAT
    if not isinstance(value, str) or not pattern.fullmatch(value):
        qualifier = "64-character lowercase " if strict else ""
        raise RecordError(f"{label} must be a {qualifier}SHA-256 digest")
    return value


def normalize_architecture(value: str) -> str:
    """Normalize common macOS, Linux, and Windows architecture aliases."""

    normalized = value.strip().lower().replace(" ", "").replace("/", "-")
    if not normalized:
        raise RecordError("architecture must not be empty")
    return _ARCHITECTURE_ALIASES.get(normalized, normalized)


def _privacy_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    return (
        normalized in _FORBIDDEN_EXACT_KEYS
        or normalized.endswith(_PRIVATE_SUFFIXES)
        or normalized.endswith(_CANDIDATE_SUFFIXES)
    )


def _validate_stable_mapping(value: Mapping[str, object], prefix: str = "") -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key or key != key.strip():
            raise RecordError(f"comparison fingerprint key at {prefix or '<root>'} is invalid")
        if _privacy_key(key):
            raise RecordError(f"comparison fingerprint must exclude {prefix}{key}")
        if isinstance(item, Mapping):
            _validate_stable_mapping(item, f"{prefix}{key}.")
        elif isinstance(item, (list, tuple)):
            for index, member in enumerate(item):
                if isinstance(member, Mapping):
                    _validate_stable_mapping(member, f"{prefix}{key}[{index}].")


def _freeze(value: object, *, key: str | None = None) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(name): _freeze(item, key=str(name)) for name, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float):
        raise RecordError("record and fingerprint payloads reject binary floats")
    if value is None or isinstance(value, (str, int, bool, Decimal)):
        if isinstance(value, str) and key in _ARCHITECTURE_KEYS:
            return normalize_architecture(value)
        if isinstance(value, str) and key == "product":
            normalized = value.strip().lower().replace(" ", "_")
            return _OS_ALIASES.get(normalized, normalized)
        if isinstance(value, str) and key in {"translation", "emulation"}:
            normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
            return "rosetta-2" if normalized in {"rosetta", "rosetta2"} else normalized
        return value
    raise RecordError(f"unsupported record value: {type(value).__name__}")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _frozen_mapping(value: Mapping[str, object], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RecordError(f"{label} must be an object")
    frozen = _freeze(value)
    assert isinstance(frozen, Mapping)
    try:
        canonical_json(frozen)
    except CanonicalJsonError as error:
        raise RecordError(f"{label} is not canonical data: {error}") from error
    return frozen


@dataclass(frozen=True, slots=True)
class ComparisonFingerprint:
    """Stable environment identity, intentionally separate from candidate provenance."""

    stable: Mapping[str, object]
    schema_version: int = FINGERPRINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FINGERPRINT_SCHEMA_VERSION:
            raise RecordError(
                f"unsupported fingerprint schema version {self.schema_version}; "
                f"expected {FINGERPRINT_SCHEMA_VERSION}"
            )
        if not isinstance(self.stable, Mapping) or not self.stable:
            raise RecordError("comparison fingerprint must not be empty")
        _validate_stable_mapping(self.stable)
        normalized = _frozen_mapping(self.stable, "comparison fingerprint")
        _validate_stable_mapping(normalized)
        object.__setattr__(self, "stable", normalized)

    @property
    def id(self) -> str:
        return content_hash(
            {"schema_version": self.schema_version, "stable": _thaw(self.stable)}
        ).split(":", 1)[1]

    def to_dict(self) -> dict[str, object]:
        stable = _thaw(self.stable)
        assert isinstance(stable, dict)
        return {"schema_version": self.schema_version, "stable": stable, "id": self.id}

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ComparisonFingerprint:
        _strict_keys(
            raw,
            allowed=frozenset({"schema_version", "stable", "id"}),
            required=frozenset({"schema_version", "stable", "id"}),
            label="fingerprint",
        )
        stable = raw["stable"]
        if not isinstance(stable, Mapping):
            raise RecordError("fingerprint stable field must be an object")
        fingerprint = cls(
            stable,
            _positive_integer(raw["schema_version"], "fingerprint schema_version"),
        )
        if raw["id"] != fingerprint.id:
            raise RecordError("fingerprint id does not match normalized stable content")
        return fingerprint


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
        subject = _text(self.subject_commit, "subject commit").lower()
        object.__setattr__(self, "subject_commit", subject)
        _digest(self.source_digest, "source_digest")
        _digest(self.tree_digest, "tree_digest")
        _digest(self.wheel_hash, "wheel_hash")
        _digest(self.lockfile_hash, "lockfile_hash")
        object.__setattr__(self, "build", _frozen_mapping(self.build, "build provenance"))
        object.__setattr__(self, "runtime", _frozen_mapping(self.runtime, "runtime provenance"))

    def to_dict(self) -> dict[str, object]:
        build = _thaw(self.build)
        runtime = _thaw(self.runtime)
        assert isinstance(build, dict) and isinstance(runtime, dict)
        return {
            "subject_commit": self.subject_commit,
            "source_digest": self.source_digest,
            "tree_digest": self.tree_digest,
            "wheel_hash": self.wheel_hash,
            "lockfile_hash": self.lockfile_hash,
            "build": build,
            "runtime": runtime,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object], *, strict_digests: bool = True) -> Provenance:
        fields = frozenset(
            {
                "subject_commit",
                "source_digest",
                "tree_digest",
                "wheel_hash",
                "lockfile_hash",
                "build",
                "runtime",
            }
        )
        _strict_keys(raw, allowed=fields, required=fields, label="provenance")
        subject = _text(raw["subject_commit"], "subject commit").lower()
        if strict_digests and not _GIT_OBJECT.fullmatch(subject):
            raise RecordError("parsed subject commit must be a hexadecimal Git object id")
        build = raw["build"]
        runtime = raw["runtime"]
        if not isinstance(build, Mapping) or not isinstance(runtime, Mapping):
            raise RecordError("provenance build and runtime fields must be objects")
        for name in ("source_digest", "tree_digest", "wheel_hash", "lockfile_hash"):
            _digest(raw[name], name, strict=strict_digests)
        return cls(
            subject,
            str(raw["source_digest"]),
            str(raw["tree_digest"]),
            str(raw["wheel_hash"]),
            str(raw["lockfile_hash"]),
            build,
            runtime,
        )


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _estimate(raw_blocks: tuple[tuple[int, ...], ...], work_per_block: int) -> Decimal:
    process_medians = tuple(
        _median(tuple(Decimal(value) / Decimal(work_per_block) for value in process))
        for process in raw_blocks
    )
    return _median(process_medians)


def _benchmark_key(
    value: object, *, strict_digest: bool = False
) -> tuple[str, int, str, str, str, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 7:
        raise RecordError("benchmark_key must contain seven identity fields")
    benchmark, benchmark_version, case, parameter, metric, metric_version, suite_version = value
    return (
        _id(benchmark, "benchmark key benchmark id"),
        _positive_integer(benchmark_version, "benchmark version"),
        _id(case, "benchmark key case id"),
        _digest(parameter, "parameter digest", strict=strict_digest),
        _id(metric, "benchmark key metric id"),
        _positive_integer(metric_version, "metric version"),
        _positive_integer(suite_version, "suite version"),
    )


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
    aggregation: str = "median-of-process-medians"
    precision: int = 0
    valid_domain: str = "non-negative"

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_key", _benchmark_key(self.benchmark_key))
        if not isinstance(self.raw_blocks_ns, (list, tuple)) or not self.raw_blocks_ns:
            raise RecordError("metric result requires non-empty process blocks")
        blocks: list[tuple[int, ...]] = []
        for process in self.raw_blocks_ns:
            if not isinstance(process, (list, tuple)) or not process:
                raise RecordError("metric result requires non-empty blocks for every process")
            converted: list[int] = []
            for value in process:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise RecordError("raw samples must be integer non-negative nanoseconds")
                converted.append(value)
            blocks.append(tuple(converted))
        object.__setattr__(self, "raw_blocks_ns", tuple(blocks))
        work = _positive_integer(self.work_per_block, "work_per_block")
        estimate = _decimal(self.estimate, "metric estimate")
        object.__setattr__(self, "estimate", estimate)
        if estimate != _estimate(tuple(blocks), work):
            raise RecordError("metric estimate is not recomputable from raw process blocks")
        _text(self.unit, "metric unit")
        if self.direction not in {"lower-is-better", "higher-is-better"}:
            raise RecordError("metric direction is unsupported")
        if self.transform not in {"ratio", "absolute", "positive-offset-ratio"}:
            raise RecordError("metric transform is unsupported")
        if not isinstance(self.correctness_passed, bool):
            raise RecordError("correctness_passed must be a boolean")
        _id(self.aggregation, "metric aggregation")
        _non_negative_integer(self.precision, "metric precision")
        if self.valid_domain not in {"non-negative", "positive", "signed"}:
            raise RecordError("metric valid_domain is unsupported")
        if self.valid_domain == "positive" and estimate <= 0:
            raise RecordError("positive-domain metric estimate must be positive")
        if self.valid_domain == "non-negative" and estimate < 0:
            raise RecordError("non-negative metric estimate must not be negative")
        if self.transform in {"ratio", "positive-offset-ratio"}:
            if self.denominator is None:
                raise RecordError("percentage metric requires an explicit positive denominator")
            denominator = _decimal(self.denominator, "metric denominator")
            if denominator <= 0:
                raise RecordError("percentage metric denominator must be strictly positive")
            object.__setattr__(self, "denominator", denominator)
        elif self.denominator is not None:
            raise RecordError("absolute metric must not declare a percentage denominator")

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
            "aggregation": self.aggregation,
            "precision": self.precision,
            "valid_domain": self.valid_domain,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> MetricResult:
        allowed = frozenset(
            {
                "benchmark_key",
                "raw_blocks_ns",
                "work_per_block",
                "estimate",
                "unit",
                "direction",
                "transform",
                "denominator",
                "correctness_passed",
                "aggregation",
                "precision",
                "valid_domain",
            }
        )
        required = frozenset(
            {
                "benchmark_key",
                "raw_blocks_ns",
                "work_per_block",
                "estimate",
                "unit",
                "direction",
                "transform",
                "denominator",
                "correctness_passed",
            }
        )
        _strict_keys(raw, allowed=allowed, required=required, label="metric result")
        blocks = raw["raw_blocks_ns"]
        if not isinstance(blocks, list):
            raise RecordError("raw_blocks_ns must be a list of process lists")
        return cls(
            _benchmark_key(raw["benchmark_key"], strict_digest=True),
            tuple(tuple(process) if isinstance(process, list) else () for process in blocks),
            _positive_integer(raw["work_per_block"], "work_per_block"),
            _decimal(raw["estimate"], "metric estimate"),
            _text(raw["unit"], "metric unit"),
            _text(raw["direction"], "metric direction"),
            _text(raw["transform"], "metric transform"),
            _decimal(raw["denominator"], "metric denominator")
            if raw["denominator"] is not None
            else None,
            raw["correctness_passed"]
            if isinstance(raw["correctness_passed"], bool)
            else _raise("correctness_passed must be a boolean"),
            _id(raw.get("aggregation", "median-of-process-medians"), "metric aggregation"),
            _non_negative_integer(raw.get("precision", 0), "metric precision"),
            _text(raw.get("valid_domain", "non-negative"), "metric valid_domain"),
        )


def _raise(message: str) -> Any:
    raise RecordError(message)


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    id: str
    required: bool
    available: bool
    detail: str = ""

    def __post_init__(self) -> None:
        _id(self.id, "capability id")
        if not isinstance(self.required, bool) or not isinstance(self.available, bool):
            raise RecordError("capability required/available values must be booleans")
        if not isinstance(self.detail, str):
            raise RecordError("capability detail must be a string")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "required": self.required,
            "available": self.available,
            "detail": self.detail,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> CapabilityResult:
        fields = frozenset({"id", "required", "available", "detail"})
        _strict_keys(
            raw,
            allowed=fields,
            required=fields - frozenset({"detail"}),
            label="capability result",
        )
        detail = raw.get("detail", "")
        if not isinstance(detail, str):
            raise RecordError("detail must be str")
        return cls(
            _id(raw["id"], "capability id"),
            raw["required"]
            if isinstance(raw["required"], bool)
            else _raise("required must be bool"),
            raw["available"]
            if isinstance(raw["available"], bool)
            else _raise("available must be bool"),
            detail,
        )


@dataclass(frozen=True, slots=True)
class CorrectnessResult:
    id: str
    passed: bool
    expected: object
    observed: object

    def __post_init__(self) -> None:
        _id(self.id, "correctness id")
        if not isinstance(self.passed, bool):
            raise RecordError("correctness passed value must be a boolean")
        object.__setattr__(self, "expected", _freeze(self.expected))
        object.__setattr__(self, "observed", _freeze(self.observed))
        canonical_json({"expected": self.expected, "observed": self.observed})

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "passed": self.passed,
            "expected": _thaw(self.expected),
            "observed": _thaw(self.observed),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> CorrectnessResult:
        fields = frozenset({"id", "passed", "expected", "observed"})
        _strict_keys(raw, allowed=fields, required=fields, label="correctness result")
        return cls(
            _id(raw["id"], "correctness id"),
            raw["passed"] if isinstance(raw["passed"], bool) else _raise("passed must be bool"),
            raw["expected"],
            raw["observed"],
        )


@dataclass(frozen=True, slots=True)
class ComparisonEvidence:
    benchmark_key: tuple[str, int, str, str, str, int, int]
    baseline_record_id: str
    decision: str
    baseline_estimate: Decimal
    candidate_estimate: Decimal
    change: Decimal | None
    threshold: Decimal | None
    transform: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_key", _benchmark_key(self.benchmark_key))
        _digest(self.baseline_record_id, "baseline record id")
        if self.decision not in {"pass", "regression", "inconclusive", "absolute-failure"}:
            raise RecordError("comparison decision is unsupported")
        object.__setattr__(
            self, "baseline_estimate", _decimal(self.baseline_estimate, "baseline estimate")
        )
        object.__setattr__(
            self, "candidate_estimate", _decimal(self.candidate_estimate, "candidate estimate")
        )
        if self.change is not None:
            object.__setattr__(self, "change", _decimal(self.change, "comparison change"))
        if self.threshold is not None:
            object.__setattr__(self, "threshold", _decimal(self.threshold, "comparison threshold"))
        if self.transform not in {"ratio", "absolute", "positive-offset-ratio"}:
            raise RecordError("comparison transform is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_key": list(self.benchmark_key),
            "baseline_record_id": self.baseline_record_id,
            "decision": self.decision,
            "baseline_estimate": self.baseline_estimate,
            "candidate_estimate": self.candidate_estimate,
            "change": self.change,
            "threshold": self.threshold,
            "transform": self.transform,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ComparisonEvidence:
        fields = frozenset(
            {
                "benchmark_key",
                "baseline_record_id",
                "decision",
                "baseline_estimate",
                "candidate_estimate",
                "change",
                "threshold",
                "transform",
            }
        )
        _strict_keys(raw, allowed=fields, required=fields, label="comparison evidence")
        return cls(
            _benchmark_key(raw["benchmark_key"], strict_digest=True),
            _digest(raw["baseline_record_id"], "baseline record id", strict=True),
            _text(raw["decision"], "comparison decision"),
            _decimal(raw["baseline_estimate"], "baseline estimate"),
            _decimal(raw["candidate_estimate"], "candidate estimate"),
            _decimal(raw["change"], "comparison change") if raw["change"] is not None else None,
            _decimal(raw["threshold"], "comparison threshold")
            if raw["threshold"] is not None
            else None,
            _text(raw["transform"], "comparison transform"),
        )


@dataclass(frozen=True, slots=True)
class Invalidation:
    phase: str
    reason: str
    fatal: bool = True

    def __post_init__(self) -> None:
        _id(self.phase, "invalidation phase")
        _text(self.reason, "invalidation reason")
        if not isinstance(self.fatal, bool):
            raise RecordError("invalidation fatal value must be a boolean")

    def to_dict(self) -> dict[str, object]:
        return {"phase": self.phase, "reason": self.reason, "fatal": self.fatal}

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> Invalidation:
        fields = frozenset({"phase", "reason", "fatal"})
        _strict_keys(
            raw,
            allowed=fields,
            required=fields - frozenset({"fatal"}),
            label="invalidation",
        )
        fatal = raw.get("fatal", True)
        return cls(
            _id(raw["phase"], "invalidation phase"),
            _text(raw["reason"], "invalidation reason"),
            fatal if isinstance(fatal, bool) else _raise("invalidation fatal must be bool"),
        )


def _coerce_items(value: object, item_type: type[Any], label: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise RecordError(f"{label} must be a list")
    result: list[Any] = []
    for item in value:
        if isinstance(item, item_type):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(item_type.from_mapping(item))
        else:
            raise RecordError(f"{label} contains an invalid item")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    """Append-only suite record whose id hashes every non-id field."""

    fingerprint: ComparisonFingerprint
    provenance: Provenance
    suite_id: str
    suite_version: int
    catalog_digest: str
    metrics: tuple[MetricResult, ...]
    run_conditions: Mapping[str, object]
    schema_version: int = RECORD_SCHEMA_VERSION
    capabilities: tuple[CapabilityResult, ...] = ()
    correctness: tuple[CorrectnessResult, ...] = ()
    comparisons: tuple[ComparisonEvidence, ...] = ()
    invalidations: tuple[Invalidation, ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    record_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != RECORD_SCHEMA_VERSION:
            raise RecordError(
                f"unsupported record schema version {self.schema_version}; "
                f"expected {RECORD_SCHEMA_VERSION}"
            )
        _id(self.suite_id, "suite id")
        _positive_integer(self.suite_version, "suite version")
        _digest(self.catalog_digest, "catalog digest")
        if not isinstance(self.fingerprint, ComparisonFingerprint):
            raise RecordError("record fingerprint has the wrong type")
        if not isinstance(self.provenance, Provenance):
            raise RecordError("record provenance has the wrong type")
        metrics = _coerce_items(self.metrics, MetricResult, "metrics")
        if not metrics:
            raise RecordError("record requires one or more metric results")
        if any(metric.benchmark_key[-1] != self.suite_version for metric in metrics):
            raise RecordError("metric benchmark key suite version does not match record")
        keys = [metric.benchmark_key for metric in metrics]
        if len(set(keys)) != len(keys):
            raise RecordError("record contains duplicate metric benchmark keys")
        if any(not metric.correctness_passed for metric in metrics):
            raise RecordError("benchmark records require correctness to pass before timing")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(
            self, "capabilities", _coerce_items(self.capabilities, CapabilityResult, "capabilities")
        )
        object.__setattr__(
            self, "correctness", _coerce_items(self.correctness, CorrectnessResult, "correctness")
        )
        object.__setattr__(
            self, "comparisons", _coerce_items(self.comparisons, ComparisonEvidence, "comparisons")
        )
        object.__setattr__(
            self, "invalidations", _coerce_items(self.invalidations, Invalidation, "invalidations")
        )
        if any(result.required and not result.available for result in self.capabilities):
            raise RecordError("benchmark record cannot contain an unavailable required capability")
        if any(not result.passed for result in self.correctness):
            raise RecordError("benchmark record cannot contain a failed correctness check")
        object.__setattr__(
            self, "run_conditions", _frozen_mapping(self.run_conditions, "run conditions")
        )
        object.__setattr__(self, "diagnostics", _frozen_mapping(self.diagnostics, "diagnostics"))
        object.__setattr__(self, "record_id", content_hash(self.payload()))

    @property
    def primary_key(self) -> tuple[str, str, str, int]:
        return (
            self.provenance.subject_commit,
            self.fingerprint.id,
            self.suite_id,
            self.suite_version,
        )

    @property
    def expected_path(self) -> str:
        subject, fingerprint, suite, version = self.primary_key
        return f"records/v1/{fingerprint}/{subject}/{suite}@{version}.json"

    def payload(self) -> dict[str, object]:
        run_conditions = _thaw(self.run_conditions)
        diagnostics = _thaw(self.diagnostics)
        assert isinstance(run_conditions, dict) and isinstance(diagnostics, dict)
        return {
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint.to_dict(),
            "provenance": self.provenance.to_dict(),
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "catalog_digest": self.catalog_digest,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "capabilities": [item.to_dict() for item in self.capabilities],
            "correctness": [item.to_dict() for item in self.correctness],
            "comparisons": [item.to_dict() for item in self.comparisons],
            "invalidations": [item.to_dict() for item in self.invalidations],
            "diagnostics": diagnostics,
            "run_conditions": run_conditions,
        }

    def to_dict(self) -> dict[str, object]:
        data = self.payload()
        data["record_id"] = self.record_id
        return data

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, object], *, expected_path: str | None = None
    ) -> BenchmarkRecord:
        required = frozenset(
            {
                "schema_version",
                "fingerprint",
                "provenance",
                "suite_id",
                "suite_version",
                "catalog_digest",
                "metrics",
                "run_conditions",
                "record_id",
            }
        )
        optional = frozenset(
            {"capabilities", "correctness", "comparisons", "invalidations", "diagnostics"}
        )
        _strict_keys(raw, allowed=required | optional, required=required, label="benchmark record")
        fingerprint = raw["fingerprint"]
        provenance = raw["provenance"]
        metrics = raw["metrics"]
        run_conditions = raw["run_conditions"]
        if not isinstance(fingerprint, Mapping) or not isinstance(provenance, Mapping):
            raise RecordError("record fingerprint and provenance must be objects")
        if not isinstance(metrics, list) or not isinstance(run_conditions, Mapping):
            raise RecordError("record metrics must be a list and run_conditions an object")
        diagnostics = raw.get("diagnostics", {})
        if not isinstance(diagnostics, Mapping):
            raise RecordError("record diagnostics must be an object")
        record = cls(
            ComparisonFingerprint.from_mapping(fingerprint),
            Provenance.from_mapping(provenance),
            _id(raw["suite_id"], "suite id"),
            _positive_integer(raw["suite_version"], "suite version"),
            _digest(raw["catalog_digest"], "catalog digest", strict=True),
            tuple(
                MetricResult.from_mapping(item)
                if isinstance(item, Mapping)
                else _raise("record metrics must contain objects")
                for item in metrics
            ),
            run_conditions,
            _positive_integer(raw["schema_version"], "record schema_version"),
            _coerce_items(raw.get("capabilities", []), CapabilityResult, "capabilities"),
            _coerce_items(raw.get("correctness", []), CorrectnessResult, "correctness"),
            _coerce_items(raw.get("comparisons", []), ComparisonEvidence, "comparisons"),
            _coerce_items(raw.get("invalidations", []), Invalidation, "invalidations"),
            diagnostics,
        )
        if raw["record_id"] != record.record_id:
            raise RecordError("record_id does not match canonical record content")
        if expected_path is not None and expected_path != record.expected_path:
            raise RecordError("record path does not match its primary key")
        return record


def parse_benchmark_record(
    payload: bytes | str, *, expected_path: str | None = None
) -> BenchmarkRecord:
    """Parse canonical JSON into a verified record, optionally checking its shard path."""

    parsed = canonical_json_loads(payload)
    if not isinstance(parsed, Mapping):
        raise RecordError("benchmark record JSON must contain an object")
    if expected_path is not None:
        path = PurePosixPath(expected_path)
        if path.is_absolute() or ".." in path.parts:
            raise RecordError("record path must be a canonical relative POSIX path")
    return BenchmarkRecord.from_mapping(parsed, expected_path=expected_path)
