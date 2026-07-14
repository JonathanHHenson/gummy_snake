from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.cli import main
from benchmarks.framework.local_database import (
    DEFAULT_LOCAL_HISTORY,
    LocalBenchmarkDatabase,
    LocalDatabaseError,
)
from benchmarks.schema.canonical import canonical_json
from benchmarks.schema.records import (
    BenchmarkRecord,
    ComparisonFingerprint,
    MetricResult,
    Provenance,
)


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def commit(repository: Path, value: str, message: str) -> str:
    (repository / "code.txt").write_text(value)
    git(repository, "add", "code.txt")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def repository(path: Path) -> tuple[Path, str]:
    git(path, "init")
    git(path, "config", "user.email", "benchmark@example.test")
    git(path, "config", "user.name", "Benchmark Test")
    (path / ".gitignore").write_text(".scratch/\n")
    git(path, "add", ".gitignore")
    first = commit(path, "first", "first")
    return path, first


def digest(character: str) -> str:
    return "sha256:" + character * 64


def benchmark_record(subject: str, sample: int = 100) -> BenchmarkRecord:
    return BenchmarkRecord(
        ComparisonFingerprint({"architecture": "arm64", "runtime_route": "headless"}),
        Provenance(
            subject,
            digest("1"),
            digest("2"),
            digest("3"),
            digest("4"),
            {"profile": "release"},
            {"python": "3.12"},
        ),
        "ecs",
        1,
        digest("5"),
        (
            MetricResult(
                ("query", 1, "small", digest("6"), "elapsed", 1, 1),
                ((sample, sample), (sample, sample)),
                1,
                Decimal(sample),
                "ns",
                "lower-is-better",
                "ratio",
                Decimal(sample),
            ),
        ),
        {},
    )


def test_local_store_defaults_to_ignored_history_and_writes_deterministic_records(
    tmp_path: Path,
) -> None:
    repo, head = repository(tmp_path)
    database = LocalBenchmarkDatabase(repo)
    record = benchmark_record(head)

    stored = database.record(record)

    assert database.root == repo / DEFAULT_LOCAL_HISTORY
    assert stored.created
    assert stored.path == database.root / record.expected_path
    assert stored.path.read_bytes() == canonical_json(record.to_dict())
    assert database.require_clean_head() == head
    assert database.exact_record(head, record.fingerprint.id, "ecs", 1) == record.to_dict()
    assert database.audit() == ()

    repeated = database.record(record)
    assert not repeated.created
    assert repeated.record_id == record.record_id
    assert len(database.list_records()) == 1

    with pytest.raises(LocalDatabaseError, match="different local benchmark record"):
        database.record(benchmark_record(head, 101))


def test_baseline_resolution_prefers_exact_then_latest_recorded_ancestor(
    tmp_path: Path,
) -> None:
    repo, first = repository(tmp_path)
    database = LocalBenchmarkDatabase(repo)
    fingerprint = benchmark_record(first).fingerprint.id
    database.record(benchmark_record(first, 90))

    main_branch = git(repo, "branch", "--show-current")
    git(repo, "checkout", "-b", "side")
    side = commit(repo, "side", "side")
    database.record(benchmark_record(side, 110))

    git(repo, "checkout", main_branch)
    current = commit(repo, "main", "main")

    ancestor = database.nearest_ancestor_record(current, fingerprint, "ecs", 1)
    latest = database.latest_record(fingerprint, "ecs", 1)
    assert ancestor is not None
    ancestor_provenance = ancestor["provenance"]
    assert isinstance(ancestor_provenance, dict)
    assert ancestor_provenance["subject_commit"] == first
    assert latest is not None
    latest_provenance = latest["provenance"]
    assert isinstance(latest_provenance, dict)
    assert latest_provenance["subject_commit"] == side

    database.record(benchmark_record(current, 100))
    exact = database.exact_record(current, fingerprint, "ecs", 1)
    assert exact is not None
    exact_provenance = exact["provenance"]
    assert isinstance(exact_provenance, dict)
    assert exact_provenance["subject_commit"] == current


def test_local_audit_and_list_cli_make_history_inspectable(tmp_path: Path, capsys) -> None:
    repo, head = repository(tmp_path)
    database = LocalBenchmarkDatabase(repo)
    record = benchmark_record(head)
    stored = database.record(record)

    assert main(["--repo", str(repo), "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["record_id"] == record.record_id
    assert listed["path"] == record.expected_path

    assert main(["--repo", str(repo), "audit", "--json"]) == 0
    audited = json.loads(capsys.readouterr().out)
    assert audited["ok"] is True
    assert audited["issues"] == []

    stored.path.write_bytes(
        stored.path.read_bytes().replace(b'"suite_id":"ecs"', b'"suite_id":"bad"')
    )
    issues = database.audit()
    assert len(issues) == 1
    assert issues[0].path == record.expected_path
    assert "invalid local benchmark record" in issues[0].message


def test_record_head_cleanliness_is_checked_before_local_write(tmp_path: Path) -> None:
    repo, head = repository(tmp_path)
    database = LocalBenchmarkDatabase(repo)
    assert database.require_clean_head() == head

    (repo / "untracked.txt").write_text("dirty")
    with pytest.raises(LocalDatabaseError, match="clean worktree"):
        database.require_clean_head()
