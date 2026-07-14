from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.cli import _parser, main
from benchmarks.framework.local_database import LocalDatabaseError
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
    ancestor: object | None = None
    latest: object | None = None
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

    def nearest_ancestor_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None:
        return self.ancestor

    def latest_record(
        self, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> object | None:
        return self.latest

    def record(self, record: BenchmarkRecord) -> object:
        self.writes += 1
        return type(
            "Stored",
            (),
            {
                "path": ".scratch/benchmark/history/record.json",
                "record_id": record.record_id,
                "created": True,
            },
        )()


def test_worktree_prefers_exact_then_ancestor_then_latest_without_writing() -> None:
    report = RunReport(candidate(), complete=True)
    compared: list[object] = []

    def compare(baseline: object, current: BenchmarkRecord) -> Decision:
        del current
        compared.append(baseline)
        return Decision.PASS

    exact = object()
    ancestor = object()
    latest = object()
    database = FakeDatabase(exact=exact, ancestor=ancestor, latest=latest)
    assert worktree(database, FakeRunner(report), compare).outcome is GateOutcome.PASS
    assert compared.pop() is exact

    database.exact = None
    assert worktree(database, FakeRunner(report), compare).outcome is GateOutcome.PASS
    assert compared.pop() is ancestor

    database.ancestor = None
    assert worktree(database, FakeRunner(report), compare).outcome is GateOutcome.PASS
    assert compared.pop() is latest
    assert database.writes == 0


def test_unseen_worktree_fingerprint_is_advisory_and_never_writes() -> None:
    report = RunReport(candidate(), complete=True)
    database = FakeDatabase()
    result = worktree(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert result.outcome is GateOutcome.PASS_NEW_FINGERPRINT
    assert database.writes == 0


def test_record_head_writes_only_after_pass() -> None:
    current = candidate()
    report = RunReport(current, complete=True)
    database = FakeDatabase(ancestor=object())
    rejected = record_head(database, FakeRunner(report), lambda base, current: Decision.REGRESSION)
    assert rejected.outcome is GateOutcome.REGRESSION
    assert database.writes == 0
    passed = record_head(database, FakeRunner(report), lambda base, current: Decision.PASS)
    assert passed.recorded
    assert passed.record_path == ".scratch/benchmark/history/record.json"
    assert passed.record_id == current.record_id
    assert passed.candidate_branch is None
    assert database.writes == 1


def test_cli_worktree_uses_local_store_and_record_head_checks_preconditions(
    monkeypatch, tmp_path, capsys
) -> None:
    catalog = tmp_path / "catalog.toml"
    catalog.write_text("ignored")
    report = RunReport(candidate(), complete=True)
    created: list[object] = []

    database_arguments: list[tuple[object, object]] = []

    class CliDatabase(FakeDatabase):
        def __init__(self, repository: object, history: object) -> None:
            database_arguments.append((repository, history))
            super().__init__(known=False)

    class CliRunner:
        def __init__(self, _repository: object, _catalog: object, _output: object) -> None:
            created.append(self)

        def run(self, _mode: BenchmarkMode) -> RunReport:
            return report

    monkeypatch.setattr("benchmarks.cli.LocalBenchmarkDatabase", CliDatabase)
    monkeypatch.setattr("benchmarks.cli.BenchmarkRecorderRunner", CliRunner)
    monkeypatch.setattr(
        "benchmarks.cli.load_catalog", lambda _path: type("Catalog", (), {"digest": "sha256:c"})()
    )
    monkeypatch.setattr("benchmarks.cli.compare_record_to_baseline", lambda *_args: Decision.PASS)

    assert main(["--repo", str(tmp_path), "worktree", str(catalog)]) == 0
    assert created
    assert database_arguments == [(tmp_path, Path(".scratch/benchmark/history"))]
    assert "pass-new-fingerprint" in capsys.readouterr().out

    class DirtyDatabase(CliDatabase):
        def require_clean_head(self) -> str:
            raise LocalDatabaseError("record-head requires a clean worktree")

    monkeypatch.setattr("benchmarks.cli.LocalBenchmarkDatabase", DirtyDatabase)
    assert main(["--repo", str(tmp_path), "record-head", str(catalog)]) == 2
    assert "clean worktree" in capsys.readouterr().err


def test_cli_has_local_history_default_and_no_remote_option() -> None:
    namespace = _parser().parse_args(["list"])

    assert namespace.history == Path(".scratch/benchmark/history")
    assert not hasattr(namespace, "remote")
    assert "--remote" not in _parser().format_help()
