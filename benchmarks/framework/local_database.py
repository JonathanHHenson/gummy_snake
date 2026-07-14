"""Append-only local benchmark history and compatible baseline resolution."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..governance import LOCAL_HISTORY_DIRECTORY
from ..schema.canonical import canonical_json, canonical_json_loads
from ..schema.records import BenchmarkRecord, parse_benchmark_record

DEFAULT_LOCAL_HISTORY = Path(LOCAL_HISTORY_DIRECTORY)
_INDEX_NAME = "index.json"
_INDEX_SCHEMA_VERSION = 1


class LocalDatabaseError(RuntimeError):
    """The local benchmark history is corrupt or cannot be updated safely."""


@dataclass(frozen=True, slots=True)
class StoredLocalRecord:
    """The result of an immutable local record operation."""

    path: Path
    record_id: str
    created: bool


@dataclass(frozen=True, slots=True)
class LocalRecordSummary:
    """Audit-friendly metadata for one locally recorded benchmark suite."""

    path: str
    record_id: str
    subject: str
    fingerprint_id: str
    suite_id: str
    suite_version: int


@dataclass(frozen=True, slots=True)
class LocalAuditIssue:
    """One integrity problem in the local benchmark history."""

    path: str
    message: str


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            with suppress(OSError):
                os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":  # pragma: no cover - exercised by Windows benchmark runners
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":  # pragma: no cover - exercised by Windows benchmark runners
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            with suppress(OSError):
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            with suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise LocalDatabaseError(detail)
    return result


class LocalBenchmarkDatabase:
    """Canonical records stored under an ignored repository-local directory.

    Record payloads remain deterministic and immutable. ``index.json`` records only local
    insertion order so the newest compatible non-ancestor record can be selected explicitly.
    """

    def __init__(self, repository: Path, history_directory: Path | None = None) -> None:
        self.repository = repository.resolve()
        configured = history_directory or DEFAULT_LOCAL_HISTORY
        self.root = (
            configured if configured.is_absolute() else self.repository / configured
        ).resolve()
        _git(self.repository, "rev-parse", "--git-dir")

    @property
    def index_path(self) -> Path:
        return self.root / _INDEX_NAME

    def head(self) -> str:
        """Return the full current code commit without requiring a special data ref."""

        return (
            _git(self.repository, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
        )

    def require_clean_head(self) -> str:
        """Return HEAD only when tracked and untracked repository files are clean."""

        if _git(self.repository, "status", "--porcelain", "--untracked-files=all").stdout:
            raise LocalDatabaseError("record-head requires a clean worktree")
        return self.head()

    @staticmethod
    def _valid_record_path(path: object) -> str:
        if not isinstance(path, str):
            raise LocalDatabaseError("local benchmark index paths must be strings")
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or len(parsed.parts) < 2
            or parsed.parts[:2] != ("records", "v1")
            or parsed.suffix != ".json"
        ):
            raise LocalDatabaseError(f"invalid local benchmark record path: {path}")
        return path

    def _load_index(self) -> tuple[str, ...]:
        if not self.index_path.exists():
            return ()
        try:
            decoded = canonical_json_loads(self.index_path.read_bytes())
        except (OSError, UnicodeError, ValueError) as error:
            raise LocalDatabaseError(f"local benchmark index is corrupt: {error}") from error
        if not isinstance(decoded, Mapping) or set(decoded) != {"records", "schema_version"}:
            raise LocalDatabaseError(
                "local benchmark index must contain records and schema_version"
            )
        if decoded["schema_version"] != _INDEX_SCHEMA_VERSION:
            raise LocalDatabaseError("unsupported local benchmark index schema version")
        raw_records = decoded["records"]
        if not isinstance(raw_records, list):
            raise LocalDatabaseError("local benchmark index records must be a list")
        records = tuple(self._valid_record_path(path) for path in raw_records)
        if len(records) != len(set(records)):
            raise LocalDatabaseError("local benchmark index contains duplicate record paths")
        return records

    def _write_index(self, records: tuple[str, ...]) -> None:
        _atomic_write(
            self.index_path,
            canonical_json({"schema_version": _INDEX_SCHEMA_VERSION, "records": records}),
        )

    def _read_record(self, relative_path: str) -> BenchmarkRecord:
        path = self.root / relative_path
        try:
            payload = path.read_bytes()
            return parse_benchmark_record(payload, expected_path=relative_path)
        except (OSError, UnicodeError, ValueError) as error:
            raise LocalDatabaseError(
                f"invalid local benchmark record {relative_path}: {error}"
            ) from error

    def _indexed_records(self) -> tuple[tuple[str, BenchmarkRecord], ...]:
        return tuple((path, self._read_record(path)) for path in self._load_index())

    @staticmethod
    def _matches(
        record: BenchmarkRecord,
        fingerprint_id: str,
        suite_id: str,
        suite_version: int,
    ) -> bool:
        return (
            record.fingerprint.id == fingerprint_id
            and record.suite_id == suite_id
            and record.suite_version == suite_version
        )

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        for _, record in reversed(self._indexed_records()):
            if record.primary_key == (subject, fingerprint_id, suite_id, suite_version):
                return record.to_dict()
        return None

    def nearest_ancestor_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        """Return the nearest compatible record reachable from ``subject``."""

        by_subject = {
            record.provenance.subject_commit: record
            for _, record in self._indexed_records()
            if self._matches(record, fingerprint_id, suite_id, suite_version)
            and record.provenance.subject_commit != subject
        }
        if not by_subject:
            return None
        history = _git(self.repository, "rev-list", subject, check=False)
        if history.returncode:
            return None
        for commit in history.stdout.splitlines():
            record = by_subject.get(commit)
            if record is not None:
                return record.to_dict()
        return None

    def latest_record(
        self, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        """Return the newest compatible local record, regardless of Git ancestry."""

        for _, record in reversed(self._indexed_records()):
            if self._matches(record, fingerprint_id, suite_id, suite_version):
                return record.to_dict()
        return None

    def record(self, record: BenchmarkRecord) -> StoredLocalRecord:
        """Append one canonical record without replacing an existing primary key."""

        relative_path = record.expected_path
        destination = self.root / relative_path
        payload = canonical_json(record.to_dict())
        with _file_lock(self.root / ".lock"):
            index = self._load_index()
            if destination.exists():
                existing = self._read_record(relative_path)
                if existing.record_id != record.record_id:
                    raise LocalDatabaseError(
                        "a different local benchmark record already exists for this "
                        "HEAD/fingerprint/suite key"
                    )
                if relative_path not in index:
                    self._write_index((*index, relative_path))
                return StoredLocalRecord(destination, record.record_id, created=False)
            _atomic_write(destination, payload)
            self._write_index((*index, relative_path))
        return StoredLocalRecord(destination, record.record_id, created=True)

    def list_records(self) -> tuple[LocalRecordSummary, ...]:
        """List local records in insertion order after fully validating each payload."""

        summaries: list[LocalRecordSummary] = []
        for path, record in self._indexed_records():
            summaries.append(
                LocalRecordSummary(
                    path,
                    record.record_id,
                    record.provenance.subject_commit,
                    record.fingerprint.id,
                    record.suite_id,
                    record.suite_version,
                )
            )
        return tuple(summaries)

    def audit(self) -> tuple[LocalAuditIssue, ...]:
        """Validate the index, canonical records, path identities, and unindexed files."""

        issues: list[LocalAuditIssue] = []
        try:
            indexed = self._load_index()
        except LocalDatabaseError as error:
            return (LocalAuditIssue(_INDEX_NAME, str(error)),)
        indexed_set = set(indexed)
        for path in indexed:
            try:
                self._read_record(path)
            except LocalDatabaseError as error:
                issues.append(LocalAuditIssue(path, str(error)))
        records_root = self.root / "records" / "v1"
        if records_root.exists():
            for file_path in sorted(records_root.rglob("*.json")):
                relative = file_path.relative_to(self.root).as_posix()
                if relative not in indexed_set:
                    issues.append(LocalAuditIssue(relative, "record is not present in local index"))
        return tuple(issues)


__all__ = [
    "DEFAULT_LOCAL_HISTORY",
    "LocalAuditIssue",
    "LocalBenchmarkDatabase",
    "LocalDatabaseError",
    "LocalRecordSummary",
    "StoredLocalRecord",
]
