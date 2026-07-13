"""History-wide integrity auditing for the append-only benchmark database."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ...governance import AUTHORITATIVE_DATA_REF
from ...schema.canonical import canonical_json
from . import AuditIssue, DatabaseError
from .git_operations import git, git_succeeded
from .paths import (
    MANAGED_ROOTS,
    canonical_object,
    hash_digest,
    integer_field,
    mapping_field,
    string_field,
)
from .store import GitBenchmarkDatabase
from .transactions import atomic_write

_AUDIT_STATE_NAME = "benchmark-data-v1-audit-state.json"


def _managed_changes(database: GitBenchmarkDatabase, commit: str) -> tuple[tuple[str, str], ...]:
    parents = git(database.repository, "show", "-s", "--format=%P", commit).split()
    roots = [root.rstrip("/") for root in MANAGED_ROOTS]
    if parents:
        output = git(
            database.repository,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            parents[0],
            commit,
            "--",
            *roots,
        )
    else:
        output = git(
            database.repository,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            commit,
            "--",
            *roots,
        )
    changes: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0][0], parts[-1]))
    return tuple(changes)


def _declared_baseline(record: Mapping[str, object]) -> tuple[bool, str | None]:
    run_conditions = record.get("run_conditions")
    if not isinstance(run_conditions, Mapping) or "baseline_record_id" not in run_conditions:
        return False, None
    value = run_conditions["baseline_record_id"]
    if value is None:
        return True, None
    if not isinstance(value, str):
        raise ValueError("run_conditions.baseline_record_id must be a record id or null")
    hash_digest(value, field="run_conditions.baseline_record_id")
    return True, value


def _audit_state(database: GitBenchmarkDatabase) -> tuple[Path, dict[str, object] | None]:
    path = database._common_directory() / _AUDIT_STATE_NAME
    if not path.exists():
        return path, None
    try:
        state = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DatabaseError(f"local benchmark audit state is corrupt: {error}") from error
    if not isinstance(state, dict):
        raise DatabaseError("local benchmark audit state is corrupt: expected object")
    return path, state


def _check_previous_audit(
    database: GitBenchmarkDatabase,
    tip: str,
    state_path: Path,
    state: dict[str, object] | None,
    issues: list[AuditIssue],
) -> None:
    if state is None:
        return
    previous_ref = state.get("data_ref")
    previous_format = state.get("object_format")
    previous_tip = state.get("tip")
    if previous_ref != AUTHORITATIVE_DATA_REF or previous_format != database.object_format:
        issues.append(AuditIssue(str(state_path), "local audit state has incompatible governance"))
    elif (
        isinstance(previous_tip, str)
        and previous_tip != tip
        and (
            not git_succeeded(database.repository, "cat-file", "-e", f"{previous_tip}^{{commit}}")
            or not database._is_ancestor(previous_tip, tip)
        )
    ):
        issues.append(
            AuditIssue(
                AUTHORITATIVE_DATA_REF,
                "authoritative data history was rewritten since the previous audit",
            )
        )


def _audit_record(
    database: GitBenchmarkDatabase,
    *,
    path: str,
    payload: bytes,
    commit: str,
    parents: list[str],
    seen_keys: dict[tuple[str, str, str, int], str],
    records_by_id: dict[str, tuple[str, Mapping[str, object], str]],
    issues: list[AuditIssue],
) -> None:
    preview = canonical_object(payload, kind="benchmark record", path=path)
    provenance = mapping_field(preview["provenance"], "provenance")
    fingerprint = mapping_field(preview["fingerprint"], "fingerprint")
    key = (
        string_field(provenance["subject_commit"], "provenance.subject_commit"),
        string_field(fingerprint["id"], "fingerprint.id"),
        string_field(preview["suite_id"], "suite_id"),
        integer_field(preview["suite_version"], "suite_version"),
    )
    previous_path = seen_keys.get(key)
    if previous_path is not None:
        issues.append(AuditIssue(path, f"duplicate immutable primary key also at {previous_path}"))
    seen_keys[key] = path
    record = database._validated_record(path, payload)
    stored_record_id = string_field(record["record_id"], "record_id")
    if stored_record_id in records_by_id:
        issues.append(AuditIssue(path, "duplicate benchmark record content id"))
    records_by_id[stored_record_id] = (path, record, commit)
    if not git_succeeded(database.repository, "cat-file", "-e", f"{key[0]}^{{commit}}"):
        issues.append(AuditIssue(path, "benchmark subject commit is missing from the repository"))
    declared, declared_id = _declared_baseline(record)
    if declared:
        parent_ref = parents[0] if parents else commit
        expected = database._nearest_record_at(parent_ref, key[0], key[1], key[2], key[3])
        if declared_id != database._record_id(expected):
            issues.append(
                AuditIssue(
                    path,
                    "declared baseline is not the nearest earlier first-parent record",
                )
            )


def _audit_added_shard(
    database: GitBenchmarkDatabase,
    *,
    path: str,
    payload: bytes,
    commit: str,
    parents: list[str],
    seen_keys: dict[tuple[str, str, str, int], str],
    records_by_id: dict[str, tuple[str, Mapping[str, object], str]],
    revocation_targets: dict[str, str],
    fingerprints: dict[str, tuple[str, Mapping[str, object]]],
    issues: list[AuditIssue],
) -> None:
    if path.startswith("fingerprints/v1/"):
        fingerprint = database._validated_fingerprint(path, payload)
        fingerprint_id = string_field(fingerprint["id"], "fingerprint.id")
        if fingerprint_id in fingerprints:
            issues.append(AuditIssue(path, "duplicate fingerprint content id"))
        fingerprints[fingerprint_id] = (path, fingerprint)
    elif path.startswith("records/v1/"):
        _audit_record(
            database,
            path=path,
            payload=payload,
            commit=commit,
            parents=parents,
            seen_keys=seen_keys,
            records_by_id=records_by_id,
            issues=issues,
        )
    elif path.startswith("revocations/v1/"):
        revocation = database._validated_revocation(path, payload)
        target = string_field(revocation["record_id"], "record_id")
        previous = revocation_targets.get(target)
        if previous is not None:
            issues.append(AuditIssue(path, f"record already revoked by immutable shard {previous}"))
        revocation_targets[target] = path
    else:
        issues.append(AuditIssue(path, "path is outside managed database roots"))


def audit_database(database: GitBenchmarkDatabase) -> tuple[AuditIssue, ...]:
    """Audit canonical shards and every append-only transition on the authority chain."""

    database.require_complete_history()
    issues: list[AuditIssue] = []
    with database._lock():
        tip = database.data_tip()
        state_path, state = _audit_state(database)
        _check_previous_audit(database, tip, state_path, state, issues)
        commits = tuple(
            line
            for line in git(
                database.repository, "rev-list", "--reverse", "--first-parent", tip
            ).splitlines()
            if line
        )
        seen_paths: set[str] = set()
        seen_keys: dict[tuple[str, str, str, int], str] = {}
        records_by_id: dict[str, tuple[str, Mapping[str, object], str]] = {}
        revocation_targets: dict[str, str] = {}
        fingerprints: dict[str, tuple[str, Mapping[str, object]]] = {}

        for commit in commits:
            parents = git(database.repository, "show", "-s", "--format=%P", commit).split()
            changes = _managed_changes(database, commit)
            if changes and len(parents) > 1:
                issues.append(
                    AuditIssue(commit, "managed database shards were introduced by a merge commit")
                )
            for status, path in changes:
                if status != "A":
                    issues.append(
                        AuditIssue(path, "immutable historical shard was modified or deleted")
                    )
                    continue
                if path in seen_paths:
                    issues.append(AuditIssue(path, "immutable shard path was added more than once"))
                seen_paths.add(path)
                payload = database._show(path, commit)
                if payload is None:
                    issues.append(AuditIssue(path, "added shard is unavailable at its commit"))
                    continue
                try:
                    _audit_added_shard(
                        database,
                        path=path,
                        payload=payload,
                        commit=commit,
                        parents=parents,
                        seen_keys=seen_keys,
                        records_by_id=records_by_id,
                        revocation_targets=revocation_targets,
                        fingerprints=fingerprints,
                        issues=issues,
                    )
                except (KeyError, TypeError, ValueError, DatabaseError) as error:
                    issues.append(AuditIssue(path, str(error)))

        current_paths = {
            line
            for line in git(database.repository, "ls-tree", "-r", "--name-only", tip).splitlines()
            if line.startswith(MANAGED_ROOTS)
        }
        for path in sorted(current_paths - seen_paths):
            issues.append(
                AuditIssue(
                    path, "current shard has no append-only addition in first-parent history"
                )
            )
        for record_id_value, (path, historical_record, _commit) in records_by_id.items():
            historical_fingerprint = mapping_field(historical_record["fingerprint"], "fingerprint")
            fingerprint_id = string_field(historical_fingerprint["id"], "fingerprint.id")
            stored = fingerprints.get(fingerprint_id)
            if stored is None:
                issues.append(AuditIssue(path, "record references a missing fingerprint shard"))
            elif dict(stored[1]) != dict(historical_fingerprint):
                issues.append(
                    AuditIssue(path, "record fingerprint conflicts with its fingerprint shard")
                )
            if (
                record_id_value in revocation_targets
                and revocation_targets[record_id_value] not in current_paths
            ):
                issues.append(
                    AuditIssue(
                        revocation_targets[record_id_value],
                        "revocation is absent from the current tree",
                    )
                )
        for target, path in revocation_targets.items():
            if target not in records_by_id:
                issues.append(
                    AuditIssue(path, "revocation references no record in authority history")
                )

        if database.data_tip() != tip:
            raise DatabaseError("authoritative data tip changed during integrity audit")
        if not issues:
            atomic_write(
                state_path,
                canonical_json(
                    {
                        "schema_version": 1,
                        "data_ref": AUTHORITATIVE_DATA_REF,
                        "object_format": database.object_format,
                        "tip": tip,
                    }
                ),
            )
    return tuple(issues)
