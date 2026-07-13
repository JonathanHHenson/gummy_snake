"""Canonical shard paths and strict JSON field validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from ...schema.canonical import canonical_json
from . import DatabaseError

MANAGED_ROOTS = ("fingerprints/v1/", "records/v1/", "revocations/v1/")
_HEX_RE = re.compile(r"^[0-9a-f]+$")
_SUITE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def is_lower_hex(value: str) -> bool:
    """Return whether a value is non-empty lowercase hexadecimal text."""

    return _HEX_RE.fullmatch(value) is not None


def canonical_object(payload: bytes, *, kind: str, path: str) -> dict[str, object]:
    """Decode one canonical JSON object or raise a path-specific database error."""

    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DatabaseError(f"corrupt {kind} {path}: {error}") from error
    if not isinstance(value, dict):
        raise DatabaseError(f"corrupt {kind} {path}: expected object")
    if payload != canonical_json(value):
        raise DatabaseError(f"corrupt {kind} {path}: expected canonical JSON")
    return value


def mapping_field(value: object, field: str) -> Mapping[str, object]:
    """Narrow a decoded field to a string-keyed mapping."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return value


def string_field(value: object, field: str) -> str:
    """Narrow a decoded field to a non-empty string."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def integer_field(value: object, field: str) -> int:
    """Narrow a decoded field to a non-boolean integer."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def hash_digest(value: str, *, field: str) -> str:
    """Return the digest from a canonical SHA-256 content identifier."""

    prefix, separator, digest = value.partition(":")
    if separator != ":" or prefix != "sha256" or len(digest) != 64 or not is_lower_hex(digest):
        raise ValueError(f"{field} must be a canonical sha256 content id")
    return digest


def validate_suite(suite_id: str) -> None:
    """Reject suite identifiers that cannot safely form immutable paths."""

    if not _SUITE_RE.fullmatch(suite_id):
        raise DatabaseError(
            "benchmark suite id must use lowercase letters, digits, dots, underscores, or hyphens"
        )


def fingerprint_path(fingerprint_id: str) -> str:
    """Return the canonical fixed-width shard path for a fingerprint."""

    if len(fingerprint_id) != 64 or not is_lower_hex(fingerprint_id):
        raise DatabaseError("fingerprint id must be a 64-character lowercase hexadecimal digest")
    return f"fingerprints/v1/{fingerprint_id[:2]}/{fingerprint_id}.json"


def record_path_parts(
    subject: str,
    fingerprint_id: str,
    suite_id: str,
    suite_version: int,
) -> str:
    """Return the canonical shard path for one immutable record primary key."""

    if len(fingerprint_id) != 64 or not is_lower_hex(fingerprint_id):
        raise DatabaseError("fingerprint id must be a 64-character lowercase hexadecimal digest")
    validate_suite(suite_id)
    if suite_version < 1:
        raise DatabaseError("suite version must be positive")
    return (
        f"records/v1/{fingerprint_id[:2]}/{fingerprint_id}/"
        f"{subject[:2]}/{subject}/{suite_id}@{suite_version}.json"
    )


def revocation_path(revocation_id: str) -> str:
    """Return the canonical content-sharded path for a revocation identifier."""

    digest = hash_digest(revocation_id, field="revocation id")
    return f"revocations/v1/{digest[:2]}/{digest}.json"
