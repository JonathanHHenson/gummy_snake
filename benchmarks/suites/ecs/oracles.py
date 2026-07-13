"""Deterministic correctness digests and fail-closed ECS path assertions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from numbers import Real
from typing import Any


class EcsOracleError(AssertionError):
    """A workload completed with incorrect state or an unexpected runtime path."""


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


def require_counter_minimums(
    diagnostics: Mapping[str, object], minimums: Mapping[str, int]
) -> None:
    """Fail when a workload did not execute every declared production path."""

    require_counters(diagnostics, minimums)
    for name, minimum in minimums.items():
        value = diagnostics[name]
        assert isinstance(value, Real) and not isinstance(value, bool)
        if value < minimum:
            raise EcsOracleError(f"ECS counter {name} expected at least {minimum}, got {value}")


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise a digest-friendly assertion with one stable correctness label."""

    if actual != expected:
        raise EcsOracleError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def entity_rows(
    world: Any, component_type: type[Any], *field_names: str
) -> tuple[tuple[Any, ...], ...]:
    """Read dense component fields through the public Rust-backed batch API."""

    return tuple(world.iter_component_fields(component_type, *field_names))
