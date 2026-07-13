from __future__ import annotations

from pathlib import Path

from benchmarks.framework.git_database.audit import audit_database
from benchmarks.schema.canonical import canonical_json
from benchmarks.schema.records import Revocation
from tests.unit.benchmark_system.test_database_support import (
    commit_file,
    git,
    init_repository,
    integrate_candidate,
    provision_database,
    record,
)


def _authority_worktree(repository: Path, path: Path) -> None:
    git(repository, "worktree", "add", str(path), "benchmark-data-v1")


def _remove_worktree(repository: Path, path: Path) -> None:
    git(repository, "worktree", "remove", "--force", str(path))


def test_audit_accepts_canonical_append_only_record_and_revocation_history(
    tmp_path: Path,
) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)
    stored = record(subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(stored))
    revocation = Revocation(
        stored.record_id,
        "runner qualification was invalid",
        {"reviewer": "benchmark-maintainer", "ticket": "BENCH-3"},
    )
    integrate_candidate(tmp_path, database, database.stage_revocation(revocation))

    assert not audit_database(database)


def test_audit_detects_historical_modification_and_deletion(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    init_repository(repository)
    subject = commit_file(repository, "one", "one")
    database = provision_database(repository)
    stored = record(subject)
    integrate_candidate(repository, database, database.stage_candidate(stored))
    assert not audit_database(database)

    worktree = tmp_path / "authority-worktree"
    _authority_worktree(repository, worktree)
    record_path = worktree / database.record_path(stored)
    record_path.write_bytes(record_path.read_bytes() + b" ")
    git(worktree, "add", database.record_path(stored))
    git(worktree, "commit", "-m", "illegally modify immutable record")
    git(worktree, "rm", database.record_path(stored))
    git(worktree, "commit", "-m", "illegally delete immutable record")
    _remove_worktree(repository, worktree)

    issues = audit_database(database)
    assert any(
        issue.path == database.record_path(stored) and "modified or deleted" in issue.message
        for issue in issues
    )


def test_audit_detects_invalid_paths_hashes_missing_subjects_and_revocations(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    init_repository(repository)
    subject = commit_file(repository, "one", "one")
    database = provision_database(repository)
    stored = record(subject)
    integrate_candidate(repository, database, database.stage_candidate(stored))

    worktree = tmp_path / "authority-worktree"
    _authority_worktree(repository, worktree)

    wrong_record_path = worktree / "records/v1/ff/not-the-key.json"
    wrong_record_path.parent.mkdir(parents=True)
    wrong_record_path.write_bytes(canonical_json(stored.to_dict()))

    bad_fingerprint_id = "a" * 64
    bad_fingerprint_path = (
        worktree / f"fingerprints/v1/{bad_fingerprint_id[:2]}/{bad_fingerprint_id}.json"
    )
    bad_fingerprint_path.parent.mkdir(parents=True)
    bad_fingerprint_path.write_bytes(
        canonical_json(
            {"schema_version": 1, "stable": {"architecture": "x86_64"}, "id": bad_fingerprint_id}
        )
    )

    missing_subject_record = record("0" * database.object_id_length, suite_id="missing")
    missing_subject_path = worktree / database.record_path(missing_subject_record)
    missing_subject_path.parent.mkdir(parents=True)
    missing_subject_path.write_bytes(canonical_json(missing_subject_record.to_dict()))

    invalid_revocation = Revocation(
        "sha256:" + "f" * 64,
        "record never existed",
        {"reviewer": "benchmark-maintainer"},
    )
    invalid_revocation_path = worktree / database.revocation_path(invalid_revocation)
    invalid_revocation_path.parent.mkdir(parents=True)
    invalid_revocation_path.write_bytes(canonical_json(invalid_revocation.to_dict()))

    git(worktree, "add", "fingerprints/v1", "records/v1", "revocations/v1")
    git(worktree, "commit", "-m", "introduce invalid shards")
    _remove_worktree(repository, worktree)

    issues = audit_database(database)
    messages = [issue.message for issue in issues]
    assert any("duplicate immutable primary key" in message for message in messages)
    assert any("path does not match its primary key" in message for message in messages)
    assert any("fingerprint hash mismatch" in message for message in messages)
    assert any("subject commit is missing" in message for message in messages)
    assert any("revocation references no record" in message for message in messages)


def test_audit_checks_declared_baseline_against_nearest_first_parent(tmp_path: Path) -> None:
    init_repository(tmp_path)
    first_subject = commit_file(tmp_path, "one", "one")
    second_subject = commit_file(tmp_path, "two", "two")
    third_subject = commit_file(tmp_path, "three", "three")
    database = provision_database(tmp_path)
    first = record(first_subject)
    second = record(second_subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(first))
    integrate_candidate(tmp_path, database, database.stage_candidate(second))
    third = record(
        third_subject,
        run_conditions={"baseline_record_id": first.record_id},
    )
    integrate_candidate(tmp_path, database, database.stage_candidate(third))

    issues = audit_database(database)
    assert any("not the nearest earlier first-parent record" in issue.message for issue in issues)


def test_audit_local_anchor_detects_rewritten_authority_history(tmp_path: Path) -> None:
    init_repository(tmp_path)
    subject = commit_file(tmp_path, "one", "one")
    database = provision_database(tmp_path)
    stored = record(subject)
    integrate_candidate(tmp_path, database, database.stage_candidate(stored))
    audited_tip = database.data_tip()
    assert not audit_database(database)

    parent = git(tmp_path, "rev-parse", f"{audited_tip}^")
    git(
        tmp_path,
        "update-ref",
        "refs/heads/benchmark-data-v1",
        parent,
        audited_tip,
    )
    issues = audit_database(database)
    assert any("history was rewritten" in issue.message for issue in issues)
