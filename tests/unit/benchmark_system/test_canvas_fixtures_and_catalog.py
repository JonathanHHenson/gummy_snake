from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.canvas.fixtures import FIXTURE_BYTES, FIXTURE_MANIFEST, validate_manifest

ROOT = Path(__file__).resolve().parents[3]


def test_canvas_fixtures_have_a_complete_deterministic_manifest() -> None:
    validate_manifest()
    assert {entry.name for entry in FIXTURE_MANIFEST} == set(FIXTURE_BYTES)
    assert all(entry.byte_length > 0 and len(entry.sha256) == 64 for entry in FIXTURE_MANIFEST)


def test_canvas_fixture_manifest_rejects_changed_bytes() -> None:
    changed = dict(FIXTURE_BYTES)
    changed["checkerboard-8"] = b"changed"

    with pytest.raises(ValueError, match="fixture length mismatch"):
        validate_manifest(payloads=changed)


def test_canvas_catalog_is_static_and_hashes_suite_sources() -> None:
    catalog = load_catalog(ROOT / "benchmarks" / "canvas_v1.toml")

    assert len(catalog.workloads) == 6
    assert {workload.execution_class.value for workload in catalog.workloads} == {
        "headless",
        "native-interactive",
    }
    assert all(
        source.startswith("suites/canvas/") or source == "suites/__init__.py"
        for source in catalog.workload_files()
    )
    assert all(workload.definition_digest.startswith("sha256:") for workload in catalog.workloads)
