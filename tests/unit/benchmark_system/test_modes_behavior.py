from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from benchmarks.framework.modes import GateOutcome, RunReport, record_head, worktree
from benchmarks.framework.statistics import Decision
from benchmarks.governance import BenchmarkMode
from benchmarks.schema.records import (
    BenchmarkRecord,
    ComparisonFingerprint,
    MetricResult,
    Provenance,
)


def candidate(subject: str = "head") -> BenchmarkRecord:
    return BenchmarkRecord(
        ComparisonFingerprint({"architecture": "x86_64", "runtime_route": "headless"}),
        Provenance(subject, "sha256:s", "sha256:t", "sha256:w", "sha256:l", {}, {}),
        "canvas",
        1,
        "sha256:c",
        (
            MetricResult(
                ("x", 1, "c", "sha256:p", "m", 1, 1),
                ((1,), (1,)),
                1,
                Decimal(1),
                "ns",
                "lower-is-better",
                "ratio",
                Decimal(1),
            ),
        ),
        {},
    )


@dataclass
class FakeRunner:
    report: RunReport

    def run(self, mode: BenchmarkMode) -> RunReport:
        return self.report


@dataclass
class FakeDatabase:
    known: bool = False
    exact: object | None = None
    nearest: object | None = None
    writes: int = 0

    def head(self) -> str:
        return "head"

    def require_clean_head(self) -> str:
        return "head"

    def fingerprint_known(self, fingerprint_id: str) -> bool:
        return self.known

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None:
        return self.exact

    def nearest_first_parent_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None:
        return self.nearest

    def record_local(self, record: BenchmarkRecord, *, message: str | None = None) -> str:
        self.writes += 1
        return "tip"


def test_worktree_never_writes_and_requires_exact_baseline_for_known_machine() -> None:
    report = RunReport(candidate(), complete=True, stable=True)
    database = FakeDatabase(known=True)
    result = worktree(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert result.outcome is GateOutcome.MISSING_EXACT_BASELINE
    assert database.writes == 0


def test_unseen_worktree_fingerprint_requires_stability_but_never_writes() -> None:
    report = RunReport(candidate(), complete=True, stable=False)
    database = FakeDatabase()
    result = worktree(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert result.outcome is GateOutcome.INVALID
    assert database.writes == 0


def test_record_head_writes_only_after_pass() -> None:
    report = RunReport(candidate(), complete=True, stable=True)
    database = FakeDatabase(nearest=object())
    rejected = record_head(database, FakeRunner(report), lambda base, current: Decision.REGRESSION)
    assert rejected.outcome is GateOutcome.REGRESSION
    assert database.writes == 0
    passed = record_head(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert passed.recorded
    assert database.writes == 1
