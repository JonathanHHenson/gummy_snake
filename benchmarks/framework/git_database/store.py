"""Immutable shard storage and the primary Git benchmark database API."""

from __future__ import annotations

from ...schema.canonical import content_hash
from ...schema.records import BenchmarkRecord, Revocation
from . import DatabaseError, StagedCandidate
from .git_operations import git_result, show_file
from .history import GitRepositoryHistory
from .paths import (
    canonical_object,
    fingerprint_path,
    hash_digest,
    integer_field,
    mapping_field,
    record_path_parts,
    revocation_path,
    string_field,
)
from .transactions import (
    candidate_branch,
    push_candidate,
    record_id,
    revocation_branch,
    stage_candidate,
    stage_revocation,
)


class GitBenchmarkDatabase(GitRepositoryHistory):
    """A fixed-ref Git view with append-only, first-writer-wins candidate staging."""

    @staticmethod
    def fingerprint_path(fingerprint_id: str) -> str:
        """Return the canonical sharded path for a fingerprint identifier."""

        return fingerprint_path(fingerprint_id)

    @staticmethod
    def _record_path_parts(
        subject: str,
        fingerprint_id: str,
        suite_id: str,
        suite_version: int,
    ) -> str:
        return record_path_parts(subject, fingerprint_id, suite_id, suite_version)

    def record_path(self, record: BenchmarkRecord) -> str:
        """Return the canonical sharded path for a benchmark record."""

        subject, fingerprint, suite, version = record.primary_key
        self._validate_object_id(subject, field="benchmark subject commit")
        return record_path_parts(subject, fingerprint, suite, version)

    @staticmethod
    def revocation_path(revocation: Revocation) -> str:
        """Return the canonical content-sharded path for a revocation."""

        return revocation_path(revocation.id)

    def _show(self, path: str, ref: str | None = None) -> bytes | None:
        return show_file(self.repository, ref or self.data_ref, path)

    def _list_paths(self, ref: str, prefix: str) -> tuple[str, ...]:
        result = git_result(self.repository, "ls-tree", "-r", "--name-only", ref, "--", prefix)
        if result.returncode:
            raise DatabaseError(
                f"cannot list authoritative {prefix.rstrip('/')} shards at {ref}: {result.stderr}"
            )
        return tuple(line for line in result.stdout.splitlines() if line)

    def _validated_record(
        self,
        path: str,
        payload: bytes,
        *,
        expected_key: tuple[str, str, str, int] | None = None,
    ) -> dict[str, object]:
        record = canonical_object(payload, kind="benchmark record", path=path)
        try:
            stored_record_id = string_field(record["record_id"], "record_id")
            hash_digest(stored_record_id, field="record_id")
            unhashed = {key: value for key, value in record.items() if key != "record_id"}
            if content_hash(unhashed) != stored_record_id:
                raise ValueError("record content hash mismatch")
            provenance = mapping_field(record["provenance"], "provenance")
            fingerprint = mapping_field(record["fingerprint"], "fingerprint")
            subject = string_field(provenance["subject_commit"], "provenance.subject_commit")
            self._validate_object_id(subject, field="benchmark subject commit")
            fingerprint_id = string_field(fingerprint["id"], "fingerprint.id")
            suite_id = string_field(record["suite_id"], "suite_id")
            suite_version = integer_field(record["suite_version"], "suite_version")
            key = (subject, fingerprint_id, suite_id, suite_version)
            expected_path = record_path_parts(*key)
            if path != expected_path:
                raise ValueError("record path does not match its primary key")
            if expected_key is not None and key != expected_key:
                raise ValueError("record content does not match the requested primary key")
        except (KeyError, TypeError, ValueError, DatabaseError) as error:
            raise DatabaseError(f"corrupt benchmark record {path}: {error}") from error
        return record

    def _validated_fingerprint(self, path: str, payload: bytes) -> dict[str, object]:
        fingerprint = canonical_object(payload, kind="fingerprint", path=path)
        try:
            fingerprint_id = string_field(fingerprint["id"], "fingerprint.id")
            expected_id = content_hash(
                {
                    "schema_version": fingerprint["schema_version"],
                    "stable": fingerprint["stable"],
                }
            ).split(":", 1)[1]
            if fingerprint_id != expected_id:
                raise ValueError("fingerprint hash mismatch")
            if path != fingerprint_path(fingerprint_id):
                raise ValueError("fingerprint path does not match its hash")
        except (KeyError, TypeError, ValueError, DatabaseError) as error:
            raise DatabaseError(f"corrupt fingerprint {path}: {error}") from error
        return fingerprint

    def _validated_revocation(self, path: str, payload: bytes) -> dict[str, object]:
        revocation = canonical_object(payload, kind="revocation", path=path)
        try:
            revoked_record_id = string_field(revocation["record_id"], "record_id")
            hash_digest(revoked_record_id, field="record_id")
            if not string_field(revocation["reason"], "reason").strip():
                raise ValueError("revocation reason must not be blank")
            if not mapping_field(revocation["approval"], "approval"):
                raise ValueError("revocation requires approval metadata")
            digest = content_hash(revocation).split(":", 1)[1]
            expected = f"revocations/v1/{digest[:2]}/{digest}.json"
            if path != expected:
                raise ValueError("revocation path does not match its content hash")
        except (KeyError, TypeError, ValueError) as error:
            raise DatabaseError(f"corrupt revocation {path}: {error}") from error
        return revocation

    def _record_ids_at(self, ref: str) -> frozenset[str]:
        ids: set[str] = set()
        for path in self._list_paths(ref, "records/v1"):
            payload = self._show(path, ref)
            if payload is None:
                raise DatabaseError(f"record disappeared while reading {path}")
            record = self._validated_record(path, payload)
            stored_record_id = string_field(record["record_id"], "record_id")
            if stored_record_id in ids:
                raise DatabaseError(
                    f"duplicate benchmark record id in authority history: {stored_record_id}"
                )
            ids.add(stored_record_id)
        return frozenset(ids)

    def _revoked_record_ids(self, ref: str) -> frozenset[str]:
        revoked: set[str] = set()
        for path in self._list_paths(ref, "revocations/v1"):
            payload = self._show(path, ref)
            if payload is None:
                raise DatabaseError(f"revocation disappeared while reading {path}")
            revocation = self._validated_revocation(path, payload)
            revoked_record_id = string_field(revocation["record_id"], "record_id")
            if revoked_record_id in revoked:
                raise DatabaseError(
                    f"multiple revocations target benchmark record {revoked_record_id}"
                )
            revoked.add(revoked_record_id)
        if revoked:
            available_records = self._record_ids_at(ref)
            missing = sorted(revoked - available_records)
            if missing:
                raise DatabaseError(
                    f"revocation references no authoritative benchmark record: {missing[0]}"
                )
        return frozenset(revoked)

    def _exact_record_at(
        self,
        ref: str,
        subject: str,
        fingerprint_id: str,
        suite_id: str,
        suite_version: int,
        *,
        include_revoked: bool = False,
    ) -> dict[str, object] | None:
        self._validate_object_id(subject, field="benchmark subject commit")
        key = (subject, fingerprint_id, suite_id, suite_version)
        path = record_path_parts(*key)
        payload = self._show(path, ref)
        if payload is None:
            return None
        record = self._validated_record(path, payload, expected_key=key)
        embedded_fingerprint = mapping_field(record["fingerprint"], "fingerprint")
        stored_fingerprint_path = fingerprint_path(fingerprint_id)
        fingerprint_payload = self._show(stored_fingerprint_path, ref)
        if fingerprint_payload is None:
            raise DatabaseError(f"benchmark record {path} references a missing fingerprint shard")
        stored_fingerprint = self._validated_fingerprint(
            stored_fingerprint_path, fingerprint_payload
        )
        if dict(embedded_fingerprint) != stored_fingerprint:
            raise DatabaseError(f"benchmark record {path} conflicts with its fingerprint shard")
        if not include_revoked and string_field(
            record["record_id"], "record_id"
        ) in self._revoked_record_ids(ref):
            return None
        return record

    def exact_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        """Return the exact active record for a complete immutable primary key."""

        tip = self.require_authoritative_ready()
        return self._exact_record_at(tip, subject, fingerprint_id, suite_id, suite_version)

    def fingerprint_known(self, fingerprint_id: str) -> bool:
        """Return whether the authority contains a valid fingerprint shard."""

        tip = self.require_authoritative_ready()
        path = fingerprint_path(fingerprint_id)
        payload = self._show(path, tip)
        if payload is None:
            return False
        self._validated_fingerprint(path, payload)
        return True

    def _nearest_record_at(
        self,
        data_ref: str,
        subject: str,
        fingerprint_id: str,
        suite_id: str,
        suite_version: int,
    ) -> dict[str, object] | None:
        revoked = self._revoked_record_ids(data_ref)
        for ancestor in self.first_parent_commits(subject):
            record = self._exact_record_at(
                data_ref,
                ancestor,
                fingerprint_id,
                suite_id,
                suite_version,
                include_revoked=True,
            )
            if record is not None and string_field(record["record_id"], "record_id") not in revoked:
                return record
        return None

    def nearest_first_parent_record(
        self, subject: str, fingerprint_id: str, suite_id: str, suite_version: int
    ) -> dict[str, object] | None:
        """Return the nearest active record on the subject's earlier first-parent chain."""

        tip = self.require_authoritative_ready()
        return self._nearest_record_at(tip, subject, fingerprint_id, suite_id, suite_version)

    def is_revoked(self, record_id_value: str) -> bool:
        """Return whether an additive authority shard revokes a record identifier."""

        hash_digest(record_id_value, field="record_id")
        tip = self.require_authoritative_ready()
        return record_id_value in self._revoked_record_ids(tip)

    @staticmethod
    def candidate_branch(record: BenchmarkRecord) -> str:
        """Return the deterministic first-writer branch for a record."""

        return candidate_branch(record)

    @staticmethod
    def revocation_branch(revocation: Revocation) -> str:
        """Return the deterministic first-writer branch for a revocation target."""

        return revocation_branch(revocation)

    @staticmethod
    def _record_id(record: dict[str, object] | None) -> str | None:
        return record_id(record)

    def stage_candidate(
        self,
        record: BenchmarkRecord,
        *,
        captured_tip: str | None = None,
    ) -> StagedCandidate:
        """Stage a record without advancing the protected authoritative ref.

        A stale captured tip is accepted only when the nearest baseline remains unchanged.
        Changed baselines require the caller to rerun its benchmark comparison.
        """

        return stage_candidate(self, record, captured_tip=captured_tip)

    def stage_revocation(
        self,
        revocation: Revocation,
        *,
        captured_tip: str | None = None,
    ) -> StagedCandidate:
        """Stage an additive revocation after validating its target and approval."""

        return stage_revocation(self, revocation, captured_tip=captured_tip)

    def push_candidate(self, candidate: StagedCandidate, remote: str) -> None:
        """Publish a new candidate under an absent-ref lease, never the authority ref."""

        push_candidate(self, candidate, remote)
