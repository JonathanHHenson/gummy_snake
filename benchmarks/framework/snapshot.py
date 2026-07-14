"""Deterministic declared-root source snapshots for isolated benchmark builds."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable, Mapping
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
    tree_digest: str
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


def _tracked_paths(repository: Path, roots: Iterable[str]) -> frozenset[Path]:
    """Read tracked paths for all declared roots in one Git invocation."""

    result = subprocess.run(
        ("git", "-C", str(repository), "ls-files", "-z", "--", *roots),
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise SnapshotError("could not enumerate tracked declared snapshot inputs")
    return frozenset(Path(item) for item in result.stdout.decode("utf-8").split("\0") if item)


def _entry_payload(repository: Path, relative: Path) -> tuple[int, str, bytes]:
    candidate = repository / relative
    try:
        status = candidate.lstat()
    except OSError as error:
        raise SnapshotError(f"declared input disappeared while snapshotting: {relative}") from error
    mode = status.st_mode & 0o7777
    if candidate.is_symlink():
        target = os.readlink(candidate)
        target_path = Path(target)
        if target_path.is_absolute():
            raise SnapshotError(f"declared symlink target must be repository-relative: {relative}")
        resolved_target = (candidate.parent / target_path).resolve()
        try:
            resolved_target.relative_to(repository.resolve())
        except ValueError as error:
            raise SnapshotError(f"declared symlink escapes repository: {relative}") from error
        return mode, "symlink", target.encode("utf-8", "surrogateescape")
    if candidate.is_file():
        return mode, "file", candidate.read_bytes()
    raise SnapshotError(f"unsupported declared input type: {relative}")


def _entry(repository: Path, relative: Path) -> SnapshotEntry:
    mode, kind, payload = _entry_payload(repository, relative)
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
    tracked = _tracked_paths(repository, declared)
    files: set[Path] = {
        relative
        for relative in tracked
        if (repository / relative).is_file() or (repository / relative).is_symlink()
    }
    for root_text in declared:
        root = repository / root_text
        if root.is_symlink() or root.is_file():
            files.add(Path(root_text))
            continue
        for current, directories, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            # Never descend ignored build/output trees (notably Rust target/). Git's
            # tracked set remains canonical for files that are actually inputs.
            descend: list[str] = []
            for name in sorted(directories):
                absolute = current_path / name
                relative = absolute.relative_to(repository)
                if absolute.is_symlink():
                    if relative in tracked or not _ignored(repository, relative):
                        files.add(relative)
                elif relative in tracked or not _ignored(repository, relative):
                    descend.append(name)
            directories[:] = descend
            for name in sorted(names):
                absolute = current_path / name
                relative = absolute.relative_to(repository)
                if (absolute.is_symlink() or absolute.is_file()) and (
                    relative in tracked or not _ignored(repository, relative)
                ):
                    files.add(relative)
    declared_paths = tuple(Path(root) for root in declared)
    for relative in files:
        candidate = repository / relative
        if not candidate.is_symlink():
            continue
        target = Path(os.readlink(candidate))
        resolved = Path(os.path.normpath((relative.parent / target).as_posix()))
        if not any(resolved == root or resolved.is_relative_to(root) for root in declared_paths):
            raise SnapshotError(
                f"declared symlink references input outside snapshot roots: {relative}"
            )
        if not (repository / resolved).exists() and not (repository / resolved).is_symlink():
            raise SnapshotError(f"declared symlink target does not exist: {relative}")
    entries = tuple(_entry(repository, relative) for relative in sorted(files))
    head = _git(repository, "rev-parse", "--verify", "HEAD^{commit}")
    tree_payload = {
        "roots": list(declared),
        "entries": [
            {"path": item.path, "mode": item.mode, "kind": item.kind, "digest": item.digest}
            for item in entries
        ],
    }
    tree_digest = content_hash(tree_payload)
    digest = content_hash({"head": head, "tree_digest": tree_digest})
    return SourceSnapshot(
        head=head,
        entries=entries,
        digest=digest,
        tree_digest=tree_digest,
        declared_roots=declared,
    )


def require_referenced_input(snapshot: SourceSnapshot, path: str) -> None:
    """Reject build inputs not included by declared catalog roots."""

    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SnapshotError(f"referenced build input lies outside declared snapshot roots: {path}")
    normalized = candidate.as_posix()
    entries = {entry.path for entry in snapshot.entries}
    roots = tuple(Path(root) for root in snapshot.declared_roots)
    represented = normalized in entries or any(
        normalized == root.as_posix()
        or (
            root.as_posix() not in entries
            and candidate.is_relative_to(root)
            and any(Path(entry).is_relative_to(candidate) for entry in entries)
        )
        for root in roots
    )
    if not represented:
        raise SnapshotError(
            f"referenced build input lies outside declared snapshot roots: {normalized}"
        )


def verify_materialized_source(snapshot: SourceSnapshot, directory: Path) -> None:
    """Require a materialized tree to contain exactly the recorded entries and modes."""

    directory = directory.resolve()
    files: set[Path] = set()
    for root_text in snapshot.declared_roots:
        root = directory / root_text
        if not root.exists() and not root.is_symlink():
            raise SnapshotError(f"materialized source is missing declared root: {root_text}")
        if root.is_file() or root.is_symlink():
            files.add(Path(root_text))
            continue
        for current, directories, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            descend: list[str] = []
            for name in sorted(directories):
                candidate = current_path / name
                if candidate.is_symlink():
                    files.add(candidate.relative_to(directory))
                else:
                    descend.append(name)
            directories[:] = descend
            files.update(
                (current_path / name).relative_to(directory)
                for name in sorted(names)
                if (current_path / name).is_file() or (current_path / name).is_symlink()
            )
    entries = tuple(_entry(directory, relative) for relative in sorted(files))
    if entries != snapshot.entries:
        raise SnapshotError("materialized source tree no longer matches its immutable snapshot")


def validate_referenced_build_inputs(repository: Path, snapshot: SourceSnapshot) -> None:
    """Require configured Python/Rust build inputs to be represented by the snapshot."""

    repository = repository.resolve()
    pyproject_path = repository / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as source:
            raw = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SnapshotError(f"cannot inspect pyproject build inputs: {error}") from error
    references: set[str] = {"pyproject.toml", "Cargo.toml", "Cargo.lock", "uv.lock"}
    project = raw.get("project")
    if isinstance(project, Mapping):
        readme = project.get("readme")
        if isinstance(readme, str):
            references.add(readme)
        license_files = project.get("license-files")
        if isinstance(license_files, list):
            for pattern in license_files:
                if isinstance(pattern, str):
                    matches = [path for path in repository.glob(pattern) if path.is_file()]
                    references.update(path.relative_to(repository).as_posix() for path in matches)
    tool = raw.get("tool")
    maturin = tool.get("maturin") if isinstance(tool, Mapping) else None
    if isinstance(maturin, Mapping):
        for key in ("manifest-path", "python-source"):
            value = maturin.get(key)
            if isinstance(value, str):
                references.add(value)
        includes = maturin.get("include")
        if isinstance(includes, list):
            for pattern in includes:
                if not isinstance(pattern, str):
                    continue
                matches = [path for path in repository.glob(pattern) if path.is_file()]
                if not matches:
                    raise SnapshotError(f"configured build include matches no input: {pattern}")
                references.update(path.relative_to(repository).as_posix() for path in matches)
    for reference in sorted(references):
        require_referenced_input(snapshot, reference)

    manifest_entries = [entry for entry in snapshot.entries if entry.path.endswith("Cargo.toml")]
    for entry in manifest_entries:
        manifest_path = repository / entry.path
        try:
            with manifest_path.open("rb") as source:
                manifest = tomllib.load(source)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise SnapshotError(
                f"cannot inspect Rust build inputs in {entry.path}: {error}"
            ) from error
        for table_name in ("dependencies", "dev-dependencies", "build-dependencies"):
            table = manifest.get(table_name)
            if not isinstance(table, Mapping):
                continue
            for dependency in table.values():
                if not isinstance(dependency, Mapping) or not isinstance(
                    dependency.get("path"), str
                ):
                    continue
                relative = (Path(entry.path).parent / str(dependency["path"])).as_posix()
                normalized = Path(os.path.normpath(relative)).as_posix()
                require_referenced_input(snapshot, normalized)


def materialize_source_snapshot(
    repository: Path, snapshot: SourceSnapshot, destination: Path
) -> Path:
    """Copy verified snapshot bytes into a tool-owned tree independent of the live checkout.

    Every copied payload is checked against the recorded digest. A second snapshot rejects
    additions, removals, mode changes, and edits that occurred between planning and copying.
    """

    repository = repository.resolve()
    destination = destination.resolve()
    try:
        destination.relative_to(repository)
    except ValueError:
        pass
    else:
        raise SnapshotError("materialized benchmark source must be outside the live repository")
    current = snapshot_declared_roots(repository, snapshot.declared_roots)
    if current != snapshot:
        raise SnapshotError("live repository changed while materializing benchmark source snapshot")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for entry in snapshot.entries:
            relative = Path(entry.path)
            mode, kind, payload = _entry_payload(repository, relative)
            digest = "sha256:" + hashlib.sha256(payload).hexdigest()
            if (mode, kind, digest) != (entry.mode, entry.kind, entry.digest):
                raise SnapshotError(f"declared input changed while materializing: {entry.path}")
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "symlink":
                target.symlink_to(payload.decode("utf-8", "surrogateescape"))
            else:
                target.write_bytes(payload)
                target.chmod(entry.mode)
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        temporary.replace(destination)
        verify_materialized_source(snapshot, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination
