"""Canonical JSON, strict parsing, and digest helpers for benchmark data."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn


class CanonicalJsonError(ValueError):
    """A value violates the benchmark canonical JSON contract."""


def _normalise(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalise(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.init or field.name != "record_id"
        }
    if isinstance(value, Enum):
        return _normalise(value.value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalJsonError("canonical JSON rejects non-finite Decimal values")
        # Decimal summaries are strings so JSON readers cannot silently round them.
        return format(value, "f")
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalJsonError("canonical JSON object keys must be strings")
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJsonError("canonical JSON rejects NaN and infinity")
        raise CanonicalJsonError(
            "canonical records must not contain binary floats; use integer raw values or Decimal"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Sequence):
        raise CanonicalJsonError(f"unsupported canonical JSON sequence: {type(value).__name__}")
    raise CanonicalJsonError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Return UTF-8 canonical JSON with sorted keys and exactly one trailing newline."""

    normalized = _normalise(value)
    try:
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CanonicalJsonError(f"value is not canonical JSON: {error}") from error
    return encoded + b"\n"


def _reject_float(value: str) -> NoReturn:
    raise CanonicalJsonError(
        f"canonical JSON rejects binary-float number token {value!r}; decimals are strings"
    )


def _reject_constant(value: str) -> NoReturn:
    raise CanonicalJsonError(f"canonical JSON rejects non-finite number token {value!r}")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJsonError(f"canonical JSON rejects duplicate object key {key!r}")
        result[key] = value
    return result


def canonical_json_loads(payload: bytes | str, *, require_canonical: bool = True) -> object:
    """Parse benchmark JSON without floats, duplicate keys, or non-canonical encoding.

    When ``require_canonical`` is true (the default), key order, whitespace, UTF-8,
    and the single trailing newline must exactly match :func:`canonical_json`.
    """

    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CanonicalJsonError("canonical JSON must be valid UTF-8") from error
    elif isinstance(payload, str):
        text = payload
    else:
        raise CanonicalJsonError("canonical JSON payload must be bytes or str")
    if text.startswith("\ufeff"):
        raise CanonicalJsonError("canonical JSON must not contain a byte-order mark")
    try:
        parsed = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except json.JSONDecodeError as error:
        raise CanonicalJsonError(f"invalid canonical JSON: {error}") from error
    if require_canonical and text.encode("utf-8") != canonical_json(parsed):
        raise CanonicalJsonError(
            "JSON is not canonical: require sorted keys, compact separators, "
            "and one trailing newline"
        )
    return parsed


def content_hash(value: Any) -> str:
    """Return a SHA-256 digest of canonical JSON with an explicit algorithm prefix."""

    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def file_hash(path: Path) -> str:
    """Hash a file's exact bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def definition_digest(entry: Mapping[str, object], files: Mapping[str, Path]) -> str:
    """Hash a catalog definition and the exact bytes of all declared workload files."""

    if not files:
        raise CanonicalJsonError("definition digests require at least one declared file")
    hashed = {name: file_hash(path) for name, path in sorted(files.items())}
    return content_hash({"entry": dict(entry), "files": hashed})
