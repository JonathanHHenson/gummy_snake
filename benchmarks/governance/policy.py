"""Non-configurable governance rules for authoritative benchmark comparisons.

These rules intentionally live apart from CLI parsing.  A caller may choose a data
remote, but neither a different data ref nor a weaker gate is a supported option.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

AUTHORITATIVE_DATA_REF = "refs/heads/benchmark-data-v1"
# Local baseline recording prioritizes useful signal over lab-grade repeatability.
# Tighten this only when the project has dedicated controlled benchmark hardware.
PERCENT_REGRESSION_LIMIT = Decimal("0.05")
SCHEMA_VERSION = 1


class GovernanceError(RuntimeError):
    """A request attempted to weaken a frozen benchmark policy."""


class AuthorityError(GovernanceError):
    """A workload or recorder does not meet authority requirements."""


class BenchmarkMode(StrEnum):
    WORKTREE = "worktree"
    RECORD_HEAD = "record-head"


class ExecutionClass(StrEnum):
    """Catalog execution routes; only the listed classes have defined semantics."""

    AUTHORITATIVE = "authoritative"
    TRIAL = "trial"
    HEADLESS = "headless"
    SIMULATED_REALTIME = "simulated-realtime"
    NATIVE_INTERACTIVE = "native-interactive"
    NATIVE_AUDIO = "native-audio"


@dataclass(frozen=True, slots=True)
class AuthorityRequirements:
    """Properties required before a workload may make an authoritative record."""

    self_contained: bool
    release_built: bool
    cataloged: bool
    correctness_first: bool
    capability_explicit: bool
    independent_of_legacy: bool

    @property
    def satisfied(self) -> bool:
        return all(
            (
                self.self_contained,
                self.release_built,
                self.cataloged,
                self.correctness_first,
                self.capability_explicit,
                self.independent_of_legacy,
            )
        )


def require_authoritative_workload(requirements: AuthorityRequirements) -> None:
    """Reject incomplete authority declarations instead of assuming safe defaults."""

    if not requirements.satisfied:
        missing = [
            name
            for name in AuthorityRequirements.__dataclass_fields__
            if not getattr(requirements, name)
        ]
        raise AuthorityError(
            "authoritative workloads must be self-contained, release-built, cataloged, "
            "correctness-first, capability-explicit, and independent of legacy helpers; "
            f"missing: {', '.join(missing)}"
        )


def reject_authority_overrides(arguments: Iterable[str]) -> None:
    """Reject known bypass flags before any runner or database work starts."""

    forbidden = (
        "--threshold",
        "--regression-threshold",
        "--force",
        "--force-record",
        "--ignore-fingerprint",
        "--fingerprint",
        "--database-ref",
        "--branch",
        "--sampling",
        "--profile",
    )
    for argument in arguments:
        if any(argument == flag or argument.startswith(f"{flag}=") for flag in forbidden):
            raise GovernanceError(f"authoritative override is not supported: {argument}")


def capability_error(required: str, detail: str | None = None) -> AuthorityError:
    """Create a clear fail-closed capability error without selecting an alternate path."""

    suffix = f": {detail}" if detail else ""
    return AuthorityError(
        f"required benchmark capability unavailable ({required}){suffix}; no fallback is permitted"
    )
