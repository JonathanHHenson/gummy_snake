"""Code-facing policy for deterministic local benchmark comparisons."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

LOCAL_HISTORY_DIRECTORY = ".scratch/benchmark/history"
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
    """A request attempted to weaken a fixed benchmark policy."""


class CapabilityError(GovernanceError):
    """A selected benchmark route is missing a required capability."""


class BenchmarkMode(StrEnum):
    WORKTREE = "worktree"
    RECORD_HEAD = "record-head"


class ExecutionClass(StrEnum):
    """Concrete runtime routes selectable by benchmark catalogs."""

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
    route: str
    fail_closed_capabilities: tuple[str, ...]
    timing_scope: str


EXECUTION_CLASS_POLICIES: Mapping[ExecutionClass, ExecutionClassPolicy] = MappingProxyType(
    {
        ExecutionClass.HEADLESS: ExecutionClassPolicy(
            ExecutionClass.HEADLESS,
            "offscreen-canvas-or-offline-runtime",
            ("required-runtime", "offscreen-route"),
            "comparable only for cataloged headless behavior; never substitutes for native routes",
        ),
        ExecutionClass.SIMULATED_REALTIME: ExecutionClassPolicy(
            ExecutionClass.SIMULATED_REALTIME,
            "deterministic-clock-and-bounded-runtime",
            ("required-runtime", "simulated-clock"),
            "comparable for declared simulated-time behavior only",
        ),
        ExecutionClass.NATIVE_INTERACTIVE: ExecutionClassPolicy(
            ExecutionClass.NATIVE_INTERACTIVE,
            "native-window-with-headless-false",
            ("native-window", "gpu-or-declared-render-route", "frames-presented-counter"),
            "must verify public frames_presented and cannot use headless substitution",
        ),
        ExecutionClass.NATIVE_AUDIO: ExecutionClassPolicy(
            ExecutionClass.NATIVE_AUDIO,
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
            "dirty worktree measured with current HEAD provenance",
            "latest compatible local record: exact HEAD, then recorded ancestor, then latest",
            False,
            "dirty is permitted",
            "pass without recording when no compatible local baseline exists",
        ),
        BenchmarkMode.RECORD_HEAD: ModePolicy(
            BenchmarkMode.RECORD_HEAD,
            "clean exact HEAD",
            "latest compatible local record with exact-HEAD and ancestor preference",
            True,
            "must be clean",
            "explicit maintainer command appends an immutable local HEAD record after all gates",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class LocalDatabasePolicy:
    """Fixed policy for the ignored repository-local benchmark store."""

    backend: str = "local-filesystem"
    history_directory: str = LOCAL_HISTORY_DIRECTORY
    append_policy: str = "immutable-primary-key-first-writer-wins"
    audit: str = "canonical-index-and-record-validation"
    schema_migration: str = "versioned-migration-required"
    benchmark_versioning: str = "meaning-change-requires-version-bump"
    configurable_value: str = "local-history-directory-only"


LOCAL_DATABASE_POLICY = LocalDatabasePolicy()


def degradation_exceeds_limit(change_fraction: Decimal) -> bool:
    """Apply the fixed policy: exactly 5.00% passes; any larger degradation fails."""

    if not isinstance(change_fraction, Decimal) or not change_fraction.is_finite():
        raise GovernanceError("degradation must be a finite Decimal fraction")
    return change_fraction > REGRESSION_LIMIT_FRACTION


def reject_policy_overrides(arguments: Iterable[str]) -> None:
    """Reject CLI flags that would weaken fixed local comparison semantics."""

    forbidden = (
        "--threshold",
        "--regression-threshold",
        "--regression-limit",
        "--force",
        "--force-record",
        "--ignore-fingerprint",
        "--fingerprint",
        "--sampling",
        "--profile",
    )
    for argument in arguments:
        if any(argument == flag or argument.startswith(f"{flag}=") for flag in forbidden):
            raise GovernanceError(f"benchmark policy override is not supported: {argument}")


def capability_error(required: str, detail: str | None = None) -> CapabilityError:
    """Create a fail-closed capability error without selecting an alternate path."""

    suffix = f": {detail}" if detail else ""
    return CapabilityError(
        f"required benchmark capability unavailable ({required}){suffix}; no fallback is permitted"
    )
