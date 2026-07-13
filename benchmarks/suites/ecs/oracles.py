"""Deterministic correctness digests and fail-closed ECS path assertions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
from numbers import Real
from typing import Any


class EcsOracleError(AssertionError):
    """A workload completed with incorrect state or an unexpected runtime path."""


@dataclass(frozen=True, slots=True)
class EcsStateDigest:
    """Canonical, allocation-independent observable state for one ECS workload.

    The benchmark owns the explicit ``observable`` value, while the Rust-backed
    world contributes only public diagnostics.  This makes correctness checks
    include entity generations, component/tag/resource/event rows supplied by the
    workload without depending on private storage addresses or Python mirrors.
    """

    alive_entities: int
    structural_revision: int | None
    field_revision: int | None
    change_epoch: int | None
    observable: object
    selected_diagnostics: Mapping[str, object]

    def digest(self) -> str:
        """Return the stable digest used as a benchmark correctness oracle."""

        return correctness_digest(self)


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


def assert_path_counters(
    diagnostics: Mapping[str, object], expectations: Iterable[CounterExpectation]
) -> None:
    """Require exact, minimum, and maximum path counters without substitutes.

    This is intentionally suitable for no-materialization and no-recompile
    assertions: an ``exact=0`` contract fails if any Python boundary path was
    selected unexpectedly.
    """

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


def world_state_digest(world: Any, observable: object) -> EcsStateDigest:
    """Capture the canonical public world state surrounding a benchmark result.

    The workload must supply complete observable rows for the component/tag,
    resource, event, and spatial semantics it exercises.  The facade supplies
    only public Rust-backed diagnostics; no private component-column inspection
    is performed.
    """

    diagnostics = world.diagnostics()
    alive = diagnostics.get("ecs_entities_alive")
    if isinstance(alive, bool) or not isinstance(alive, int) or alive < 0:
        raise EcsOracleError("ECS state digest requires non-negative ecs_entities_alive")
    selected_names = (
        "ecs_entities_alive",
        "ecs_rust_entities_alive",
        "ecs_rust_structural_revision",
        "ecs_rust_field_revision",
        "ecs_change_journal_retained_records",
        "ecs_change_journal_updates",
        "ecs_event_records_read",
        "ecs_spatial_candidate_rows",
        "ecs_spatial_exact_rows",
    )
    selected = {name: diagnostics[name] for name in selected_names if name in diagnostics}
    for name, value in selected.items():
        if isinstance(value, bool) or not isinstance(value, Real):
            raise EcsOracleError(f"ECS state digest counter {name} must be numeric")
    epoch = diagnostics.get("ecs_change_epoch")
    if epoch is not None and (isinstance(epoch, bool) or not isinstance(epoch, int)):
        raise EcsOracleError("ecs_change_epoch must be an integer when reported")
    structural = diagnostics.get("ecs_rust_structural_revision")
    field = diagnostics.get("ecs_rust_field_revision")
    if structural is not None and (isinstance(structural, bool) or not isinstance(structural, int)):
        raise EcsOracleError("ecs_rust_structural_revision must be an integer when reported")
    if field is not None and (isinstance(field, bool) or not isinstance(field, int)):
        raise EcsOracleError("ecs_rust_field_revision must be an integer when reported")
    return EcsStateDigest(
        alive_entities=alive,
        structural_revision=structural,
        field_revision=field,
        change_epoch=epoch,
        observable=_canonical(observable),
        selected_diagnostics=selected,
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
