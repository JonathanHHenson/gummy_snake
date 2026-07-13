"""Atomic local staging and lease-guarded candidate publication."""

from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

from ...schema.canonical import canonical_json
from ...schema.records import BenchmarkRecord, Revocation
from . import DatabaseError, StagedCandidate
from .git_operations import git, git_result, git_succeeded
from .paths import hash_digest, is_lower_hex, validate_suite

if TYPE_CHECKING:
    from .store import GitBenchmarkDatabase


def fsync_directory(path: Path) -> None:
    """Best-effort fsync a directory after an atomic filesystem transition."""

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        with suppress(OSError):
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes) -> None:
    """Flush and atomically rename a temporary file into its final path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fsync_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            with suppress(OSError):
                os.fsync(output.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _lock_descriptor(descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised by Windows benchmark runners
        import msvcrt

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        locking = getattr(msvcrt, "locking", None)
        lock_mode = getattr(msvcrt, "LK_NBLCK", None)
        if not callable(locking) or not isinstance(lock_mode, int):
            raise DatabaseError("Windows runtime does not expose file locking")
        try:
            locking(descriptor, lock_mode, 1)
        except OSError as error:
            raise DatabaseError(
                "another local benchmark recorder holds the database lock"
            ) from error
        return

    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EAGAIN):
            raise DatabaseError(
                "another local benchmark recorder holds the database lock"
            ) from error
        raise


def _unlock_descriptor(descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised by Windows benchmark runners
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        locking = getattr(msvcrt, "locking", None)
        unlock_mode = getattr(msvcrt, "LK_UNLCK", None)
        if callable(locking) and isinstance(unlock_mode, int):
            with suppress(OSError):
                locking(descriptor, unlock_mode, 1)
        return

    import fcntl

    with suppress(OSError):
        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def repository_lock(common_directory: Path) -> Iterator[None]:
    """Hold the process-safe recorder lock in the repository common directory."""

    lock_path = common_directory / "benchmark-data-v1.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _lock_descriptor(descriptor)
        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        with suppress(OSError):
            os.fsync(descriptor)
        fsync_directory(common_directory)
        yield
    finally:
        _unlock_descriptor(descriptor)
        os.close(descriptor)


def candidate_branch(record: BenchmarkRecord) -> str:
    """Return the deterministic first-writer branch for a record primary key."""

    subject, fingerprint, suite_id, suite_version = record.primary_key
    if len(subject) not in {40, 64} or not is_lower_hex(subject):
        raise DatabaseError("benchmark subject commit must be a full lowercase Git object id")
    if len(fingerprint) != 64 or not is_lower_hex(fingerprint):
        raise DatabaseError("benchmark fingerprint must be a hexadecimal content id")
    validate_suite(suite_id)
    return f"benchmark-record/{subject[:12]}-{fingerprint[:12]}-{suite_id}-v{suite_version}"


def revocation_branch(revocation: Revocation) -> str:
    """Return the deterministic first-writer branch for a revoked record key."""

    target_digest = hash_digest(revocation.record_id, field="revoked record id")
    return f"benchmark-revocation/{target_digest[:16]}"


def record_id(record: dict[str, object] | None) -> str | None:
    """Extract a validated record identifier for baseline concurrency checks."""

    if record is None:
        return None
    value = record.get("record_id")
    return value if isinstance(value, str) else None


def _assert_captured_tip(
    database: GitBenchmarkDatabase, captured_tip: str, current_tip: str
) -> None:
    database._validate_object_id(captured_tip, field="captured database tip")
    database._commit_id(captured_tip, field="captured database tip")
    if captured_tip != current_tip and not database._is_ancestor(captured_tip, current_tip):
        raise DatabaseError(
            "authoritative database history changed non-fast-forward since it was captured"
        )


def stage_files(
    database: GitBenchmarkDatabase,
    *,
    tip: str,
    branch: str,
    files: Mapping[str, bytes],
    message: Sequence[str],
) -> StagedCandidate:
    """Commit immutable files in a verified temporary detached worktree."""

    branch_ref = f"refs/heads/{branch}"
    if git_succeeded(database.repository, "rev-parse", "--verify", branch_ref):
        raise DatabaseError(f"candidate branch already exists: {branch}")
    temporary = Path(tempfile.mkdtemp(prefix="benchmark-data-v1-worktree-"))
    added = False
    try:
        git(database.repository, "worktree", "add", "--detach", str(temporary), tip)
        added = True
        if git(temporary, "rev-parse", "HEAD") != tip:
            raise DatabaseError("temporary benchmark worktree was not rooted at the captured tip")
        for path, payload in files.items():
            target = temporary / path
            if target.exists():
                raise DatabaseError(f"immutable shard already exists in staged tree: {path}")
            atomic_write(target, payload)
            if target.read_bytes() != payload:
                raise DatabaseError(f"atomic shard verification failed: {path}")
        expected_status = {f"?? {path}" for path in files}
        status = {
            line
            for line in git(
                temporary, "status", "--porcelain", "--untracked-files=all"
            ).splitlines()
            if line
        }
        if status != expected_status:
            raise DatabaseError(
                "temporary data worktree contains changes outside the immutable transaction"
            )
        ordered_paths = sorted(files)
        git(temporary, "add", "--", *ordered_paths)
        commit_arguments: list[str] = ["commit", "-m", message[0]]
        if len(message) > 1:
            commit_arguments.extend(("-m", "\n".join(message[1:])))
        git(temporary, *commit_arguments)
        commit = database._validate_object_id(
            git(temporary, "rev-parse", "HEAD"), field="candidate commit"
        )
        parents = git(temporary, "show", "-s", "--format=%P", commit).split()
        if parents != [tip]:
            raise DatabaseError("candidate commit is not a single-parent child of the captured tip")
        if git(temporary, "status", "--porcelain", "--untracked-files=all"):
            raise DatabaseError("temporary data worktree is not clean after candidate commit")
        for path, payload in files.items():
            if database._show(path, commit) != payload:
                raise DatabaseError(f"committed shard verification failed: {path}")
        if database.data_tip() != tip:
            raise DatabaseError(
                "database tip changed during candidate staging; rerun baseline resolution"
            )
        git(database.repository, "update-ref", branch_ref, commit, "")
        return StagedCandidate(branch=branch, commit=commit)
    finally:
        if added:
            git(
                database.repository,
                "worktree",
                "remove",
                "--force",
                str(temporary),
                check=False,
            )
        with suppress(OSError):
            temporary.rmdir()
        git(database.repository, "worktree", "prune", check=False)


def stage_candidate(
    database: GitBenchmarkDatabase,
    record: BenchmarkRecord,
    *,
    captured_tip: str | None = None,
) -> StagedCandidate:
    """Stage a record after revalidating its captured tip and nearest baseline."""

    database.require_complete_history()
    initial_tip = captured_tip or database.data_tip()
    database._validate_object_id(initial_tip, field="captured database tip")
    subject, fingerprint_id, suite_id, suite_version = record.primary_key
    database._validate_object_id(subject, field="benchmark subject commit")
    database._commit_id(subject, field="benchmark subject commit")
    branch = candidate_branch(record)
    record_path = database.record_path(record)
    fingerprint_path = database.fingerprint_path(fingerprint_id)
    fingerprint_payload = canonical_json(record.fingerprint.to_dict())
    with database._lock():
        current_tip = database.data_tip()
        _assert_captured_tip(database, initial_tip, current_tip)
        if initial_tip != current_tip:
            previous_baseline = database._nearest_record_at(
                initial_tip, subject, fingerprint_id, suite_id, suite_version
            )
            current_baseline = database._nearest_record_at(
                current_tip, subject, fingerprint_id, suite_id, suite_version
            )
            if record_id(previous_baseline) != record_id(current_baseline):
                raise DatabaseError(
                    "nearest first-parent baseline changed after the database tip was "
                    "captured; rerun comparison before staging"
                )
        if (
            database._exact_record_at(
                current_tip,
                subject,
                fingerprint_id,
                suite_id,
                suite_version,
                include_revoked=True,
            )
            is not None
        ):
            raise DatabaseError("immutable record key already exists; first writer wins")
        existing_fingerprint = database._show(fingerprint_path, current_tip)
        if existing_fingerprint is not None:
            database._validated_fingerprint(fingerprint_path, existing_fingerprint)
            if existing_fingerprint != fingerprint_payload:
                raise DatabaseError("immutable fingerprint id maps to conflicting content")
        files = {record_path: canonical_json(record.to_dict())}
        if existing_fingerprint is None:
            files[fingerprint_path] = fingerprint_payload
        return stage_files(
            database,
            tip=current_tip,
            branch=branch,
            files=files,
            message=(
                f"benchmark: {record.record_id}",
                f"Benchmark-Subject: {subject}",
                f"Benchmark-Fingerprint: {fingerprint_id}",
                f"Benchmark-Record: {record.record_id}",
            ),
        )


def stage_revocation(
    database: GitBenchmarkDatabase,
    revocation: Revocation,
    *,
    captured_tip: str | None = None,
) -> StagedCandidate:
    """Stage an additive revocation after validating its target and current tip."""

    database.require_complete_history()
    initial_tip = captured_tip or database.data_tip()
    path = database.revocation_path(revocation)
    branch = revocation_branch(revocation)
    payload = canonical_json(revocation.to_dict())
    with database._lock():
        current_tip = database.data_tip()
        _assert_captured_tip(database, initial_tip, current_tip)
        if revocation.record_id not in database._record_ids_at(current_tip):
            raise DatabaseError("revocation target is not present in authoritative record history")
        if revocation.record_id in database._revoked_record_ids(current_tip):
            raise DatabaseError("benchmark record is already revoked")
        if database._show(path, current_tip) is not None:
            raise DatabaseError("immutable revocation already exists; first writer wins")
        return stage_files(
            database,
            tip=current_tip,
            branch=branch,
            files={path: payload},
            message=(
                f"benchmark: revoke {revocation.record_id}",
                f"Benchmark-Revocation: {revocation.id}",
                f"Benchmark-Record: {revocation.record_id}",
            ),
        )


def push_candidate(database: GitBenchmarkDatabase, candidate: StagedCandidate, remote: str) -> None:
    """Publish a new candidate ref under an absent-ref lease, never the authority ref."""

    if not remote or remote.startswith("-"):
        raise DatabaseError("a candidate remote name or URL is required")
    if not candidate.branch.startswith(("benchmark-record/", "benchmark-revocation/")):
        raise DatabaseError("candidate branch is outside the governed candidate namespaces")
    branch_ref = f"refs/heads/{candidate.branch}"
    commit = database._validate_object_id(candidate.commit, field="candidate commit")
    if database._commit_id(branch_ref, field="candidate branch") != commit:
        raise DatabaseError("candidate branch no longer identifies the staged commit")
    existing = git_result(
        database.repository,
        "ls-remote",
        "--exit-code",
        "--heads",
        remote,
        branch_ref,
    )
    if existing.returncode == 0 and existing.stdout:
        raise DatabaseError("candidate publication failed; the same key already has a first writer")
    if existing.returncode not in {0, 2}:
        detail = existing.stderr or existing.stdout or "remote query failed"
        raise DatabaseError(f"candidate remote could not be queried: {detail}")
    parents = git(database.repository, "show", "-s", "--format=%P", commit).split()
    if len(parents) != 1:
        raise DatabaseError("candidate publication requires a single-parent commit")
    result = git_result(
        database.repository,
        "push",
        "--porcelain",
        f"--force-with-lease={branch_ref}:",
        "--",
        remote,
        f"{commit}:{branch_ref}",
    )
    if result.returncode:
        detail = result.stderr or result.stdout or "remote rejected candidate"
        raise DatabaseError(
            f"candidate publication failed; the same key may already have a first writer: {detail}"
        )
