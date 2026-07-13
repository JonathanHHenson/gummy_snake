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
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"
CHECKED_PATH = ROOT / "benchmarks" / "coverage" / "ecs_v1.json"


def test_ecs_checked_coverage_is_the_exact_24_case_catalog_projection() -> None:
    catalog = load_catalog(CATALOG_PATH)
    generated = load_manifest(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_PATH)

    assert_checked_manifest(catalog, checked)
    assert generated.to_dict() == checked.to_dict()
    assert len(checked.entries) == len(catalog.workloads) == 24
    assert {(entry.workload_id, entry.case_id, entry.route) for entry in checked.entries} == {
        (workload.id, workload.case_id, workload.execution_class.value)
        for workload in catalog.workloads
    }
    for entry in checked.entries:
        declared = entry.runtime_parameters["required_counters"]
        assert isinstance(declared, list)
        assert entry.required_counters == tuple(declared)
        work_units = entry.runtime_parameters["work_units"]
        assert isinstance(work_units, int) and not isinstance(work_units, bool)
        assert work_units > 0


def test_ecs_checked_coverage_rejects_omitted_and_stale_cases() -> None:
    catalog = load_catalog(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_PATH)

    with pytest.raises(CoverageManifestError, match="omitted catalog cases"):
        assert_checked_manifest(catalog, replace(checked, entries=checked.entries[1:]))

    stale_entry = replace(checked.entries[0], definition_digest="sha256:" + "0" * 64)
    with pytest.raises(CoverageManifestError, match="stale checked cases"):
        assert_checked_manifest(
            catalog,
            replace(checked, entries=(stale_entry, *checked.entries[1:])),
        )
