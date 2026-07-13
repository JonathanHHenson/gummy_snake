from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.framework.git_database import DatabaseError
from benchmarks.framework.git_database.audit import audit_database
from benchmarks.framework.git_database.store import GitBenchmarkDatabase
from tests.unit.benchmark_system.test_database_support import (
    commit_file,
    git,
    init_repository,
    integrate_candidate,
    provision_database,
    record,
)


def test_first_parent_lookup_ignores_merge_second_parent_and_supports_detached_head(
    tmp_path: Path,
) -> None:
    init_repository(tmp_path)
    root = commit_file(tmp_path, "root", "root")
    main_branch = git(tmp_path, "branch", "--show-current")
    git(tmp_path, "checkout", "-b", "side", root)
    (tmp_path / "side.txt").write_text("side")
    git(tmp_path, "add", "side.txt")
    git(tmp_path, "commit", "-m", "side")
    side = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", main_branch)
    (tmp_path / "main.txt").write_text("main")
    git(tmp_path, "add", "main.txt")
    git(tmp_path, "commit", "-m", "main")
    git(tmp_path, "merge", "--no-ff", "side", "-m", "merge side")
    merge = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "--orphan", "orphan")
    git(tmp_path, "rm", "-rf", ".")
    (tmp_path / "orphan.txt").write_text("orphan")
    git(tmp_path, "add", "orphan.txt")
    git(tmp_path, "commit", "-m", "orphan")
    orphan = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", main_branch)

    database = provision_database(tmp_path)
    root_record = record(root)
    integrate_candidate(tmp_path, database, database.stage_candidate(root_record))
    side_record = record(side)
    integrate_candidate(tmp_path, database, database.stage_candidate(side_record))
    orphan_record = record(orphan)
    integrate_candidate(tmp_path, database, database.stage_candidate(orphan_record))

    git(tmp_path, "checkout", "--detach", merge)
    assert database.head() == merge
    baseline = database.nearest_first_parent_record(merge, root_record.fingerprint.id, "canvas", 1)
    assert baseline is not None
    assert baseline["record_id"] == root_record.record_id
    assert baseline["record_id"] not in {side_record.record_id, orphan_record.record_id}


def test_shallow_repository_is_an_infrastructure_error(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repository(source)
    commit_file(source, "one", "one")
    commit_file(source, "two", "two")
    provision_database(source)

    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "--bare")
    git(source, "remote", "add", "origin", str(bare))
    git(source, "push", "origin", "HEAD", "refs/heads/benchmark-data-v1")

    shallow = tmp_path / "shallow"
    git(
        tmp_path,
        "clone",
        "--depth",
        "1",
        "--no-single-branch",
        f"file://{bare}",
        str(shallow),
    )
    remote_tip = git(shallow, "rev-parse", "refs/remotes/origin/benchmark-data-v1")
    git(shallow, "update-ref", "refs/heads/benchmark-data-v1", remote_tip)

    with pytest.raises(DatabaseError, match="must not be shallow"):
        GitBenchmarkDatabase(shallow).require_authoritative_ready()


def test_replacement_refs_are_rejected_even_though_git_commands_disable_them(
    tmp_path: Path,
) -> None:
    init_repository(tmp_path)
    original = commit_file(tmp_path, "one", "one")
    replacement = commit_file(tmp_path, "two", "two")
    provision_database(tmp_path)
    git(tmp_path, "replace", original, replacement)

    with pytest.raises(DatabaseError, match="replacement refs"):
        GitBenchmarkDatabase(tmp_path).first_parent_commits(replacement)


def test_sha256_repository_uses_full_object_ids_when_supported(tmp_path: Path) -> None:
    try:
        init_repository(tmp_path, object_format="sha256")
    except AssertionError as error:
        pytest.skip(f"installed Git lacks SHA-256 repository support: {error}")
    subject = commit_file(tmp_path, "sha256", "sha256 root")
    database = provision_database(tmp_path)
    stored = record(subject)
    staged = database.stage_candidate(stored)
    integrate_candidate(tmp_path, database, staged)

    assert database.object_format == "sha256"
    assert len(subject) == 64
    assert database.exact_record(subject, stored.fingerprint.id, "canvas", 1) is not None
    assert not audit_database(database)


def test_fetch_requires_exact_ref_and_only_fast_forwards(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repository(source)
    subject = commit_file(source, "one", "one")
    source_database = provision_database(source)

    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "--bare")
    git(source, "remote", "add", "origin", str(bare))
    git(source, "push", "origin", "HEAD", "refs/heads/benchmark-data-v1")

    local = tmp_path / "local"
    git(tmp_path, "clone", str(bare), str(local))
    local_database = GitBenchmarkDatabase(local)
    first_tip = local_database.fetch_authoritative_ref("origin")
    assert first_tip == source_database.data_tip()

    integrate_candidate(source, source_database, source_database.stage_candidate(record(subject)))
    git(source, "push", "origin", "refs/heads/benchmark-data-v1")
    second_tip = local_database.fetch_authoritative_ref("origin")
    assert second_tip == source_database.data_tip()
    assert second_tip != first_tip

    missing = tmp_path / "missing.git"
    missing.mkdir()
    git(missing, "init", "--bare")
    with pytest.raises(DatabaseError, match="failed to fetch required"):
        local_database.fetch_authoritative_ref(str(missing))


def test_fetch_rejects_divergence_and_stale_checked_out_authority(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repository(source)
    subject = commit_file(source, "one", "one")
    source_database = provision_database(source)
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "--bare")
    git(source, "remote", "add", "origin", str(bare))
    git(source, "push", "origin", "HEAD", "refs/heads/benchmark-data-v1")

    local = tmp_path / "local"
    git(tmp_path, "clone", str(bare), str(local))
    git(local, "config", "user.email", "test@example.test")
    git(local, "config", "user.name", "Benchmark Test")
    local_database = GitBenchmarkDatabase(local)
    local_database.fetch_authoritative_ref("origin")

    local_candidate = local_database.stage_candidate(record(subject, suite_id="local"))
    integrate_candidate(local, local_database, local_candidate)
    remote_candidate = source_database.stage_candidate(record(subject, suite_id="remote"))
    integrate_candidate(source, source_database, remote_candidate)
    git(source, "push", "origin", "refs/heads/benchmark-data-v1")

    with pytest.raises(DatabaseError, match="diverged"):
        local_database.fetch_authoritative_ref("origin")

    checked = tmp_path / "checked"
    git(tmp_path, "clone", str(bare), str(checked))
    git(checked, "config", "user.email", "test@example.test")
    git(checked, "config", "user.name", "Benchmark Test")
    checked_database = GitBenchmarkDatabase(checked)
    checked_database.fetch_authoritative_ref("origin")
    git(checked, "checkout", "benchmark-data-v1")

    newer = source_database.stage_candidate(record(subject, suite_id="newer"))
    integrate_candidate(source, source_database, newer)
    git(source, "push", "origin", "refs/heads/benchmark-data-v1")
    with pytest.raises(DatabaseError, match="checked-out benchmark-data-v1 worktree is stale"):
        checked_database.fetch_authoritative_ref("origin")
