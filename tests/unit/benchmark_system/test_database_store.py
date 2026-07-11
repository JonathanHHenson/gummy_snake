from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.framework.database import DatabaseError, GitBenchmarkDatabase, audit_database
from benchmarks.schema.records import (
    BenchmarkRecord,
    ComparisonFingerprint,
    MetricResult,
    Provenance,
)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repository), *args), check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()


def record(subject: str) -> BenchmarkRecord:
    return BenchmarkRecord(
        fingerprint=ComparisonFingerprint({"architecture": "arm64", "runtime_route": "headless"}),
        provenance=Provenance(
            subject,
            "sha256:source",
            "sha256:tree",
            "sha256:wheel",
            "sha256:lock",
            {"profile": "release"},
            {},
        ),
        suite_id="canvas",
        suite_version=1,
        catalog_digest="sha256:catalog",
        metrics=(
            MetricResult(
                ("fill", 1, "small", "sha256:param", "elapsed", 1, 1),
                ((10, 11), (12, 13)),
                1,
                Decimal("11.5"),
                "ns",
                "lower-is-better",
                "ratio",
                Decimal("11.5"),
            ),
        ),
        run_conditions={},
    )


def test_missing_authoritative_ref_is_an_actionable_infrastructure_error(tmp_path: Path) -> None:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.test")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "code.txt").write_text("a")
    git(tmp_path, "add", "code.txt")
    git(tmp_path, "commit", "-m", "first")

    with pytest.raises(DatabaseError, match="authoritative benchmark data ref"):
        GitBenchmarkDatabase(tmp_path).data_tip()


def test_fixed_ref_immutable_store_and_first_parent_lookup(tmp_path: Path) -> None:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.test")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "code.txt").write_text("a")
    git(tmp_path, "add", "code.txt")
    git(tmp_path, "commit", "-m", "first")
    subject = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "branch", "benchmark-data-v1")
    database = GitBenchmarkDatabase(tmp_path)
    stored = record(subject)
    database.record_local(stored)
    assert database.exact_record(subject, stored.fingerprint.id, "canvas", 1) is not None
    assert not audit_database(database)
    with pytest.raises(DatabaseError):
        database.record_local(stored)
    with pytest.raises(DatabaseError):
        GitBenchmarkDatabase(tmp_path, "refs/heads/other")
