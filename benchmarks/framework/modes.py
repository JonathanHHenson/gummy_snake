"""Frozen Mode 1 and Mode 2 orchestration around injected runners and Git stores."""

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
    """Runner result after correctness, capabilities, teardown, and A/A validation."""

    record: BenchmarkRecord | None
    complete: bool
    stable: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ModeResult:
    mode: BenchmarkMode
    outcome: GateOutcome
    reason: str
    recorded: bool = False
    baseline_found: bool = False
    candidate_branch: str | None = None
    candidate_commit: str | None = None


class BenchmarkRunner(Protocol):
    def run(self, mode: BenchmarkMode) -> RunReport: ...


class ModeDatabase(Protocol):
    def head(self) -> str: ...

    def require_clean_head(self) -> str: ...

    def fingerprint_known(self, fingerprint_id: str) -> bool: ...

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None: ...

    def nearest_first_parent_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None: ...

    def stage_candidate(self, record: BenchmarkRecord) -> object: ...


Comparison = Callable[[object, BenchmarkRecord], Decision]


def _identity(record: BenchmarkRecord) -> tuple[str, str, str, int]:
    return record.primary_key


def _ready(report: RunReport, *, require_stability: bool) -> ModeResult | None:
    if not report.complete or report.record is None:
        return ModeResult(
            BenchmarkMode.WORKTREE, GateOutcome.INVALID, report.reason or "runner did not complete"
        )
    if require_stability and not report.stable:
        return ModeResult(
            BenchmarkMode.WORKTREE, GateOutcome.INVALID, report.reason or "A/A stability failed"
        )
    return None


def _comparison_outcome(decision: Decision) -> GateOutcome:
    if decision is Decision.PASS:
        return GateOutcome.PASS
    if decision in (Decision.REGRESSION, Decision.ABSOLUTE_FAILURE):
        return GateOutcome.REGRESSION
    return GateOutcome.INCONCLUSIVE


def worktree(database: ModeDatabase, runner: BenchmarkRunner, compare: Comparison) -> ModeResult:
    """Mode 1: exact current-HEAD lookup and strictly no database writes."""

    report = runner.run(BenchmarkMode.WORKTREE)
    blocked = _ready(report, require_stability=False)
    if blocked is not None:
        return ModeResult(BenchmarkMode.WORKTREE, blocked.outcome, blocked.reason)
    record = report.record
    assert record is not None
    subject, fingerprint, suite, version = _identity(record)
    head = database.head()
    if subject != head:
        raise ModeError("worktree runner provenance subject must equal current HEAD")
    known = database.fingerprint_known(fingerprint)
    baseline = database.exact_record(head, fingerprint, suite, version)
    if baseline is None:
        if not known:
            if not report.stable:
                return ModeResult(
                    BenchmarkMode.WORKTREE,
                    GateOutcome.INVALID,
                    report.reason or "unseen fingerprint failed required A/A stability check",
                )
            return ModeResult(
                BenchmarkMode.WORKTREE,
                GateOutcome.PASS_NEW_FINGERPRINT,
                "successful unseen fingerprint is advisory-only and remains unrecorded",
            )
        return ModeResult(
            BenchmarkMode.WORKTREE,
            GateOutcome.MISSING_EXACT_BASELINE,
            "known fingerprint has no exact current-HEAD baseline",
        )
    decision = compare(baseline, record)
    outcome = _comparison_outcome(decision)
    return ModeResult(BenchmarkMode.WORKTREE, outcome, decision.value, baseline_found=True)


def record_head(database: ModeDatabase, runner: BenchmarkRunner, compare: Comparison) -> ModeResult:
    """Mode 2: clean HEAD, nearest first-parent baseline, record only after every gate."""

    head = database.require_clean_head()
    report = runner.run(BenchmarkMode.RECORD_HEAD)
    blocked = _ready(report, require_stability=True)
    if blocked is not None:
        return ModeResult(BenchmarkMode.RECORD_HEAD, blocked.outcome, blocked.reason)
    record = report.record
    assert record is not None
    subject, fingerprint, suite, version = _identity(record)
    if subject != head:
        raise ModeError("record-head runner provenance subject must equal clean HEAD")
    baseline = database.nearest_first_parent_record(head, fingerprint, suite, version)
    if baseline is None:
        outcome = GateOutcome.PASS_NEW_FINGERPRINT
        reason = "successful stable run has no compatible earlier first-parent baseline"
    else:
        decision = compare(baseline, record)
        outcome = _comparison_outcome(decision)
        reason = decision.value
        if outcome is not GateOutcome.PASS:
            return ModeResult(BenchmarkMode.RECORD_HEAD, outcome, reason, baseline_found=True)
    # Recheck clean HEAD immediately before the immutable transaction.
    if database.require_clean_head() != head:
        raise ModeError("HEAD changed while benchmarking; refusing to record")
    staged = database.stage_candidate(record)
    branch = getattr(staged, "branch", None)
    commit = getattr(staged, "commit", None)
    if not isinstance(branch, str) or not isinstance(commit, str):
        raise ModeError("database returned an invalid staged candidate")
    return ModeResult(
        BenchmarkMode.RECORD_HEAD,
        outcome,
        reason,
        recorded=True,
        baseline_found=baseline is not None,
        candidate_branch=branch,
        candidate_commit=commit,
    )
