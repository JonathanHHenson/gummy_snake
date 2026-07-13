from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

from benchmarks.framework.git_database import StagedCandidate
from benchmarks.framework.git_database.store import GitBenchmarkDatabase
from benchmarks.schema.records import (
    BenchmarkRecord,
    ComparisonFingerprint,
    MetricResult,
    Provenance,
)


def git(repository: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *args),
        check=False,
        text=True,
        capture_output=True,
    )
    if check and result.returncode:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def init_repository(path: Path, *, object_format: str = "sha1") -> None:
    arguments = (
        ("init",) if object_format == "sha1" else ("init", f"--object-format={object_format}")
    )
    git(path, *arguments)
    git(path, "config", "user.email", "test@example.test")
    git(path, "config", "user.name", "Benchmark Test")


def commit_file(repository: Path, value: str, message: str) -> str:
    (repository / "code.txt").write_text(value)
    git(repository, "add", "code.txt")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def record(
    subject: str,
    *,
    suite_id: str = "canvas",
    suite_version: int = 1,
    fingerprint: ComparisonFingerprint | None = None,
    run_conditions: dict[str, object] | None = None,
) -> BenchmarkRecord:
    return BenchmarkRecord(
        fingerprint=fingerprint
        or ComparisonFingerprint({"architecture": "arm64", "runtime_route": "headless"}),
        provenance=Provenance(
            subject,
            "sha256:source",
            "sha256:tree",
            "sha256:wheel",
            "sha256:lock",
            {"profile": "release"},
            {},
        ),
        suite_id=suite_id,
        suite_version=suite_version,
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
        run_conditions=run_conditions or {},
    )


def provision_database(repository: Path, start: str | None = None) -> GitBenchmarkDatabase:
    git(repository, "branch", "benchmark-data-v1", start or "HEAD")
    return GitBenchmarkDatabase(repository)


def integrate_candidate(
    repository: Path,
    database: GitBenchmarkDatabase,
    candidate: StagedCandidate,
) -> None:
    old_tip = database.data_tip()
    assert git(repository, "rev-parse", f"{candidate.commit}^") == old_tip
    git(
        repository,
        "update-ref",
        "refs/heads/benchmark-data-v1",
        candidate.commit,
        old_tip,
    )
