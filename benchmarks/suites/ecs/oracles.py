"""Deterministic correctness digests and fail-closed ECS path assertions."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
from numbers import Real
from typing import Any


class EcsOracleError(AssertionError):
    """A workload completed with incorrect state or an unexpected runtime path."""


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{7,64}$")
_WORLD_DIAGNOSTICS = (
    "ecs_entities_alive",
    "ecs_rust_entities_alive",
    "ecs_rust_structural_revision",
    "ecs_rust_field_revision",
    "ecs_change_epoch",
    "ecs_change_journal_retained_records",
    "ecs_change_journal_updates",
    "ecs_event_records_read",
    "ecs_physical_system_runs",
    "ecs_physical_rows_scanned",
    "ecs_physical_fields_written",
    "ecs_spatial_candidate_rows",
    "ecs_spatial_exact_rows",
)


@dataclass(frozen=True, slots=True)
class EcsStateDigest:
    """Canonical allocation-independent state captured through public ECS APIs.

    Entity rows include stable index/generation pairs, alive/dead state, all component
    snapshots requested by the workload, and membership in every requested tag. The
    resource/event sections preserve public values and event order. ``semantic_trace``
    records historical facts that are no longer present in the final world, such as
    cleared events and retired entity generations.
    """

    alive_entities: int
    structural_revision: int | None
    field_revision: int | None
    change_epoch: int | None
    entities: tuple[Mapping[str, object], ...]
    resources: Mapping[str, object]
    events: Mapping[str, object]
    semantic_trace: object
    selected_diagnostics: Mapping[str, object]
    schema_version: int = 1

    def digest(self) -> str:
        """Return the stable digest used as the benchmark correctness oracle."""

        return correctness_digest(self)


@dataclass(frozen=True, slots=True)
class FrameDigest:
    """Exact final-frame identity using top-left packed RGBA bytes."""

    width: int
    height: int
    pixel_bytes: int
    pixel_sha256: str
    schema_version: int = 1

    def digest(self) -> str:
        """Hash dimensions and exact pixel identity as one versioned frame oracle."""

        return correctness_digest(self)


@dataclass(frozen=True, slots=True)
class PixelRule:
    """An exact or bounded per-channel comparison rule for rendered frames."""

    max_channel_delta: int = 0
    max_different_channels: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("max_channel_delta", self.max_channel_delta),
            ("max_different_channels", self.max_different_channels),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_channel_delta > 255:
            raise ValueError("max_channel_delta cannot exceed 255")


@dataclass(frozen=True, slots=True)
class CounterExpectation:
    """One exact or bounded required runtime-path counter contract."""

    name: str
    minimum: int | float | None = None
    maximum: int | float | None = None
    exact: int | float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("counter expectation name must be non-empty")
        values = (self.minimum, self.maximum, self.exact)
        if any(isinstance(value, bool) for value in values if value is not None):
            raise ValueError("counter expectation bounds must be numeric, not boolean")
        if any(not isinstance(value, Real) for value in values if value is not None):
            raise ValueError("counter expectation bounds must be numeric")
        if self.exact is not None and (self.minimum is not None or self.maximum is not None):
            raise ValueError("exact counter expectations cannot also declare bounds")
        if (
            self.minimum is not None
            and self.maximum is not None
            and float(self.minimum) > float(self.maximum)
        ):
            raise ValueError("counter expectation minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class ReleaseProvenanceContract:
    """Authoritative ECS recording requirements enforced by the shared recorder."""

    profile: str = "release"
    required_features: tuple[str, ...] = ("extension-module",)

    def validate(self, reported: Mapping[str, object]) -> Mapping[str, object]:
        """Reject debug, unrecorded, malformed, or feature-incomplete native builds."""

        required = {
            "source_commit",
            "source_digest",
            "tree_digest",
            "profile",
            "features",
            "canvas_crate_version",
            "ecs_crate_version",
        }
        missing = sorted(required - set(reported))
        if missing:
            raise EcsOracleError(
                "authoritative ECS benchmark provenance is missing: " + ", ".join(missing)
            )
        commit = reported["source_commit"]
        if not isinstance(commit, str) or not _GIT_OBJECT.fullmatch(commit):
            raise EcsOracleError(
                "authoritative ECS benchmarks require a recorded hexadecimal source commit"
            )
        for name in ("source_digest", "tree_digest"):
            value = reported[name]
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise EcsOracleError(
                    f"authoritative ECS benchmarks require a recorded {name} SHA-256 digest"
                )
        if reported["profile"] != self.profile:
            raise EcsOracleError(
                f"authoritative ECS benchmarks require profile={self.profile!r}, "
                f"got {reported['profile']!r}"
            )
        features = reported["features"]
        if not isinstance(features, Sequence) or isinstance(features, str):
            raise EcsOracleError("native benchmark provenance features must be a sequence")
        normalized_features = tuple(str(feature) for feature in features)
        missing_features = sorted(set(self.required_features) - set(normalized_features))
        if missing_features:
            raise EcsOracleError(
                "authoritative ECS benchmark build is missing feature(s): "
                + ", ".join(missing_features)
            )
        for name in ("canvas_crate_version", "ecs_crate_version"):
            value = reported[name]
            if not isinstance(value, str) or not value.strip():
                raise EcsOracleError(f"native benchmark provenance {name} must be non-empty")
        return {key: _canonical(reported[key]) for key in sorted(required)}


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise EcsOracleError("correctness digest mappings must use string keys")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise EcsOracleError(f"unsupported correctness digest value: {type(value).__name__}")


def correctness_digest(value: object) -> str:
    """Return a stable allocation-independent digest for observable workload state."""

    encoded = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def require_counters(diagnostics: Mapping[str, object], required: Iterable[str]) -> None:
    """Require declared public diagnostics to exist and remain numeric."""

    for name in required:
        value = diagnostics.get(name)
        if isinstance(value, bool) or not isinstance(value, Real):
            raise EcsOracleError(f"required ECS counter unavailable or non-numeric: {name}")


def assert_diagnostic_values(
    diagnostics: Mapping[str, object], expected: Mapping[str, object]
) -> None:
    """Require exact scalar diagnostic identities, including non-numeric path markers."""

    for name, expected_value in expected.items():
        if name not in diagnostics:
            raise EcsOracleError(f"required ECS diagnostic unavailable: {name}")
        actual = diagnostics[name]
        if actual != expected_value:
            raise EcsOracleError(
                f"ECS diagnostic {name} expected exactly {expected_value!r}, got {actual!r}"
            )


def assert_path_counters(
    diagnostics: Mapping[str, object], expectations: Iterable[CounterExpectation]
) -> None:
    """Require exact, minimum, and maximum path counters without substitutes."""

    for expectation in expectations:
        require_counters(diagnostics, (expectation.name,))
        value = diagnostics[expectation.name]
        assert isinstance(value, Real) and not isinstance(value, bool)
        numeric_value = float(value)
        if expectation.exact is not None and numeric_value != float(expectation.exact):
            raise EcsOracleError(
                f"ECS counter {expectation.name} expected exactly {expectation.exact}, got {value}"
            )
        if expectation.minimum is not None and numeric_value < float(expectation.minimum):
            raise EcsOracleError(
                f"ECS counter {expectation.name} expected at least "
                f"{expectation.minimum}, got {value}"
            )
        if expectation.maximum is not None and numeric_value > float(expectation.maximum):
            raise EcsOracleError(
                f"ECS counter {expectation.name} expected at most "
                f"{expectation.maximum}, got {value}"
            )


def require_counter_minimums(
    diagnostics: Mapping[str, object], minimums: Mapping[str, int]
) -> None:
    """Fail when a workload did not execute every declared production path."""

    assert_path_counters(
        diagnostics,
        (CounterExpectation(name=name, minimum=minimum) for name, minimum in minimums.items()),
    )


def _handle_key(entity: object) -> tuple[int, int]:
    try:
        index = entity.index  # type: ignore[attr-defined]
        generation = entity.generation  # type: ignore[attr-defined]
    except AttributeError as error:
        raise EcsOracleError(
            "entity digest rows require public index/generation handles"
        ) from error
    if isinstance(index, bool) or not isinstance(index, int):
        raise EcsOracleError("entity index must be an integer")
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise EcsOracleError("entity generation must be an integer")
    return index, generation


def _type_name(value_type: type[Any]) -> str:
    return f"{value_type.__module__}.{value_type.__qualname__}"


def world_state_digest(
    world: Any,
    semantic_trace: object,
    *,
    component_types: Iterable[type[Any]] = (),
    tags: Iterable[str] = (),
    resource_types: Iterable[type[Any]] = (),
    event_types: Iterable[type[Any]] = (),
    dead_entities: Iterable[object] = (),
) -> EcsStateDigest:
    """Capture complete declared world state through public Rust-backed APIs.

    The caller declares the schemas/tags relevant to its generated fixture. This avoids
    private schema/storage inspection while ensuring every declared value is included.
    Dead generations cannot be enumerated publicly, so structural workloads supply the
    handles they retired and retain those facts in the digest.
    """

    entity_data: dict[tuple[int, int], dict[str, object]] = {}
    for view in world.iter_entities():
        key = _handle_key(view.entity)
        entity_data[key] = {
            "index": key[0],
            "generation": key[1],
            "alive": True,
            "components": {},
            "tags": [],
        }
    for component_type in component_types:
        name = _type_name(component_type)
        for view in world.iter_entities(component_type):
            key = _handle_key(view.entity)
            row = entity_data.get(key)
            if row is None:
                raise EcsOracleError(
                    "component query returned an entity absent from the world query"
                )
            components = row["components"]
            assert isinstance(components, dict)
            components[name] = world.component_snapshot(view.entity, component_type)
    for tag in tags:
        if not isinstance(tag, str) or not tag:
            raise EcsOracleError("world digest tags must be non-empty strings")
        for view in world.iter_entities(tags=[tag]):
            key = _handle_key(view.entity)
            row = entity_data.get(key)
            if row is None:
                raise EcsOracleError("tag query returned an entity absent from the world query")
            row_tags = row["tags"]
            assert isinstance(row_tags, list)
            row_tags.append(tag)
    for entity in dead_entities:
        key = _handle_key(entity)
        if key in entity_data:
            raise EcsOracleError("an entity generation cannot be both alive and dead in one digest")
        entity_data[key] = {
            "index": key[0],
            "generation": key[1],
            "alive": False,
            "components": {},
            "tags": [],
        }
    resources = {
        _type_name(resource_type): world.get_resource(resource_type).snapshot()
        for resource_type in resource_types
    }
    events = {
        _type_name(event_type): tuple(world.read_events(event_type)) for event_type in event_types
    }
    diagnostics = world.diagnostics()
    alive = diagnostics.get("ecs_entities_alive")
    if isinstance(alive, bool) or not isinstance(alive, int) or alive < 0:
        raise EcsOracleError("ECS state digest requires non-negative ecs_entities_alive")
    selected = {name: diagnostics.get(name) for name in _WORLD_DIAGNOSTICS}
    for name, value in selected.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, Real)):
            raise EcsOracleError(f"ECS state digest counter {name} must be numeric or unavailable")
    structural = selected["ecs_rust_structural_revision"]
    field = selected["ecs_rust_field_revision"]
    epoch = selected["ecs_change_epoch"]
    return EcsStateDigest(
        alive_entities=alive,
        structural_revision=int(structural) if structural is not None else None,
        field_revision=int(field) if field is not None else None,
        change_epoch=int(epoch) if epoch is not None else None,
        entities=tuple(entity_data[key] for key in sorted(entity_data)),
        resources=_canonical(resources),  # type: ignore[arg-type]
        events=_canonical(events),  # type: ignore[arg-type]
        semantic_trace=_canonical(semantic_trace),
        selected_diagnostics=selected,
    )


def frame_digest(pixels: bytes | bytearray | memoryview, width: int, height: int) -> FrameDigest:
    """Create an exact final-frame oracle from public top-left RGBA readback bytes."""

    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise EcsOracleError("frame digest width must be a positive integer")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise EcsOracleError("frame digest height must be a positive integer")
    payload = bytes(pixels)
    expected = width * height * 4
    if len(payload) != expected:
        raise EcsOracleError(f"frame digest expected {expected} RGBA bytes, got {len(payload)}")
    return FrameDigest(width, height, len(payload), "sha256:" + sha256(payload).hexdigest())


def assert_pixels(
    actual: bytes | bytearray | memoryview,
    expected: bytes | bytearray | memoryview,
    rule: PixelRule | None = None,
) -> None:
    """Apply the shared exact/tolerant per-channel rule to two packed RGBA buffers."""

    if rule is None:
        rule = PixelRule()
    actual_bytes = bytes(actual)
    expected_bytes = bytes(expected)
    if len(actual_bytes) != len(expected_bytes):
        raise EcsOracleError(
            "pixel buffers differ in length: "
            f"expected {len(expected_bytes)}, got {len(actual_bytes)}"
        )
    different = 0
    largest_delta = 0
    for left, right in zip(actual_bytes, expected_bytes, strict=True):
        delta = abs(left - right)
        if delta:
            different += 1
            largest_delta = max(largest_delta, delta)
    if largest_delta > rule.max_channel_delta or different > rule.max_different_channels:
        raise EcsOracleError(
            "pixel rule mismatch: "
            f"largest channel delta {largest_delta} (limit {rule.max_channel_delta}), "
            f"different channels {different} (limit {rule.max_different_channels})"
        )


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise a digest-friendly assertion with one stable correctness label."""

    if actual != expected:
        raise EcsOracleError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def entity_rows(
    world: Any, component_type: type[Any], *field_names: str
) -> tuple[tuple[Any, ...], ...]:
    """Read dense component fields through the public Rust-backed batch API."""

    return tuple(world.iter_component_fields(component_type, *field_names))
