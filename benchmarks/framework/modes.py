"""Local-first worktree comparison and explicit clean-HEAD recording modes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..governance import BenchmarkMode
from ..schema.records import BenchmarkRecord
from .statistics import Decision


class ModeError(RuntimeError):
    """A mode request cannot establish its required baseline or preconditions."""


class GateOutcome(StrEnum):
    PASS = "pass"
    PASS_NEW_FINGERPRINT = "pass-new-fingerprint"
    MISSING_EXACT_BASELINE = "missing-exact-baseline"
    REGRESSION = "regression"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RunReport:
    """Runner result after correctness, capability, and teardown validation."""

    record: BenchmarkRecord | None
    complete: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ModeResult:
    mode: BenchmarkMode
    outcome: GateOutcome
    reason: str
    recorded: bool = False
    baseline_found: bool = False
    record_path: str | None = None
    record_id: str | None = None


class BenchmarkRunner(Protocol):
    def run(self, mode: BenchmarkMode) -> RunReport: ...


class ModeDatabase(Protocol):
    def head(self) -> str: ...

    def require_clean_head(self) -> str: ...

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None: ...

    def nearest_ancestor_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None: ...

    def latest_record(
        self, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None: ...

    def record(self, record: BenchmarkRecord) -> object: ...


Comparison = Callable[[object, BenchmarkRecord], Decision]


def _identity(record: BenchmarkRecord) -> tuple[str, str, str, int]:
    return record.primary_key


def _ready(report: RunReport) -> ModeResult | None:
    if not report.complete or report.record is None:
        return ModeResult(
            BenchmarkMode.WORKTREE, GateOutcome.INVALID, report.reason or "runner did not complete"
        )
    return None


def _comparison_outcome(decision: Decision) -> GateOutcome:
    if decision is Decision.PASS:
        return GateOutcome.PASS
    if decision in (Decision.REGRESSION, Decision.ABSOLUTE_FAILURE):
        return GateOutcome.REGRESSION
    return GateOutcome.INCONCLUSIVE


def _compatible_baseline(
    database: ModeDatabase,
    subject: str,
    fingerprint: str,
    suite: str,
    version: int,
) -> object | None:
    exact = database.exact_record(subject, fingerprint, suite, version)
    if exact is not None:
        return exact
    ancestor_lookup = getattr(database, "nearest_ancestor_record", None)
    if callable(ancestor_lookup):
        ancestor = ancestor_lookup(subject, fingerprint, suite, version)
        if ancestor is not None:
            return ancestor
    latest_lookup = getattr(database, "latest_record", None)
    if callable(latest_lookup):
        return latest_lookup(fingerprint, suite, version)
    return None


def worktree(database: ModeDatabase, runner: BenchmarkRunner, compare: Comparison) -> ModeResult:
    """Compare a worktree without writing, preferring exact and ancestor baselines."""

    report = runner.run(BenchmarkMode.WORKTREE)
    blocked = _ready(report)
    if blocked is not None:
        return ModeResult(BenchmarkMode.WORKTREE, blocked.outcome, blocked.reason)
    record = report.record
    assert record is not None
    subject, fingerprint, suite, version = _identity(record)
    head = database.head()
    if subject != head:
        raise ModeError("worktree runner provenance subject must equal current HEAD")
    baseline = _compatible_baseline(database, head, fingerprint, suite, version)
    if baseline is None:
        return ModeResult(
            BenchmarkMode.WORKTREE,
            GateOutcome.PASS_NEW_FINGERPRINT,
            "successful run has no compatible local baseline and remains unrecorded",
        )
    decision = compare(baseline, record)
    outcome = _comparison_outcome(decision)
    return ModeResult(BenchmarkMode.WORKTREE, outcome, decision.value, baseline_found=True)


def record_head(database: ModeDatabase, runner: BenchmarkRunner, compare: Comparison) -> ModeResult:
    """Benchmark clean HEAD and append a local record only after every gate passes."""

    head = database.require_clean_head()
    report = runner.run(BenchmarkMode.RECORD_HEAD)
    blocked = _ready(report)
    if blocked is not None:
        return ModeResult(BenchmarkMode.RECORD_HEAD, blocked.outcome, blocked.reason)
    record = report.record
    assert record is not None
    subject, fingerprint, suite, version = _identity(record)
    if subject != head:
        raise ModeError("record-head runner provenance subject must equal clean HEAD")
    baseline = _compatible_baseline(database, head, fingerprint, suite, version)
    if baseline is None:
        outcome = GateOutcome.PASS_NEW_FINGERPRINT
        reason = "successful run has no compatible local baseline"
    else:
        decision = compare(baseline, record)
        outcome = _comparison_outcome(decision)
        reason = decision.value
        if outcome is not GateOutcome.PASS:
            return ModeResult(BenchmarkMode.RECORD_HEAD, outcome, reason, baseline_found=True)
    # Recheck clean HEAD immediately before the immutable local write.
    if database.require_clean_head() != head:
        raise ModeError("HEAD changed while benchmarking; refusing to record")
    stored = database.record(record)
    path = getattr(stored, "path", None)
    record_id = getattr(stored, "record_id", None)
    created = getattr(stored, "created", True)
    if path is None or not isinstance(record_id, str) or not isinstance(created, bool):
        raise ModeError("database returned an invalid local record result")
    return ModeResult(
        BenchmarkMode.RECORD_HEAD,
        outcome,
        reason,
        recorded=created,
        baseline_found=baseline is not None,
        record_path=str(path),
        record_id=record_id,
    )
