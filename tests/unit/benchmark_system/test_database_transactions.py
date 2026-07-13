from __future__ import annotations

from pathlib import Path

import pytest

import benchmarks.framework.git_database.transactions as transaction_module
from benchmarks.framework.git_database import DatabaseError
from benchmarks.schema.records import Revocation
from tests.unit.benchmark_system.test_database_support import (
    commit_file,
    git,
    init_repository,
    integrate_candidate,
    provision_database,
    record,
)


def test_stale_captured_tip_merges_distinct_key_when_baseline_is_unchanged(
    tmp_path: Path,
) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)
    captured = database.data_tip()

    first = database.stage_candidate(record(subject, suite_id="canvas"), captured_tip=captured)
    integrate_candidate(tmp_path, database, first)
    second = database.stage_candidate(record(subject, suite_id="ecs"), captured_tip=captured)

    assert git(tmp_path, "rev-parse", f"{second.commit}^") == database.data_tip()
    assert database._show(database.record_path(record(subject, suite_id="ecs")), second.commit)


def test_stale_captured_tip_requires_rerun_when_nearest_baseline_changes(
    tmp_path: Path,
) -> None:
    init_repository(tmp_path)
    first_subject = commit_file(tmp_path, "one", "one")
    second_subject = commit_file(tmp_path, "two", "two")
    third_subject = commit_file(tmp_path, "three", "three")
    database = provision_database(tmp_path)

    first_record = record(first_subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(first_record))
    captured = database.data_tip()
    second_record = record(second_subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(second_record))

    with pytest.raises(DatabaseError, match="baseline changed.*rerun comparison"):
        database.stage_candidate(record(third_subject), captured_tip=captured)


def test_same_primary_key_is_first_writer_wins_even_after_revocation(tmp_path: Path) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)
    stored = record(subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(stored))

    with pytest.raises(DatabaseError, match="first writer wins"):
        database.stage_candidate(stored)

    revocation = Revocation(
        stored.record_id,
        "invalid controlled-run setup",
        {"reviewer": "benchmark-maintainer", "ticket": "BENCH-1"},
    )
    integrate_candidate(tmp_path, database, database.stage_revocation(revocation))
    assert database.is_revoked(stored.record_id)
    assert database.exact_record(subject, stored.fingerprint.id, "canvas", 1) is None
    with pytest.raises(DatabaseError, match="first writer wins"):
        database.stage_candidate(stored)


def test_revocation_must_target_an_authoritative_record_and_is_additive(tmp_path: Path) -> None:
    init_repository(tmp_path)
    first_subject = commit_file(tmp_path, "one", "one")
    second_subject = commit_file(tmp_path, "two", "two")
    database = provision_database(tmp_path)
    stored = record(first_subject)

    unknown = Revocation(
        "sha256:" + "1" * 64,
        "unknown result",
        {"reviewer": "benchmark-maintainer"},
    )
    with pytest.raises(DatabaseError, match="target is not present"):
        database.stage_revocation(unknown)

    integrate_candidate(tmp_path, database, database.stage_candidate(stored))
    revocation = Revocation(
        stored.record_id,
        "superseded after fixture audit",
        {"reviewer": "benchmark-maintainer", "approval": "BENCH-2"},
    )
    staged = database.stage_revocation(revocation)
    assert database.revocation_path(revocation).startswith(
        f"revocations/v1/{revocation.id.split(':', 1)[1][:2]}/"
    )
    competing = Revocation(
        stored.record_id,
        "competing correction before protected review",
        {"reviewer": "other-maintainer"},
    )
    with pytest.raises(DatabaseError, match="candidate branch already exists"):
        database.stage_revocation(competing)
    integrate_candidate(tmp_path, database, staged)

    assert (
        database.nearest_first_parent_record(second_subject, stored.fingerprint.id, "canvas", 1)
        is None
    )
    duplicate = Revocation(
        stored.record_id,
        "second attempt",
        {"reviewer": "other-maintainer"},
    )
    with pytest.raises(DatabaseError, match="already revoked"):
        database.stage_revocation(duplicate)


def test_failed_transaction_leaves_no_ref_partial_file_or_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)
    stored = record(subject)
    authority_tip = database.data_tip()
    real_atomic_write = transaction_module.atomic_write
    calls = 0

    def interrupted(path: Path, payload: bytes) -> None:
        nonlocal calls
        real_atomic_write(path, payload)
        calls += 1
        if calls == 1:
            raise OSError("simulated recorder crash")

    monkeypatch.setattr(transaction_module, "atomic_write", interrupted)
    with pytest.raises(OSError, match="simulated recorder crash"):
        database.stage_candidate(stored)

    assert database.data_tip() == authority_tip
    branch_ref = f"refs/heads/{database.candidate_branch(stored)}"
    assert not git(tmp_path, "show-ref", "--verify", branch_ref, check=False)
    assert "benchmark-data-v1-worktree-" not in git(tmp_path, "worktree", "list", "--porcelain")


def test_repository_common_lock_rejects_an_overlapping_local_writer(tmp_path: Path) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)

    with database._lock(), pytest.raises(DatabaseError, match="holds the database lock"):
        database.stage_candidate(record(subject))


def test_candidate_remote_publication_uses_first_writer_wins_without_pushing_authority(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    init_repository(repository)
    subject = commit_file(repository, "one", "one")
    database = provision_database(repository)
    candidate = database.stage_candidate(record(subject))
    authority_tip = database.data_tip()

    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    database.push_candidate(candidate, str(remote))

    assert git(remote, "rev-parse", f"refs/heads/{candidate.branch}") == candidate.commit
    assert not git(
        remote,
        "show-ref",
        "--verify",
        "refs/heads/benchmark-data-v1",
        check=False,
    )
    assert database.data_tip() == authority_tip
    with pytest.raises(DatabaseError, match="already has a first writer"):
        database.push_candidate(candidate, str(remote))
