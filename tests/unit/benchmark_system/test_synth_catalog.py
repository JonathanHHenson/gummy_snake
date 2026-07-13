from __future__ import annotations

from pathlib import Path

from benchmarks.schema.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "synth_v1.toml"

_EXPECTED_CASES = {
    ("composition", "flat-events-1k", "headless"),
    ("composition", "nested-lazy-depth-5", "headless"),
    ("composition", "source-synth-fx-templates-64", "headless"),
    ("serialization-bridge", "plan-roundtrip-256", "headless"),
    ("serialization-bridge", "direct-serialized-pyo3-parity-64", "headless"),
    ("serialization-bridge", "serialized-render-python-heartbeat-128", "headless"),
    (
        "voices-filters-automation",
        "all-primitive-oscillators-polyphony-4",
        "headless",
    ),
    (
        "voices-filters-automation",
        "layers-envelope-filter-automation",
        "headless",
    ),
    ("sample-engine", "generated-pcm-decode-resample-cache", "headless"),
    ("fx-mix-output", "all-practical-rust-fx-families", "headless"),
    ("fx-mix-output", "shared-buses-limiter-normaliser-output", "headless"),
    (
        "streaming-sound",
        "simulated-realtime-pcm-block-sink",
        "simulated-realtime",
    ),
    ("streaming-sound", "public-sound-headless-state", "headless"),
    ("failures-longevity", "fail-closed-validation", "headless"),
    ("failures-longevity", "bounded-compile-render-longevity", "headless"),
}


def test_synth_catalog_declares_exact_replacement_cases_and_profiles() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert {
        (workload.id, workload.case_id, workload.execution_class.value)
        for workload in catalog.workloads
    } == _EXPECTED_CASES
    assert {workload.suite_id for workload in catalog.workloads} == {"synth"}
    assert {workload.suite_version for workload in catalog.workloads} == {1}
    assert {workload.sampling_profile for workload in catalog.workloads} == {
        "micro",
        "bulk-headless",
        "simulated-realtime",
    }


def test_synth_catalog_has_explicit_work_and_only_suite_local_sources() -> None:
    catalog = load_catalog(CATALOG_PATH)

    for workload in catalog.workloads:
        work_units = workload.parameters.get("work_units")
        assert isinstance(work_units, int) and not isinstance(work_units, bool)
        assert work_units > 0
        assert workload.primary_metric.work_unit
        required_counters = workload.parameters.get("required_counters")
        if workload.case_id == "direct-serialized-pyo3-parity-64":
            assert isinstance(required_counters, list)
            assert "gil_released_calls" in required_counters
            assert "parallel_tasks" in required_counters
        elif workload.case_id == "serialized-render-python-heartbeat-128":
            assert isinstance(required_counters, list)
            assert "gil_released_calls" in required_counters
            assert "python_heartbeat_max_pause_ns" in required_counters
            assert workload.primary_metric.id == "serialized-heartbeat-render-elapsed-ns"
        else:
            assert required_counters == []
        assert workload.execution_class.value != "native-audio"
        assert "audio-output" not in workload.capabilities
        assert workload.definition_digest.startswith("sha256:")
    assert catalog.workload_files() == (
        "suites/synth/__init__.py",
        "suites/synth/diagnostics.py",
        "suites/synth/fixtures.py",
        "suites/synth/oracles.py",
        "suites/synth/workloads.py",
    )


def test_synth_package_init_is_documentation_only() -> None:
    source = (ROOT / "benchmarks" / "suites" / "synth" / "__init__.py").read_text()

    assert "from ." not in source
    assert "__all__" not in source
    assert "dispatch" not in source
