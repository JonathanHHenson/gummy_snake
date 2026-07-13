"""Shared public types for the governed Git benchmark database."""

from __future__ import annotations

from dataclasses import dataclass


class DatabaseError(RuntimeError):
    """The authoritative Git database cannot be trusted or updated safely."""


@dataclass(frozen=True, slots=True)
class AuditIssue:
    """One integrity problem found at a database path or Git reference."""

    path: str
    message: str


@dataclass(frozen=True, slots=True)
class StagedCandidate:
    """A locally staged immutable change awaiting protected-branch review."""

    branch: str
    commit: str
