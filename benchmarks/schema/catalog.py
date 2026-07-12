"""Static TOML catalog parsing and metric validity rules."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from ..governance import ExecutionClass
from .canonical import content_hash, file_hash

_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_VERSION = re.compile(r"^[1-9][0-9]*$")


class CatalogError(ValueError):
    """A catalog is malformed, dynamic, or has incomparable metric semantics."""


class Direction(StrEnum):
    LOWER_IS_BETTER = "lower-is-better"
    HIGHER_IS_BETTER = "higher-is-better"


class PercentageTransform(StrEnum):
    RATIO = "ratio"
    ABSOLUTE = "absolute"


class ZeroPolicy(StrEnum):
    POSITIVE_BASELINE = "positive-baseline"
    ZERO_TOLERANCE = "zero-tolerance"
    EXPLICIT_TRANSFORM = "explicit-transform"


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


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise CatalogError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _runtime_parameters(raw: Mapping[str, object]) -> dict[str, object]:
    """Validate values passed unchanged to a workload dispatcher."""

    matrix_keys = sorted(key for key in raw if key.endswith("_matrix"))
    if matrix_keys:
        names = ", ".join(repr(key) for key in matrix_keys)
        raise CatalogError(
            "workload parameters must contain only dispatched runtime values; "
            f"remove matrix parameter(s) {names} and declare a separate workload for each value"
        )
    return dict(raw)


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

    def __post_init__(self) -> None:
        _id(self.id, "metric id")
        _version(self.version, "metric version")
        if not self.unit or not self.work_unit or not self.aggregation:
            raise CatalogError("metric unit, work_unit, and aggregation are required")
        if self.precision < 0:
            raise CatalogError("metric precision must be non-negative")
        if (
            self.zero_policy is ZeroPolicy.ZERO_TOLERANCE
            and self.transform is not PercentageTransform.ABSOLUTE
        ):
            raise CatalogError("zero-tolerance metrics must use the absolute transform")
        if (
            self.zero_policy is not ZeroPolicy.ZERO_TOLERANCE
            and self.transform is PercentageTransform.ABSOLUTE
        ):
            raise CatalogError("absolute metrics require zero-tolerance policy")
        if self.zero_policy is ZeroPolicy.EXPLICIT_TRANSFORM:
            raise CatalogError(
                "explicit stable transforms require a schema extension, not the generic ratio gate"
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> MetricSpec:
        try:
            return cls(
                id=_id(raw["id"], "metric id"),
                version=_version(raw["version"], "metric version"),
                unit=str(raw["unit"]),
                work_unit=str(raw["work_unit"]),
                direction=Direction(str(raw["direction"])),
                transform=PercentageTransform(str(raw["transform"])),
                zero_policy=ZeroPolicy(str(raw["zero_policy"])),
                precision=_integer(raw.get("precision", 0), "metric precision"),
                aggregation=str(raw.get("aggregation", "median-of-process-medians")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CatalogError(f"invalid metric declaration: {error}") from error

    def normalized(self, elapsed_ns: int, work: int) -> Decimal:
        if elapsed_ns < 0 or work <= 0:
            raise CatalogError("elapsed nanoseconds must be non-negative and work must be positive")
        return Decimal(elapsed_ns) / Decimal(work)

    def percentage_change(self, baseline: Decimal, candidate: Decimal) -> Decimal:
        if self.transform is not PercentageTransform.RATIO:
            raise CatalogError("absolute metric has no percentage change")
        if baseline <= 0:
            raise CatalogError("percentage metric requires a strictly positive baseline")
        raw = candidate / baseline - Decimal(1)
        return raw if self.direction is Direction.LOWER_IS_BETTER else -raw


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

    @property
    def parameter_digest(self) -> str:
        return content_hash(dict(self.parameters))

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


def _digest_workload(root: Path, raw: Mapping[str, object], source_files: tuple[str, ...]) -> str:
    declared: dict[str, str] = {}
    for relative in source_files:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise CatalogError(f"declared workload file escapes catalog root: {relative}")
        candidate = root / relative_path
        if not candidate.is_file():
            raise CatalogError(f"declared workload file does not exist: {relative}")
        declared[relative] = file_hash(candidate)
    return content_hash({"entry": dict(raw), "files": declared})


def _workload(root: Path, raw: Mapping[str, object], suite_id: str, suite_version: int) -> Workload:
    if raw.get("dynamic_discovery") is True:
        raise CatalogError("dynamic authoritative workload discovery is forbidden")
    try:
        source_files = _string_list(raw["source_files"], "source_files")
        metric_raw = raw["primary_metric"]
        if not isinstance(metric_raw, Mapping):
            raise CatalogError("primary_metric must be a TOML table")
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise CatalogError("parameters must be a TOML table")
        return Workload(
            suite_id=suite_id,
            suite_version=suite_version,
            id=_id(raw["id"], "workload id"),
            version=_version(raw["version"], "workload version"),
            case_id=_id(raw["case_id"], "case id"),
            parameters=_runtime_parameters(parameters),
            execution_class=ExecutionClass(str(raw["execution_class"])),
            capabilities=_string_list(raw.get("capabilities", []), "capabilities"),
            correctness=str(raw["correctness"]),
            sampling_profile=str(raw["sampling_profile"]),
            primary_metric=MetricSpec.from_mapping(metric_raw),
            source_files=source_files,
            definition_digest=_digest_workload(root, raw, source_files),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, CatalogError):
            raise
        raise CatalogError(f"invalid workload declaration: {error}") from error


def load_catalog(path: Path) -> Catalog:
    """Load one static TOML catalog; filesystem discovery is intentionally absent."""

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CatalogError(f"cannot load catalog {path}: {error}") from error
    schema_version = _version(raw.get("schema_version"), "catalog schema_version")
    suite = raw.get("suite")
    workloads_raw = raw.get("workloads")
    if not isinstance(suite, Mapping) or not isinstance(workloads_raw, list):
        raise CatalogError("catalog requires [suite] and [[workloads]] declarations")
    suite_id = _id(suite.get("id"), "suite id")
    suite_version = _version(suite.get("version"), "suite version")
    workloads = tuple(
        _workload(path.parent, item, suite_id, suite_version)
        for item in workloads_raw
        if isinstance(item, Mapping)
    )
    if len(workloads) != len(workloads_raw) or not workloads:
        raise CatalogError("catalog must contain one or more workload tables")
    keys = [workload.key for workload in workloads]
    if len(set(keys)) != len(keys):
        raise CatalogError("catalog contains duplicate benchmark keys")
    by_suite = {(suite_id, suite_version): workloads}
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
