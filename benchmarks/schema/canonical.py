"""Canonical JSON and digest helpers used by the immutable database."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


class CanonicalJsonError(ValueError):
    """A value cannot be represented by the benchmark canonical JSON contract."""


def _normalise(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _normalise(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return _normalise(value.value)
    if isinstance(value, Decimal):
        # Decimal summaries are strings so JSON readers cannot silently round them.
        return format(value, "f")
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalJsonError("canonical JSON object keys must be strings")
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJsonError("canonical JSON rejects NaN and infinity")
        raise CanonicalJsonError(
            "canonical records must not contain binary floats; use Decimal strings"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise CanonicalJsonError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Return UTF-8 canonical JSON with exactly one trailing newline."""

    normalized = _normalise(value)
    return (
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    """SHA-256 digest of canonical JSON, prefixed to make its algorithm explicit."""

    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def file_hash(path: Path) -> str:
    """Hash a file's exact bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
