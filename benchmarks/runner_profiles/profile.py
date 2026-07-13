"""Strict parsing and matching for versioned benchmark runner profiles."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

from ..schema.canonical import file_hash

_PROFILE_VERSION = 1
_PRIVATE_FIELD_TOKENS = frozenset(
    {
        "hostname",
        "host",
        "serial",
        "uuid",
        "mac",
        "macaddress",
        "mac_address",
        "machine_id",
        "machineid",
        "volume_id",
        "volumeid",
        "volume_uuid",
        "volumeuuid",
        "device_id",
        "deviceid",
        "user",
        "username",
        "home",
        "path",
        "mountpoint",
        "address",
        "ip",
        "free_memory",
        "temperature",
        "current_frequency",
        "load",
        "process_id",
        "pid",
        "timestamp",
    }
)


class RunnerProfileError(ValueError):
    """A runner profile is malformed, private, or incompatible with this host."""


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _private_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    parts = tuple(part for part in normalized.split("_") if part)
    return normalized in _PRIVATE_FIELD_TOKENS or any(
        part in _PRIVATE_FIELD_TOKENS for part in parts
    )


def _validate_expected(value: object, path: str = "expected") -> None:
    if _is_mapping(value):
        for key, item in value.items():
            field = f"{path}.{key}"
            if _private_key(key):
                raise RunnerProfileError(f"runner profile must exclude private field {field}")
            _validate_expected(item, field)
        return
    if value is None or isinstance(value, (str, int, bool)):
        return
    raise RunnerProfileError(
        f"runner profile field {path} must be a string, integer, boolean, or table"
    )


def _same_scalar(expected: object, actual: object) -> bool:
    return type(expected) is type(actual) and expected == actual


@dataclass(frozen=True, slots=True)
class RunnerProfile:
    """Stable expected comparison environment declared by a versioned TOML file."""

    path: Path
    digest: str
    expected: Mapping[str, object]
    schema_version: int = _PROFILE_VERSION

    def validate(self, actual: Mapping[str, object]) -> None:
        """Require every declared value to be present and exactly equal in ``actual``."""

        self._validate_mapping(self.expected, actual, "expected")

    @classmethod
    def _validate_mapping(
        cls, expected: Mapping[str, object], actual: Mapping[str, object], path: str
    ) -> None:
        for key, expected_value in expected.items():
            field = f"{path}.{key}"
            if key not in actual:
                raise RunnerProfileError(f"runner profile requires unavailable field {field}")
            actual_value = actual[key]
            if _is_mapping(expected_value):
                if not _is_mapping(actual_value):
                    raise RunnerProfileError(
                        f"runner profile mismatch at {field}: expected a table, "
                        f"got {actual_value!r}"
                    )
                cls._validate_mapping(expected_value, actual_value, field)
            elif not _same_scalar(expected_value, actual_value):
                raise RunnerProfileError(
                    f"runner profile mismatch at {field}: expected {expected_value!r}, "
                    f"got {actual_value!r}"
                )


def load_runner_profile(path: Path) -> RunnerProfile:
    """Load one supported profile without permitting identity-bearing fields."""

    resolved = path.expanduser().resolve()
    try:
        with resolved.open("rb") as source:
            raw = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RunnerProfileError(f"cannot load runner profile {path}: {error}") from error
    if not _is_mapping(raw) or set(raw) != {"schema_version", "expected"}:
        raise RunnerProfileError("runner profile must contain only schema_version and expected")
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != _PROFILE_VERSION:
        raise RunnerProfileError(f"unsupported runner profile schema version: {version!r}")
    expected = raw["expected"]
    if not _is_mapping(expected) or not expected:
        raise RunnerProfileError("runner profile expected environment must be a non-empty table")
    _validate_expected(expected)
    return RunnerProfile(resolved, file_hash(resolved), dict(expected), version)
