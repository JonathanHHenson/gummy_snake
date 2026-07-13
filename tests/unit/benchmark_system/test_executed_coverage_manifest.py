from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.coverage import (
    CoverageManifestError,
    assert_checked_manifest,
    load_checked_manifest,
    load_manifest,
)
from benchmarks.schema.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "canvas_v1.toml"
CHECKED_MANIFEST_PATH = ROOT / "benchmarks" / "coverage" / "canvas_v1.json"


def test_canvas_checked_manifest_is_an_exact_catalog_projection() -> None:
    catalog = load_catalog(CATALOG_PATH)
    manifest = load_manifest(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_MANIFEST_PATH)

    assert_checked_manifest(catalog, checked)
    assert manifest.to_dict() == checked.to_dict()
    assert len(manifest.entries) == len(catalog.workloads) == 23
    for entry in manifest.entries:
        declared_counters = entry.runtime_parameters.get("required_counters", ())
        assert isinstance(declared_counters, (list, tuple))
        assert entry.required_counters == tuple(declared_counters)
    assert {
        (entry.workload_id, entry.workload_version, entry.case_id, entry.route)
        for entry in manifest.entries
    } == {
        (workload.id, workload.version, workload.case_id, workload.execution_class.value)
        for workload in catalog.workloads
    }


def test_checked_manifest_rejects_a_catalog_case_omitted_from_the_snapshot() -> None:
    catalog = load_catalog(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_MANIFEST_PATH)
    omitted = replace(checked, entries=checked.entries[1:])

    with pytest.raises(CoverageManifestError, match="omitted catalog cases"):
        assert_checked_manifest(catalog, omitted)


def test_checked_manifest_rejects_a_stale_case() -> None:
    catalog = load_catalog(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_MANIFEST_PATH)
    stale_entry = replace(checked.entries[0], definition_digest="sha256:" + "0" * 64)
    stale = replace(checked, entries=(stale_entry, *checked.entries[1:]))

    with pytest.raises(CoverageManifestError, match="stale checked cases"):
        assert_checked_manifest(catalog, stale)
