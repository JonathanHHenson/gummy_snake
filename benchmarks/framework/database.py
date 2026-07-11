"""Append-only benchmark records stored as immutable shards on a fixed Git ref."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from ..governance import AUTHORITATIVE_DATA_REF
from ..schema.canonical import canonical_json, content_hash
from ..schema.records import BenchmarkRecord, Revocation


class DatabaseError(RuntimeError):
    """The authoritative Git database cannot be trusted or updated safely."""


@dataclass(frozen=True, slots=True)
class AuditIssue:
    path: str
    message: str


def _git(repo: Path, *arguments: str, check: bool = True) -> str:
    environment = os.environ.copy()
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    result = subprocess.run(
        ("git", "-C", str(repo), *arguments),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if check and result.returncode:
        raise DatabaseError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            with suppress(OSError):
                os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class GitBenchmarkDatabase:
    """A fixed-ref Git view with first-writer-wins local recording support."""

    def __init__(self, repository: Path, data_ref: str = AUTHORITATIVE_DATA_REF) -> None:
        if data_ref != AUTHORITATIVE_DATA_REF:
            raise DatabaseError(
                f"benchmark database ref is fixed at {AUTHORITATIVE_DATA_REF}; migration required"
            )
        self.repository = repository.resolve()
        self.data_ref = data_ref
        _git(self.repository, "rev-parse", "--git-dir")

    def require_complete_history(self) -> None:
        if _git(self.repository, "rev-parse", "--is-shallow-repository") == "true":
            raise DatabaseError("authoritative benchmark history must not be shallow")
        # Replacement objects make ancestry non-authoritative even when disabled per command.
        replacements = _git(self.repository, "replace", "-l")
        if replacements:
            raise DatabaseError(
                "authoritative benchmark resolution rejects repositories with replacement refs"
            )

    def data_tip(self) -> str:
        tip = _git(
            self.repository,
            "rev-parse",
            "--verify",
            f"{self.data_ref}^{{commit}}",
            check=False,
        )
        if not tip:
            raise DatabaseError(
                f"authoritative benchmark data ref {self.data_ref} is unavailable; "
                "configure the recorder remote and provision the protected v1 data branch"
            )
        return tip

    def fetch_authoritative_ref(self, remote: str) -> str:
        """Fetch only the fixed authority ref; caller-controlled refspecs are forbidden."""

        if not remote:
            raise DatabaseError("an authoritative data remote name or URL is required")
        _git(
            self.repository,
            "fetch",
            "--no-tags",
            remote,
            f"+{AUTHORITATIVE_DATA_REF}:{AUTHORITATIVE_DATA_REF}",
        )
        return self.data_tip()

    def require_authoritative_ready(self) -> str:
        self.require_complete_history()
        return self.data_tip()

    def head(self) -> str:
        return _git(self.repository, "rev-parse", "--verify", "HEAD^{commit}")

    def require_clean_head(self) -> str:
        if _git(self.repository, "status", "--porcelain"):
            raise DatabaseError("record-head requires a clean worktree")
        self.require_complete_history()
        return self.head()

    def first_parent_commits(self, head: str | None = None) -> tuple[str, ...]:
        """Return earlier first-parent commits, never merge second parents or data history."""

        subject = head or self.head()
        parent = _git(self.repository, "rev-parse", "--verify", f"{subject}^", check=False)
        if not parent:
            return ()
        output = _git(self.repository, "rev-list", "--first-parent", parent)
        return tuple(line for line in output.splitlines() if line)

    @staticmethod
    def fingerprint_path(fingerprint_id: str) -> str:
        return f"fingerprints/v1/{fingerprint_id}.json"

    @staticmethod
    def record_path(record: BenchmarkRecord) -> str:
        subject, fingerprint, suite, version = record.primary_key
        return f"records/v1/{fingerprint}/{subject}/{suite}@{version}.json"

    @staticmethod
    def revocation_path(revocation: Revocation) -> str:
        return f"revocations/v1/{revocation.id.split(':', 1)[1]}.json"

    def _show(self, path: str, ref: str | None = None) -> bytes | None:
        reference = ref or self.data_ref
        result = subprocess.run(
            ("git", "-C", str(self.repository), "show", f"{reference}:{path}"),
            capture_output=True,
            env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
            check=False,
        )
        if result.returncode:
            return None
        return result.stdout

    def _records_for(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> list[dict[str, object]]:
        self.require_authoritative_ready()
        path = f"records/v1/{fingerprint_id}/{subject}/{suite_id}@{suite_version}.json"
        payload = self._show(path)
        if payload is None:
            return []
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as error:
            raise DatabaseError(f"corrupt benchmark record {path}: {error}") from error
        if not isinstance(parsed, dict):
            raise DatabaseError(f"corrupt benchmark record {path}: expected object")
        return [parsed]

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        records = self._records_for(subject, fingerprint_id, suite_id, suite_version)
        return records[0] if records else None

    def fingerprint_known(self, fingerprint_id: str) -> bool:
        self.require_authoritative_ready()
        return self._show(self.fingerprint_path(fingerprint_id)) is not None

    def nearest_first_parent_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        self.require_authoritative_ready()
        for ancestor in self.first_parent_commits(subject):
            record = self.exact_record(ancestor, fingerprint_id, suite_id, suite_version)
            if record is not None:
                return record
        return None

    @contextmanager
    def _lock(self) -> Iterator[None]:
        common = Path(
            _git(self.repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        lock_path = common / "benchmark-data-v1.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise DatabaseError(
                "another local benchmark recorder holds the database lock"
            ) from error
        try:
            os.write(descriptor, str(os.getpid()).encode())
            yield
        finally:
            os.close(descriptor)
            with suppress(FileNotFoundError):
                lock_path.unlink()

    def record_local(self, record: BenchmarkRecord, *, message: str | None = None) -> str:
        """Append a record in a temporary worktree and advance only the fixed ref.

        This is a local transaction. Remote protection/fast-forward push authorization is
        deliberately outside this API and must be provided by protected server policy.
        """

        self.require_complete_history()
        tip = self.data_tip()
        record_path = self.record_path(record)
        with self._lock():
            if self.data_tip() != tip:
                raise DatabaseError("database tip changed before local transaction")
            if self._show(record_path, tip) is not None:
                raise DatabaseError("immutable record key already exists")
            fingerprint_path = self.fingerprint_path(record.fingerprint.id)
            existing_fingerprint = self._show(fingerprint_path, tip)
            fingerprint_payload = canonical_json(record.fingerprint.to_dict())
            if existing_fingerprint is not None and existing_fingerprint != fingerprint_payload:
                raise DatabaseError("immutable fingerprint id maps to conflicting content")
            temporary = Path(tempfile.mkdtemp(prefix="benchmark-data-worktree-"))
            try:
                _git(self.repository, "worktree", "add", "--detach", str(temporary), tip)
                if existing_fingerprint is None:
                    _atomic_write(temporary / fingerprint_path, fingerprint_payload)
                _atomic_write(temporary / record_path, canonical_json(record.to_dict()))
                _git(temporary, "add", fingerprint_path, record_path)
                _git(temporary, "commit", "-m", message or f"benchmark: {record.record_id}")
                new_tip = _git(temporary, "rev-parse", "HEAD")
                # Compare-and-swap prevents lost updates after the record was measured.
                _git(self.repository, "update-ref", self.data_ref, new_tip, tip)
                return new_tip
            finally:
                _git(self.repository, "worktree", "remove", "--force", str(temporary), check=False)
                shutil.rmtree(temporary, ignore_errors=True)

    def record_revocation_local(self, revocation: Revocation) -> str:
        self.require_complete_history()
        tip = self.data_tip()
        path = self.revocation_path(revocation)
        with self._lock():
            if self._show(path, tip) is not None:
                raise DatabaseError("immutable revocation already exists")
            temporary = Path(tempfile.mkdtemp(prefix="benchmark-revocation-worktree-"))
            try:
                _git(self.repository, "worktree", "add", "--detach", str(temporary), tip)
                _atomic_write(temporary / path, canonical_json(revocation.to_dict()))
                _git(temporary, "add", path)
                _git(temporary, "commit", "-m", f"benchmark revocation: {revocation.record_id}")
                new_tip = _git(temporary, "rev-parse", "HEAD")
                _git(self.repository, "update-ref", self.data_ref, new_tip, tip)
                return new_tip
            finally:
                _git(self.repository, "worktree", "remove", "--force", str(temporary), check=False)
                shutil.rmtree(temporary, ignore_errors=True)


def audit_database(database: GitBenchmarkDatabase) -> tuple[AuditIssue, ...]:
    """Validate immutable shard names, canonical hashes, and subject commit existence."""

    database.require_complete_history()
    tip = database.data_tip()
    listing = _git(database.repository, "ls-tree", "-r", "--name-only", tip)
    issues: list[AuditIssue] = []
    seen_keys: set[tuple[str, str, str, int]] = set()
    record_ids: set[str] = set()
    for path in (line for line in listing.splitlines() if line.startswith("records/v1/")):
        payload = database._show(path, tip)
        if payload is None:
            issues.append(AuditIssue(path, "record disappeared during audit"))
            continue
        try:
            record = json.loads(payload)
            if not isinstance(record, dict):
                raise ValueError("not an object")
            if payload != canonical_json(record):
                raise ValueError("record is not canonical JSON")
            record_id = record.pop("record_id")
            if content_hash(record) != record_id:
                raise ValueError("record content hash mismatch")
            record_ids.add(str(record_id))
            provenance = record["provenance"]
            fingerprint = record["fingerprint"]
            key = (
                str(provenance["subject_commit"]),
                str(fingerprint["id"]),
                str(record["suite_id"]),
                int(record["suite_version"]),
            )
            expected = f"records/v1/{key[1]}/{key[0]}/{key[2]}@{key[3]}.json"
            if path != expected:
                raise ValueError("record path does not match its primary key")
            if key in seen_keys:
                raise ValueError("duplicate immutable primary key")
            seen_keys.add(key)
            _git(database.repository, "cat-file", "-e", f"{key[0]}^{{commit}}")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, DatabaseError) as error:
            issues.append(AuditIssue(path, str(error)))
    for path in (line for line in listing.splitlines() if line.startswith("fingerprints/v1/")):
        payload = database._show(path, tip)
        try:
            fingerprint = json.loads(payload or b"")
            if not isinstance(fingerprint, dict):
                raise ValueError("not an object")
            if payload != canonical_json(fingerprint):
                raise ValueError("fingerprint is not canonical JSON")
            fingerprint_id = content_hash(
                {"schema_version": fingerprint["schema_version"], "stable": fingerprint["stable"]}
            ).split(":", 1)[1]
            if fingerprint.get("id") != fingerprint_id:
                raise ValueError("fingerprint hash mismatch")
            if path != database.fingerprint_path(fingerprint_id):
                raise ValueError("fingerprint path does not match its hash")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            issues.append(AuditIssue(path, str(error)))
    for path in (line for line in listing.splitlines() if line.startswith("revocations/v1/")):
        payload = database._show(path, tip)
        try:
            revocation = json.loads(payload or b"")
            if not isinstance(revocation, dict):
                raise ValueError("not an object")
            if payload != canonical_json(revocation):
                raise ValueError("revocation is not canonical JSON")
            revocation_id = content_hash(revocation).split(":", 1)[1]
            if path != f"revocations/v1/{revocation_id}.json":
                raise ValueError("revocation path does not match its content hash")
            if not revocation.get("reason") or not revocation.get("approval"):
                raise ValueError("revocation requires reason and approval metadata")
            if revocation.get("record_id") not in record_ids:
                raise ValueError("revocation references no record in this authority history")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            issues.append(AuditIssue(path, str(error)))
    return tuple(issues)
