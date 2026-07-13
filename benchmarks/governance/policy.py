"""Frozen, code-facing governance for authoritative benchmark comparisons.

These rules intentionally live apart from CLI parsing. A caller may select the remote
location of the data ref, but cannot select another ref, weaken a gate, or convert a
trial or missing-capability route into authoritative data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

AUTHORITATIVE_DATA_REF = "refs/heads/benchmark-data-v1"
GOVERNANCE_VERSION = 1
# Both representations are public so callers cannot confuse 5.00 percent with 0.05
# percentage points. The historical name remains an alias for compatibility.
REGRESSION_LIMIT_PERCENT = Decimal("5.00")
REGRESSION_LIMIT_FRACTION = REGRESSION_LIMIT_PERCENT / Decimal(100)
PERCENT_REGRESSION_LIMIT = REGRESSION_LIMIT_FRACTION
SCHEMA_VERSION = GOVERNANCE_VERSION

if Decimal("0.05") != PERCENT_REGRESSION_LIMIT:  # pragma: no cover - import invariant
    raise RuntimeError("benchmark regression policy must remain exactly 5.00%")


class GovernanceError(RuntimeError):
    """A request attempted to weaken a frozen benchmark policy."""


class AuthorityError(GovernanceError):
    """A workload or recorder does not meet authority requirements."""


class BenchmarkMode(StrEnum):
    WORKTREE = "worktree"
    RECORD_HEAD = "record-head"


class ExecutionClass(StrEnum):
    """Catalog execution and authority classes with frozen semantics."""

    AUTHORITATIVE = "authoritative"
    TRIAL = "trial"
    HEADLESS = "headless"
    SIMULATED_REALTIME = "simulated-realtime"
    NATIVE_INTERACTIVE = "native-interactive"
    NATIVE_AUDIO = "native-audio"


class BenchmarkDomain(StrEnum):
    CANVAS = "canvas"
    ECS = "ecs"
    SYNTH = "synth"
    PYTHON_BRIDGE = "python-bridge"
    GPU = "gpu"
    SPATIAL = "spatial"
    DSP = "dsp"
    DEVICE = "device"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class DomainInventoryEntry:
    """Production behavior in replacement scope, not a copied legacy scenario."""

    domain: BenchmarkDomain
    owner: str
    concerns: tuple[str, ...]
    capability_families: tuple[str, ...]
    permitted_execution_classes: tuple[ExecutionClass, ...]


PRODUCTION_DOMAIN_INVENTORY = (
    DomainInventoryEntry(
        BenchmarkDomain.CANVAS,
        "gummy-canvas",
        (
            "lifecycle-and-presentation",
            "two-d-drawing-and-ordering",
            "images-text-pixels-effects",
            "assets-media-models-resources",
            "hidpi-and-readback",
        ),
        ("canvas-runtime", "offscreen-rendering", "native-window", "pixel-readback"),
        (ExecutionClass.HEADLESS, ExecutionClass.NATIVE_INTERACTIVE),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.ECS,
        "gummy-ecs",
        ("storage-and-query", "physical-plans", "schedules", "events-and-resources"),
        ("ecs-runtime",),
        (ExecutionClass.HEADLESS, ExecutionClass.SIMULATED_REALTIME),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.SYNTH,
        "gummy-synth",
        ("synthesis", "sample-rendering", "effects", "wav-encoding"),
        ("synth-runtime", "audio-output"),
        (ExecutionClass.HEADLESS, ExecutionClass.NATIVE_AUDIO),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.PYTHON_BRIDGE,
        "pyo3-boundary",
        ("dispatch", "conversion", "buffer-transfer", "udf-boundaries"),
        ("canvas-runtime", "ecs-runtime"),
        (ExecutionClass.HEADLESS, ExecutionClass.SIMULATED_REALTIME),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.GPU,
        "gummy-canvas",
        ("command-encoding", "batching", "uploads", "retained-resources", "presentation"),
        ("gpu", "gpu-backend"),
        (ExecutionClass.HEADLESS, ExecutionClass.NATIVE_INTERACTIVE),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.SPATIAL,
        "gummy-ecs",
        ("index-build", "candidate-generation", "exact-relations", "determinism"),
        ("ecs-runtime", "spatial-index"),
        (ExecutionClass.HEADLESS, ExecutionClass.SIMULATED_REALTIME),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.DSP,
        "gummy-synth",
        ("mixing", "filters", "resampling", "sample-decoding"),
        ("synth-runtime",),
        (ExecutionClass.HEADLESS, ExecutionClass.NATIVE_AUDIO),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.DEVICE,
        "native-runtime",
        ("window-input", "display-route", "audio-device-route", "interactive-strain"),
        ("native-window", "native-input", "audio-output"),
        (ExecutionClass.NATIVE_INTERACTIVE, ExecutionClass.NATIVE_AUDIO),
    ),
    DomainInventoryEntry(
        BenchmarkDomain.OUTPUT,
        "gummy-canvas-and-gummy-synth",
        ("image-export", "model-export", "audio-encoding", "timed-io-route"),
        ("filesystem", "storage-route"),
        (ExecutionClass.HEADLESS, ExecutionClass.NATIVE_AUDIO),
    ),
)
PRODUCTION_DOMAINS: Mapping[BenchmarkDomain, DomainInventoryEntry] = MappingProxyType(
    {entry.domain: entry for entry in PRODUCTION_DOMAIN_INVENTORY}
)


@dataclass(frozen=True, slots=True)
class ExecutionClassPolicy:
    class_: ExecutionClass
    authoritative_eligible: bool
    route: str
    fail_closed_capabilities: tuple[str, ...]
    timing_authority: str


EXECUTION_CLASS_POLICIES: Mapping[ExecutionClass, ExecutionClassPolicy] = MappingProxyType(
    {
        ExecutionClass.AUTHORITATIVE: ExecutionClassPolicy(
            ExecutionClass.AUTHORITATIVE,
            True,
            "catalog-declared-release-worker",
            ("all-catalog-capabilities",),
            "eligible only after all authority requirements and gates pass",
        ),
        ExecutionClass.TRIAL: ExecutionClassPolicy(
            ExecutionClass.TRIAL,
            False,
            "developer-selected-non-recording",
            (),
            "diagnostic only and never a baseline",
        ),
        ExecutionClass.HEADLESS: ExecutionClassPolicy(
            ExecutionClass.HEADLESS,
            True,
            "offscreen-canvas-or-offline-runtime",
            ("required-runtime", "offscreen-route"),
            "authoritative only when cataloged; never substitutes for native routes",
        ),
        ExecutionClass.SIMULATED_REALTIME: ExecutionClassPolicy(
            ExecutionClass.SIMULATED_REALTIME,
            True,
            "deterministic-clock-and-bounded-runtime",
            ("required-runtime", "simulated-clock"),
            "authoritative for declared simulated-time behavior only",
        ),
        ExecutionClass.NATIVE_INTERACTIVE: ExecutionClassPolicy(
            ExecutionClass.NATIVE_INTERACTIVE,
            True,
            "native-window-with-headless-false",
            ("native-window", "gpu-or-declared-render-route", "frames-presented-counter"),
            "must verify public frames_presented and cannot use headless substitution",
        ),
        ExecutionClass.NATIVE_AUDIO: ExecutionClassPolicy(
            ExecutionClass.NATIVE_AUDIO,
            True,
            "selected-native-audio-device",
            ("audio-output", "selected-audio-route"),
            "device route is fingerprinted; offline synthesis is not a substitute",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ModePolicy:
    mode: BenchmarkMode
    subject: str
    baseline: str
    database_writes: bool
    worktree: str
    unseen_fingerprint: str


MODE_POLICIES: Mapping[BenchmarkMode, ModePolicy] = MappingProxyType(
    {
        BenchmarkMode.WORKTREE: ModePolicy(
            BenchmarkMode.WORKTREE,
            "dirty worktree compared as exact current HEAD",
            "exact current-HEAD record for the exact comparison fingerprint",
            False,
            "dirty is permitted",
            "pass without recording; known fingerprint missing exact HEAD fails",
        ),
        BenchmarkMode.RECORD_HEAD: ModePolicy(
            BenchmarkMode.RECORD_HEAD,
            "clean exact HEAD",
            "nearest earlier compatible first-parent record",
            True,
            "must be clean",
            "pass and stage an immutable HEAD candidate after every gate passes",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class DatabaseGovernance:
    data_ref: str = AUTHORITATIVE_DATA_REF
    configurable_value: str = "remote-location-only"
    recorder: str = "trusted-local-release-recorder"
    branch_protection: str = "reviewed-append-only-no-force-update"
    review: str = "candidate-branch-review-before-protected-ref-advance"
    revocation: str = "append-only-reviewed-revocation-record"
    schema_migration: str = "reviewed-versioned-migration-required"
    benchmark_versioning: str = "meaning-change-requires-reviewed-version-bump"
    retirement: str = "legacy-scenarios-and-values-are-historical-non-authoritative"


DATABASE_GOVERNANCE = DatabaseGovernance()
LEGACY_BENCHMARK_DATA_AUTHORITY = "historical-non-authoritative-not-imported"


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


def degradation_exceeds_limit(change_fraction: Decimal) -> bool:
    """Apply the frozen policy: exactly 5.00% passes; any larger degradation fails."""

    if not isinstance(change_fraction, Decimal) or not change_fraction.is_finite():
        raise GovernanceError("degradation must be a finite Decimal fraction")
    return change_fraction > REGRESSION_LIMIT_FRACTION


def reject_authority_overrides(arguments: Iterable[str]) -> None:
    """Reject known bypass flags before any runner or database work starts."""

    forbidden = (
        "--threshold",
        "--regression-threshold",
        "--regression-limit",
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
