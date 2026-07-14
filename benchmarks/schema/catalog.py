"""Strict static catalog parsing, metric semantics, and definition auditing."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from ..governance import ExecutionClass
from .canonical import CanonicalJsonError, canonical_json, content_hash, file_hash

CATALOG_SCHEMA_VERSION = 1
_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class CatalogError(ValueError):
    """A catalog is malformed, dynamic, or has incomparable metric semantics."""


class Direction(StrEnum):
    LOWER_IS_BETTER = "lower-is-better"
    HIGHER_IS_BETTER = "higher-is-better"


class PercentageTransform(StrEnum):
    RATIO = "ratio"
    ABSOLUTE = "absolute"
    POSITIVE_OFFSET_RATIO = "positive-offset-ratio"


class ZeroPolicy(StrEnum):
    POSITIVE_BASELINE = "positive-baseline"
    ZERO_TOLERANCE = "zero-tolerance"
    EXPLICIT_TRANSFORM = "explicit-transform"
    ABSOLUTE_GATE = "absolute-gate"


class MetricDomain(StrEnum):
    NON_NEGATIVE = "non-negative"
    POSITIVE = "positive"
    SIGNED = "signed"


@dataclass(frozen=True, slots=True)
class VersioningRules:
    """Changes that require a reviewed identity/version bump."""

    schema: tuple[str, ...] = (
        "canonical encoding or validation meaning",
        "record, catalog, or fingerprint field meaning",
    )
    suite: tuple[str, ...] = (
        "suite membership or gate family",
        "suite-wide statistics or sampling policy",
    )
    benchmark: tuple[str, ...] = (
        "workload implementation or work-unit meaning",
        "capability, correctness, or execution-route meaning",
    )
    case: tuple[str, ...] = ("case setup, parameters, fixture, or expected outcome",)
    metric: tuple[str, ...] = (
        "unit, normalization, direction, transform, domain, precision, or aggregation",
    )
    statistics_policy: tuple[str, ...] = (
        "estimator, confidence method, family correction, or decision threshold",
    )


VERSIONING_RULES = VersioningRules()


def _strict_keys(
    raw: Mapping[str, object], *, allowed: frozenset[str], required: frozenset[str], label: str
) -> None:
    unknown = sorted(set(raw) - allowed)
    missing = sorted(required - set(raw))
    if unknown:
        raise CatalogError(f"{label} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise CatalogError(f"{label} is missing required field(s): {', '.join(missing)}")


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CatalogError(f"{label} must match {_ID.pattern}")
    return value


def _version(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CatalogError(f"{label} must be a positive integer")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogError(f"{label} must be an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CatalogError(f"{label} must be a boolean")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CatalogError(f"{label} must be a non-empty normalized string")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise CatalogError(f"{label} must be an integer or decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise CatalogError(f"{label} is not a decimal") from error
    if not result.is_finite():
        raise CatalogError(f"{label} must be finite")
    return result


def _string_list(
    value: object, label: str, *, identities: bool = False, require_nonempty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogError(f"{label} must be a list")
    converted = tuple(
        _id(item, f"{label} item") if identities else _text(item, f"{label} item") for item in value
    )
    if require_nonempty and not converted:
        raise CatalogError(f"{label} must not be empty")
    if len(set(converted)) != len(converted):
        raise CatalogError(f"{label} must not contain duplicates")
    return converted


def _runtime_parameters(raw: Mapping[str, object]) -> Mapping[str, object]:
    """Validate immutable values passed unchanged to a workload dispatcher."""

    matrix_keys = sorted(key for key in raw if key.endswith("_matrix"))
    if matrix_keys:
        names = ", ".join(repr(key) for key in matrix_keys)
        raise CatalogError(
            "workload parameters must contain only dispatched runtime values; "
            f"remove matrix parameter(s) {names} and declare a separate workload for each value"
        )
    try:
        canonical_json(raw)
    except CanonicalJsonError as error:
        raise CatalogError(f"parameters are not canonical data: {error}") from error
    return MappingProxyType(dict(raw))


@dataclass(frozen=True, slots=True)
class MetricSpec:
    id: str
    version: int
    unit: str
    work_unit: str
    direction: Direction
    transform: PercentageTransform
    zero_policy: ZeroPolicy
    precision: int
    aggregation: str = "median-of-process-medians"
    valid_domain: MetricDomain | None = None
    requires_positive_baseline: bool | None = None
    absolute_limit: Decimal | None = None
    transform_offset: Decimal | None = None

    def __post_init__(self) -> None:
        _id(self.id, "metric id")
        _version(self.version, "metric version")
        _text(self.unit, "metric unit")
        _id(self.work_unit, "metric work_unit")
        _id(self.aggregation, "metric aggregation")
        if isinstance(self.direction, str):
            object.__setattr__(self, "direction", Direction(self.direction))
        if isinstance(self.transform, str):
            object.__setattr__(self, "transform", PercentageTransform(self.transform))
        if isinstance(self.zero_policy, str):
            object.__setattr__(self, "zero_policy", ZeroPolicy(self.zero_policy))
        if (
            isinstance(self.precision, bool)
            or not isinstance(self.precision, int)
            or self.precision < 0
        ):
            raise CatalogError("metric precision must be a non-negative integer")

        domain = self.valid_domain
        if domain is None:
            domain = (
                MetricDomain.SIGNED
                if self.zero_policy in (ZeroPolicy.EXPLICIT_TRANSFORM, ZeroPolicy.ABSOLUTE_GATE)
                else MetricDomain.NON_NEGATIVE
            )
            object.__setattr__(self, "valid_domain", domain)
        elif isinstance(domain, str):
            domain = MetricDomain(domain)
            object.__setattr__(self, "valid_domain", domain)

        positive = self.requires_positive_baseline
        if positive is None:
            positive = self.transform in (
                PercentageTransform.RATIO,
                PercentageTransform.POSITIVE_OFFSET_RATIO,
            )
            object.__setattr__(self, "requires_positive_baseline", positive)

        if self.transform is PercentageTransform.RATIO:
            if self.zero_policy is ZeroPolicy.ZERO_TOLERANCE:
                raise CatalogError("zero-tolerance metrics must use the absolute transform")
            if self.zero_policy is not ZeroPolicy.POSITIVE_BASELINE or not positive:
                raise CatalogError("ratio metrics require positive-baseline policy and denominator")
            if domain is MetricDomain.SIGNED:
                raise CatalogError("signed metrics cannot inherit the generic ratio gate")
            if self.absolute_limit is not None or self.transform_offset is not None:
                raise CatalogError("generic ratio metrics cannot declare absolute_limit or offset")
        elif self.transform is PercentageTransform.POSITIVE_OFFSET_RATIO:
            if self.zero_policy is not ZeroPolicy.EXPLICIT_TRANSFORM or not positive:
                raise CatalogError(
                    "positive-offset-ratio metrics require explicit-transform and a positive "
                    "denominator"
                )
            if self.transform_offset is None or self.transform_offset <= 0:
                raise CatalogError(
                    "positive-offset-ratio metrics require a positive transform_offset"
                )
            if self.absolute_limit is not None:
                raise CatalogError("transformed ratio metrics cannot declare absolute_limit")
        elif self.transform is PercentageTransform.ABSOLUTE:
            if positive:
                raise CatalogError("absolute metrics do not use a positive ratio denominator")
            if self.zero_policy is ZeroPolicy.ZERO_TOLERANCE:
                if domain is MetricDomain.SIGNED:
                    raise CatalogError("zero-tolerance counts must have a non-negative domain")
                if self.absolute_limit not in (None, Decimal(0)):
                    raise CatalogError(
                        "zero-tolerance metrics have an implicit absolute limit of zero"
                    )
                object.__setattr__(self, "absolute_limit", Decimal(0))
            elif self.zero_policy is ZeroPolicy.ABSOLUTE_GATE:
                if self.absolute_limit is None or self.absolute_limit < 0:
                    raise CatalogError(
                        "absolute-gate metrics require a non-negative absolute_limit"
                    )
            else:
                raise CatalogError(
                    "absolute metrics require zero-tolerance or absolute-gate policy"
                )
            if self.transform_offset is not None:
                raise CatalogError("absolute metrics cannot declare transform_offset")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> MetricSpec:
        allowed = frozenset(
            {
                "id",
                "version",
                "unit",
                "work_unit",
                "direction",
                "transform",
                "zero_policy",
                "precision",
                "aggregation",
                "valid_domain",
                "requires_positive_baseline",
                "absolute_limit",
                "transform_offset",
            }
        )
        required = frozenset(
            {"id", "version", "unit", "work_unit", "direction", "transform", "zero_policy"}
        )
        _strict_keys(raw, allowed=allowed, required=required, label="primary_metric")
        try:
            absolute = raw.get("absolute_limit")
            offset = raw.get("transform_offset")
            positive = raw.get("requires_positive_baseline")
            domain = raw.get("valid_domain")
            return cls(
                id=_id(raw["id"], "metric id"),
                version=_version(raw["version"], "metric version"),
                unit=_text(raw["unit"], "metric unit"),
                work_unit=_id(raw["work_unit"], "metric work_unit"),
                direction=Direction(_text(raw["direction"], "metric direction")),
                transform=PercentageTransform(_text(raw["transform"], "metric transform")),
                zero_policy=ZeroPolicy(_text(raw["zero_policy"], "metric zero_policy")),
                precision=_integer(raw.get("precision", 0), "metric precision"),
                aggregation=_id(
                    raw.get("aggregation", "median-of-process-medians"), "metric aggregation"
                ),
                valid_domain=MetricDomain(_text(domain, "metric valid_domain"))
                if domain is not None
                else None,
                requires_positive_baseline=_boolean(positive, "metric requires_positive_baseline")
                if positive is not None
                else None,
                absolute_limit=_decimal(absolute, "metric absolute_limit")
                if absolute is not None
                else None,
                transform_offset=_decimal(offset, "metric transform_offset")
                if offset is not None
                else None,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, CatalogError):
                raise
            raise CatalogError(f"invalid metric declaration: {error}") from error

    def to_dict(self) -> dict[str, object]:
        domain = self.valid_domain
        assert domain is not None
        return {
            "id": self.id,
            "version": self.version,
            "unit": self.unit,
            "work_unit": self.work_unit,
            "direction": self.direction.value,
            "transform": self.transform.value,
            "zero_policy": self.zero_policy.value,
            "precision": self.precision,
            "aggregation": self.aggregation,
            "valid_domain": domain.value,
            "requires_positive_baseline": self.requires_positive_baseline,
            "absolute_limit": self.absolute_limit,
            "transform_offset": self.transform_offset,
        }

    def validate_value(self, value: Decimal) -> None:
        if not value.is_finite():
            raise CatalogError("metric values must be finite")
        if self.valid_domain is MetricDomain.POSITIVE and value <= 0:
            raise CatalogError("metric value must be positive")
        if self.valid_domain is MetricDomain.NON_NEGATIVE and value < 0:
            raise CatalogError("metric value must be non-negative")

    def normalized(self, elapsed_ns: int, work: int) -> Decimal:
        if isinstance(elapsed_ns, bool) or not isinstance(elapsed_ns, int) or elapsed_ns < 0:
            raise CatalogError("elapsed nanoseconds must be a non-negative integer")
        if isinstance(work, bool) or not isinstance(work, int) or work <= 0:
            raise CatalogError("work must be a positive integer")
        result = Decimal(elapsed_ns) / Decimal(work)
        self.validate_value(result)
        return result

    def percentage_change(self, baseline: Decimal, candidate: Decimal) -> Decimal:
        self.validate_value(baseline)
        self.validate_value(candidate)
        if self.transform is PercentageTransform.RATIO:
            if baseline <= 0:
                raise CatalogError("percentage metric requires a strictly positive baseline")
            raw = candidate / baseline - Decimal(1)
        elif self.transform is PercentageTransform.POSITIVE_OFFSET_RATIO:
            assert self.transform_offset is not None
            baseline_denominator = baseline + self.transform_offset
            candidate_denominator = candidate + self.transform_offset
            if baseline_denominator <= 0 or candidate_denominator <= 0:
                raise CatalogError("transformed percentage metric requires positive denominators")
            raw = candidate_denominator / baseline_denominator - Decimal(1)
        else:
            raise CatalogError("absolute metric has no percentage change")
        return raw if self.direction is Direction.LOWER_IS_BETTER else -raw

    def absolute_gate_failed(self, candidate: Decimal) -> bool:
        if self.transform is not PercentageTransform.ABSOLUTE or self.absolute_limit is None:
            raise CatalogError("metric does not declare an absolute gate")
        self.validate_value(candidate)
        if self.zero_policy is ZeroPolicy.ZERO_TOLERANCE:
            return candidate != 0
        if self.direction is Direction.LOWER_IS_BETTER:
            return candidate > self.absolute_limit
        return candidate < self.absolute_limit


@dataclass(frozen=True, slots=True)
class CatalogEntryIdentity:
    suite_id: str
    suite_version: int
    benchmark_id: str
    benchmark_version: int
    case_id: str
    case_version: int
    parameter_digest: str
    parameter_version: int
    metric_id: str
    metric_version: int

    @property
    def key(self) -> tuple[str, int, str, int, str, int, str, int, str, int]:
        return (
            self.suite_id,
            self.suite_version,
            self.benchmark_id,
            self.benchmark_version,
            self.case_id,
            self.case_version,
            self.parameter_digest,
            self.parameter_version,
            self.metric_id,
            self.metric_version,
        )


@dataclass(frozen=True, slots=True)
class Workload:
    suite_id: str
    suite_version: int
    id: str
    version: int
    case_id: str
    parameters: Mapping[str, object]
    execution_class: ExecutionClass
    capabilities: tuple[str, ...]
    correctness: str
    sampling_profile: str
    primary_metric: MetricSpec
    source_files: tuple[str, ...]
    definition_digest: str
    case_version: int = 1
    parameter_version: int = 1
    _definition_entry: Mapping[str, object] = field(repr=False, compare=False, default_factory=dict)

    @property
    def parameter_digest(self) -> str:
        return content_hash(dict(self.parameters))

    @property
    def identity(self) -> CatalogEntryIdentity:
        return CatalogEntryIdentity(
            self.suite_id,
            self.suite_version,
            self.id,
            self.version,
            self.case_id,
            self.case_version,
            self.parameter_digest,
            self.parameter_version,
            self.primary_metric.id,
            self.primary_metric.version,
        )

    @property
    def versioned_key(self) -> tuple[str, int, str, int, str, int, str, int, str, int]:
        return self.identity.key

    @property
    def key(self) -> tuple[str, int, str, str, str, int, int]:
        return (
            self.id,
            self.version,
            self.case_id,
            self.parameter_digest,
            self.primary_metric.id,
            self.primary_metric.version,
            self.suite_version,
        )


@dataclass(frozen=True, slots=True)
class Catalog:
    path: Path
    schema_version: int
    workloads: tuple[Workload, ...]
    digest: str
    _by_suite: Mapping[tuple[str, int], tuple[Workload, ...]] = field(repr=False)

    def suite(self, suite_id: str, suite_version: int) -> tuple[Workload, ...]:
        return self._by_suite.get((suite_id, suite_version), ())

    def workload_files(self) -> tuple[str, ...]:
        return tuple(
            sorted({source for workload in self.workloads for source in workload.source_files})
        )

    def audit_definitions(self) -> None:
        """Fail if a catalog entry or declared workload file changed after loading."""

        for workload in self.workloads:
            actual = _digest_workload(
                self.path.parent, workload._definition_entry, workload.source_files
            )
            if actual != workload.definition_digest:
                raise CatalogError(
                    f"definition digest mismatch for {workload.id}:{workload.case_id}; "
                    "bump the affected version and refresh the reviewed catalog digest"
                )


def _source_path(root: Path, relative: str) -> Path:
    if "\\" in relative:
        raise CatalogError(f"declared workload path must use POSIX separators: {relative}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise CatalogError(f"declared workload file escapes or is not canonical: {relative}")
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise CatalogError(f"declared workload file escapes catalog root: {relative}") from error
    if not candidate.is_file():
        raise CatalogError(f"declared workload file does not exist: {relative}")
    return candidate


def _digest_workload(root: Path, raw: Mapping[str, object], source_files: tuple[str, ...]) -> str:
    declared = {relative: file_hash(_source_path(root, relative)) for relative in source_files}
    entry = dict(raw)
    entry.pop("definition_digest", None)
    return content_hash({"entry": entry, "files": declared})


def _workload(root: Path, raw: Mapping[str, object], suite_id: str, suite_version: int) -> Workload:
    if "dynamic_discovery" in raw:
        raise CatalogError("dynamic workload discovery is forbidden")
    allowed = frozenset(
        {
            "id",
            "version",
            "case_id",
            "case_version",
            "parameters",
            "parameter_version",
            "execution_class",
            "capabilities",
            "correctness",
            "sampling_profile",
            "primary_metric",
            "source_files",
            "definition_digest",
        }
    )
    required = allowed - frozenset(
        {"parameters", "case_version", "parameter_version", "definition_digest"}
    )
    _strict_keys(raw, allowed=allowed, required=required, label="workload")
    try:
        source_files = _string_list(raw["source_files"], "source_files", require_nonempty=True)
        for relative in source_files:
            _source_path(root, relative)
        metric_raw = raw["primary_metric"]
        if not isinstance(metric_raw, Mapping):
            raise CatalogError("primary_metric must be a TOML table")
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise CatalogError("parameters must be a TOML table")
        digest = _digest_workload(root, raw, source_files)
        declared_digest = raw.get("definition_digest")
        if declared_digest is not None:
            if not isinstance(declared_digest, str) or not _DIGEST.fullmatch(declared_digest):
                raise CatalogError("definition_digest must be a lowercase SHA-256 digest")
            if declared_digest != digest:
                raise CatalogError(
                    "declared definition_digest does not match entry and workload files"
                )
        execution_class = ExecutionClass(_text(raw["execution_class"], "execution_class"))
        return Workload(
            suite_id=suite_id,
            suite_version=suite_version,
            id=_id(raw["id"], "workload id"),
            version=_version(raw["version"], "workload version"),
            case_id=_id(raw["case_id"], "case id"),
            parameters=_runtime_parameters(parameters),
            execution_class=execution_class,
            capabilities=_string_list(
                raw["capabilities"],
                "capabilities",
                identities=True,
                require_nonempty=True,
            ),
            correctness=_id(raw["correctness"], "correctness identity"),
            sampling_profile=_id(raw["sampling_profile"], "sampling profile identity"),
            primary_metric=MetricSpec.from_mapping(metric_raw),
            source_files=tuple(sorted(source_files)),
            definition_digest=digest,
            case_version=_version(raw.get("case_version", 1), "case version"),
            parameter_version=_version(raw.get("parameter_version", 1), "parameter version"),
            _definition_entry=MappingProxyType(dict(raw)),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, CatalogError):
            raise
        raise CatalogError(f"invalid workload declaration: {error}") from error


def load_catalog(path: Path) -> Catalog:
    """Load one static TOML catalog; filesystem discovery is intentionally absent."""

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CatalogError(f"cannot load catalog {path}: {error}") from error
    _strict_keys(
        raw,
        allowed=frozenset({"schema_version", "suite", "workloads"}),
        required=frozenset({"schema_version", "suite", "workloads"}),
        label="catalog",
    )
    schema_version = _version(raw["schema_version"], "catalog schema_version")
    if schema_version != CATALOG_SCHEMA_VERSION:
        raise CatalogError(
            f"unsupported catalog schema version {schema_version}; "
            f"expected {CATALOG_SCHEMA_VERSION}"
        )
    suite = raw["suite"]
    workloads_raw = raw["workloads"]
    if not isinstance(suite, Mapping) or not isinstance(workloads_raw, list):
        raise CatalogError("catalog requires [suite] and [[workloads]] declarations")
    _strict_keys(
        suite,
        allowed=frozenset({"id", "version"}),
        required=frozenset({"id", "version"}),
        label="suite",
    )
    suite_id = _id(suite["id"], "suite id")
    suite_version = _version(suite["version"], "suite version")
    if not all(isinstance(item, Mapping) for item in workloads_raw) or not workloads_raw:
        raise CatalogError("catalog must contain one or more workload tables")
    workloads = tuple(
        _workload(path.parent, item, suite_id, suite_version) for item in workloads_raw
    )
    keys = [workload.versioned_key for workload in workloads]
    if len(set(keys)) != len(keys):
        raise CatalogError("catalog contains duplicate benchmark keys")
    by_suite = MappingProxyType({(suite_id, suite_version): workloads})
    digest = content_hash(
        {
            "schema_version": schema_version,
            "workloads": [item.definition_digest for item in workloads],
        }
    )
    return Catalog(
        path=path,
        schema_version=schema_version,
        workloads=workloads,
        digest=digest,
        _by_suite=by_suite,
    )
