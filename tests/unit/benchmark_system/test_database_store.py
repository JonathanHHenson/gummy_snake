from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.framework.git_database import DatabaseError
from benchmarks.framework.git_database.audit import audit_database
from benchmarks.framework.git_database.store import GitBenchmarkDatabase
from tests.unit.benchmark_system.test_database_support import git, record


def test_missing_authoritative_ref_is_an_actionable_infrastructure_error(tmp_path: Path) -> None:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.test")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "code.txt").write_text("a")
    git(tmp_path, "add", "code.txt")
    git(tmp_path, "commit", "-m", "first")

    with pytest.raises(DatabaseError, match="authoritative benchmark data ref"):
        GitBenchmarkDatabase(tmp_path).data_tip()


def test_stage_candidate_writes_immutable_shards_without_advancing_authority(
    tmp_path: Path,
) -> None:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.test")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "code.txt").write_text("a")
    git(tmp_path, "add", "code.txt")
    git(tmp_path, "commit", "-m", "first")
    subject = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "branch", "benchmark-data-v1")
    database = GitBenchmarkDatabase(tmp_path)
    stored = record(subject)
    authority_tip = database.data_tip()
    staged = database.stage_candidate(stored)

    assert staged.branch == (
        f"benchmark-record/{subject[:12]}-{stored.fingerprint.id[:12]}-canvas-v1"
    )
    assert git(tmp_path, "rev-parse", "refs/heads/benchmark-data-v1") == authority_tip
    assert git(tmp_path, "rev-parse", staged.branch) == staged.commit
    assert git(tmp_path, "rev-parse", f"{staged.commit}^") == authority_tip
    assert database.exact_record(subject, stored.fingerprint.id, "canvas", 1) is None
    assert database.record_path(stored).startswith(
        f"records/v1/{stored.fingerprint.id[:2]}/{stored.fingerprint.id}/{subject[:2]}/"
    )
    assert database.fingerprint_path(stored.fingerprint.id).startswith(
        f"fingerprints/v1/{stored.fingerprint.id[:2]}/"
    )
    assert database._show(database.record_path(stored), staged.commit) is not None
    assert "Benchmark-Subject: " + subject in git(
        tmp_path, "show", "-s", "--format=%B", staged.commit
    )
    assert not audit_database(database)
    with pytest.raises(DatabaseError, match="candidate branch already exists"):
        database.stage_candidate(stored)
    with pytest.raises(DatabaseError):
        GitBenchmarkDatabase(tmp_path, "refs/heads/other")
