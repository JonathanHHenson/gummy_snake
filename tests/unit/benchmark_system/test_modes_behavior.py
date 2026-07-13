from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from benchmarks.cli import main
from benchmarks.framework.git_database import DatabaseError
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

    def stage_candidate(self, record: BenchmarkRecord) -> object:
        self.writes += 1
        return type("Candidate", (), {"branch": "benchmark-record/candidate", "commit": "tip"})()


def test_worktree_never_writes_and_requires_exact_baseline_for_known_machine() -> None:
    report = RunReport(candidate(), complete=True)
    database = FakeDatabase(known=True)
    result = worktree(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert result.outcome is GateOutcome.MISSING_EXACT_BASELINE
    assert database.writes == 0


def test_unseen_worktree_fingerprint_is_advisory_and_never_writes() -> None:
    report = RunReport(candidate(), complete=True)
    database = FakeDatabase()
    result = worktree(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert result.outcome is GateOutcome.PASS_NEW_FINGERPRINT
    assert database.writes == 0


def test_record_head_writes_only_after_pass() -> None:
    report = RunReport(candidate(), complete=True)
    database = FakeDatabase(nearest=object())
    rejected = record_head(database, FakeRunner(report), lambda base, current: Decision.REGRESSION)
    assert rejected.outcome is GateOutcome.REGRESSION
    assert database.writes == 0
    passed = record_head(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert passed.recorded
    assert passed.candidate_branch == "benchmark-record/candidate"
    assert database.writes == 1


def test_cli_worktree_uses_runner_and_record_head_stages_only_after_preconditions(
    monkeypatch, tmp_path, capsys
) -> None:
    catalog = tmp_path / "catalog.toml"
    catalog.write_text("ignored")
    report = RunReport(candidate(), complete=True)
    created: list[object] = []

    class CliDatabase(FakeDatabase):
        def __init__(self, _repository: object) -> None:
            super().__init__(known=False)

    class CliRunner:
        def __init__(self, _repository: object, _catalog: object, _output: object) -> None:
            created.append(self)

        def run(self, _mode: BenchmarkMode) -> RunReport:
            return report

    monkeypatch.setattr("benchmarks.cli.GitBenchmarkDatabase", CliDatabase)
    monkeypatch.setattr("benchmarks.cli.BenchmarkRecorderRunner", CliRunner)
    monkeypatch.setattr(
        "benchmarks.cli.load_catalog", lambda _path: type("Catalog", (), {"digest": "sha256:c"})()
    )
    monkeypatch.setattr("benchmarks.cli.compare_record_to_baseline", lambda *_args: Decision.PASS)

    assert main(["--repo", str(tmp_path), "worktree", str(catalog)]) == 0
    assert created
    assert "pass-new-fingerprint" in capsys.readouterr().out

    class DirtyDatabase(CliDatabase):
        def require_clean_head(self) -> str:
            raise DatabaseError("record-head requires a clean worktree")

    monkeypatch.setattr("benchmarks.cli.GitBenchmarkDatabase", DirtyDatabase)
    assert main(["--repo", str(tmp_path), "record-head", str(catalog)]) == 2
    assert "clean worktree" in capsys.readouterr().err
