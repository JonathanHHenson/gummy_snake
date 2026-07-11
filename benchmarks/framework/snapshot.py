"""Deterministic declared-root source snapshots for isolated benchmark builds."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..schema.canonical import content_hash


class SnapshotError(RuntimeError):
    """A declared build input cannot be safely represented by the source snapshot."""


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    path: str
    mode: int
    kind: str
    digest: str


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    head: str
    entries: tuple[SnapshotEntry, ...]
    digest: str
    declared_roots: tuple[str, ...]


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if check and result.returncode:
        raise SnapshotError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _relative_root(repository: Path, root: str) -> Path:
    candidate = Path(root)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SnapshotError(f"declared root must be a repository-relative path: {root}")
    resolved = (repository / candidate).resolve()
    try:
        resolved.relative_to(repository.resolve())
    except ValueError as error:
        raise SnapshotError(f"declared root escapes repository: {root}") from error
    if not resolved.exists() and not resolved.is_symlink():
        raise SnapshotError(f"declared root does not exist: {root}")
    return candidate


def _ignored(repository: Path, relative: Path) -> bool:
    result = subprocess.run(
        ("git", "-C", str(repository), "check-ignore", "-q", "--", relative.as_posix()),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _tracked(repository: Path, relative: Path) -> bool:
    result = subprocess.run(
        ("git", "-C", str(repository), "ls-files", "--error-unmatch", "--", relative.as_posix()),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _entry(repository: Path, relative: Path) -> SnapshotEntry:
    candidate = repository / relative
    status = candidate.lstat()
    mode = status.st_mode & 0o7777
    if candidate.is_symlink():
        payload = os.readlink(candidate).encode("utf-8", "surrogateescape")
        kind = "symlink"
    elif candidate.is_file():
        payload = candidate.read_bytes()
        kind = "file"
    else:
        raise SnapshotError(f"unsupported declared input type: {relative}")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return SnapshotEntry(relative.as_posix(), mode, kind, digest)


def snapshot_declared_roots(repository: Path, roots: Iterable[str]) -> SourceSnapshot:
    """Hash all tracked and non-ignored untracked regular files under declared roots.

    The working-tree bytes are always used, so staged and unstaged edits are both
    represented. Git's ignore rules are used only for untracked files; tracked files
    remain inputs even if a later ignore rule matches them.
    """

    repository = repository.resolve()
    declared = tuple(sorted({_relative_root(repository, root).as_posix() for root in roots}))
    if not declared:
        raise SnapshotError("at least one catalog-declared source root is required")
    files: set[Path] = set()
    for root_text in declared:
        root = repository / root_text
        if root.is_symlink() or root.is_file():
            files.add(Path(root_text))
            continue
        for current, directories, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            directories[:] = sorted(directories)
            for name in sorted(names):
                absolute = current_path / name
                relative = absolute.relative_to(repository)
                if (absolute.is_symlink() or absolute.is_file()) and (
                    _tracked(repository, relative) or not _ignored(repository, relative)
                ):
                    files.add(relative)
    entries = tuple(_entry(repository, relative) for relative in sorted(files))
    head = _git(repository, "rev-parse", "--verify", "HEAD^{commit}")
    digest = content_hash(
        {
            "head": head,
            "roots": list(declared),
            "entries": [
                {"path": item.path, "mode": item.mode, "kind": item.kind, "digest": item.digest}
                for item in entries
            ],
        }
    )
    return SourceSnapshot(head=head, entries=entries, digest=digest, declared_roots=declared)


def require_referenced_input(snapshot: SourceSnapshot, path: str) -> None:
    """Reject build inputs not included by declared catalog roots."""

    if path not in {entry.path for entry in snapshot.entries}:
        raise SnapshotError(f"referenced build input lies outside declared snapshot roots: {path}")
