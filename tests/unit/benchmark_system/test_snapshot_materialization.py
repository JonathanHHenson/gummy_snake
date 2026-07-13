from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from benchmarks.framework.snapshot import (
    SnapshotError,
    materialize_source_snapshot,
    require_referenced_input,
    snapshot_declared_roots,
    verify_materialized_source,
)


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "benchmark@example.invalid")
    _git(repository, "config", "user.name", "Benchmark Test")
    (repository / ".gitignore").write_text("src/ignored/\n")
    source = repository / "src"
    source.mkdir()
    tracked = source / "tracked.py"
    tracked.write_text("original\n")
    tracked.chmod(0o755)
    _git(repository, "add", ".gitignore", "src/tracked.py")
    _git(repository, "commit", "-qm", "initial")
    return repository


def test_snapshot_materializes_exact_worktree_modes_symlinks_and_untracked_files(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    tracked = repository / "src" / "tracked.py"
    tracked.write_text("staged\n")
    _git(repository, "add", "src/tracked.py")
    tracked.write_text("unstaged\n")
    untracked = repository / "src" / "fixture.bin"
    untracked.write_bytes(b"fixture")
    ignored = repository / "src" / "ignored"
    ignored.mkdir()
    (ignored / "output.bin").write_bytes(b"ignored")
    link = repository / "src" / "fixture-link"
    try:
        link.symlink_to("fixture.bin")
    except OSError:
        pytest.skip("platform does not permit test symlinks")

    snapshot = snapshot_declared_roots(repository, ("src",))
    destination = materialize_source_snapshot(repository, snapshot, tmp_path / "materialized")
    entries = {entry.path: entry for entry in snapshot.entries}

    assert (destination / "src" / "tracked.py").read_text() == "unstaged\n"
    assert entries["src/tracked.py"].mode & 0o111
    assert (destination / "src" / "fixture.bin").read_bytes() == b"fixture"
    assert os.readlink(destination / "src" / "fixture-link") == "fixture.bin"
    assert "src/ignored/output.bin" not in entries
    assert snapshot.digest != snapshot.tree_digest
    verify_materialized_source(snapshot, destination)
    (destination / "src" / "post-build.py").write_text("mutation\n")
    with pytest.raises(SnapshotError, match="no longer matches"):
        verify_materialized_source(snapshot, destination)


def test_materialization_rejects_live_tree_mutation_and_escaping_symlink(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    snapshot = snapshot_declared_roots(repository, ("src",))
    (repository / "src" / "added.py").write_text("changed\n")

    with pytest.raises(SnapshotError, match="changed while materializing"):
        materialize_source_snapshot(repository, snapshot, tmp_path / "materialized")

    (repository / "src" / "added.py").unlink()
    escaping = repository / "src" / "escape"
    try:
        escaping.symlink_to("../../outside")
    except OSError:
        pytest.skip("platform does not permit test symlinks")
    with pytest.raises(SnapshotError, match="symlink"):
        snapshot_declared_roots(repository, ("src",))

    escaping.unlink()
    (repository / "external-build-input.txt").write_text("outside root\n")
    escaping.symlink_to("../external-build-input.txt")
    with pytest.raises(SnapshotError, match="outside snapshot roots"):
        snapshot_declared_roots(repository, ("src",))


def test_referenced_inputs_must_be_represented_by_declared_roots(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "outside.toml").write_text("input = true\n")
    snapshot = snapshot_declared_roots(repository, ("src",))

    require_referenced_input(snapshot, "src/tracked.py")
    with pytest.raises(SnapshotError, match="outside declared snapshot roots"):
        require_referenced_input(snapshot, "outside.toml")
