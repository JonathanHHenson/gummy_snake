from __future__ import annotations

from pathlib import Path

from benchmarks.coverage import assert_checked_manifest, load_checked_manifest, load_manifest
from benchmarks.schema.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "synth_v1.toml"
CHECKED_MANIFEST_PATH = ROOT / "benchmarks" / "coverage" / "synth_v1.json"


def test_synth_checked_manifest_is_exact_catalog_projection() -> None:
    catalog = load_catalog(CATALOG_PATH)
    generated = load_manifest(CATALOG_PATH)
    checked = load_checked_manifest(CHECKED_MANIFEST_PATH)

    assert_checked_manifest(catalog, checked)
    assert generated.to_dict() == checked.to_dict()
    assert len(checked.entries) == len(catalog.workloads) == 15
    counter_cases = {entry.case_id: entry for entry in checked.entries if entry.required_counters}
    assert set(counter_cases) == {
        "direct-serialized-pyo3-parity-64",
        "serialized-render-python-heartbeat-128",
    }
    assert "parallel_tasks" in counter_cases["direct-serialized-pyo3-parity-64"].required_counters
    assert (
        "python_heartbeat_max_pause_ns"
        in counter_cases["serialized-render-python-heartbeat-128"].required_counters
    )
    assert {entry.route for entry in checked.entries} == {"headless", "simulated-realtime"}
    assert all(entry.route != "native-audio" for entry in checked.entries)


def test_synth_coverage_records_exact_work_units_and_metric_identities() -> None:
    checked = load_checked_manifest(CHECKED_MANIFEST_PATH)

    for entry in checked.entries:
        work_units = entry.runtime_parameters.get("work_units")
        assert isinstance(work_units, int) and not isinstance(work_units, bool)
        assert work_units > 0
        assert entry.metric_identity.id.endswith("-ns")
        assert entry.definition_digest.startswith("sha256:")
