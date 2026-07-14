from __future__ import annotations

from pathlib import Path

from benchmarks.schema.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "synth_v1.toml"

_EXPECTED_CASES = {
    ("composition", "flat-events-1k", "headless"),
    ("composition", "nested-lazy-depth-5", "headless"),
    ("composition", "source-synth-fx-templates-64", "headless"),
    ("composition", "flat-event-scale-1-to-65k", "headless"),
    ("composition", "nested-direct-depths-1-to-8", "headless"),
    ("composition", "lazy-expression-families-geometric", "headless"),
    ("composition", "template-first-load-warm-reuse-256", "headless"),
    ("composition", "schedule-controls-dense-sparse-open-finite", "headless"),
    ("composition", "fresh-process-seed-history-and-limits", "headless"),
    ("serialization-bridge", "plan-roundtrip-256", "headless"),
    ("serialization-bridge", "direct-serialized-pyo3-parity-64", "headless"),
    ("serialization-bridge", "serialized-render-python-heartbeat-128", "headless"),
    (
        "serialization-bridge",
        "phase-shape-size-depth-layer-fx-sample-sweeps",
        "headless",
    ),
    (
        "serialization-bridge",
        "hostile-container-types-values-and-runtime-validation",
        "headless",
    ),
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
    (
        "voices-filters-automation",
        "voice-families-rates-polyphony-matrix",
        "headless",
    ),
    (
        "voices-filters-automation",
        "layers-envelopes-filters-automation-matrix",
        "headless",
    ),
    ("sample-engine", "generated-pcm-decode-resample-cache", "headless"),
    ("sample-engine", "pcm-flac-decode-metadata-matrix", "headless"),
    ("sample-engine", "sample-resample-slice-playback-rate-matrix", "headless"),
    ("fx-mix-output", "all-practical-rust-fx-families", "headless"),
    ("fx-mix-output", "shared-buses-limiter-normaliser-output", "headless"),
    ("fx-mix-output", "fx-chain-and-bus-scaling-matrix", "headless"),
    (
        "fx-mix-output",
        "stateful-memory-file-output-1-10-60-seconds",
        "headless",
    ),
    (
        "streaming-sound",
        "simulated-realtime-pcm-block-sink",
        "simulated-realtime",
    ),
    ("streaming-sound", "public-sound-headless-state", "headless"),
    ("streaming-sound", "stateful-block-memory-file-parity", "headless"),
    (
        "streaming-sound",
        "stateful-partition-rolling-native-route-guards",
        "headless",
    ),
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


def test_synth_catalog_freezes_epic_310_composition_and_serialization_sweeps() -> None:
    catalog = load_catalog(CATALOG_PATH)
    cases = {workload.case_id: workload for workload in catalog.workloads}

    flat = cases["flat-event-scale-1-to-65k"]
    assert flat.parameters["event_counts"] == [1, 64, 1024, 16384, 65536]
    assert flat.parameters["work_units"] == 83009
    nested = cases["nested-direct-depths-1-to-8"]
    assert nested.parameters["depths"] == list(range(1, 9))
    schedule = cases["schedule-controls-dense-sparse-open-finite"]
    assert schedule.parameters["control_counts"] == [0, 64, 16384]
    shape = cases["phase-shape-size-depth-layer-fx-sample-sweeps"]
    assert shape.parameters["event_counts"] == [1, 64, 1024, 16384]
    assert shape.parameters["control_counts"] == [0, 64, 16384]
    assert shape.parameters["value_depths"] == [1, 8, 32]
    assert shape.parameters["layer_counts"] == [1, 4, 16]
    assert shape.parameters["fx_depths"] == [0, 4, 16, 64]
    assert shape.parameters["sample_path_counts"] == [1, 8, 64]
    assert shape.parameters["work_units"] == 34140
    hostile = cases["hostile-container-types-values-and-runtime-validation"]
    assert hostile.parameters["work_units"] == 24

    voices = cases["voice-families-rates-polyphony-matrix"]
    assert voices.parameters["sample_rates"] == [44100, 48000, 96000]
    assert voices.parameters["polyphonies"] == [1, 4, 12]
    assert voices.parameters["work_units"] == 90
    dsp = cases["layers-envelopes-filters-automation-matrix"]
    assert dsp.parameters["layer_counts"] == [2, 4, 7, 16]
    assert dsp.parameters["envelope_curves"] == [-4, -1, 1, 3, 4, 7]
    assert dsp.parameters["automation_counts"] == [0, 1, 8, 64]
    assert dsp.parameters["work_units"] == 90
    decode = cases["pcm-flac-decode-metadata-matrix"]
    assert decode.parameters["work_units"] == 54
    resample = cases["sample-resample-slice-playback-rate-matrix"]
    assert resample.parameters["playback_rates"] == ["-1", "0.125", "0.5", "1", "8"]
    assert resample.parameters["work_units"] == 30
    chain = cases["fx-chain-and-bus-scaling-matrix"]
    assert chain.parameters["chain_depths"] == [1, 2, 4, 8]
    assert chain.parameters["bus_counts"] == [1, 4, 16, 32]
    output = cases["stateful-memory-file-output-1-10-60-seconds"]
    assert output.parameters["duration_seconds"] == [1, 10, 60]
    assert output.parameters["work_units"] == 142


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


def test_synth_harness_is_independent_of_legacy_examples_network_and_fake_audio() -> None:
    suite_root = ROOT / "benchmarks" / "suites" / "synth"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(suite_root.glob("*.py"))
    )

    assert "benchmarks.legacy" not in sources
    assert "examples/" not in sources
    assert "urllib" not in sources
    assert "requests" not in sources
    assert 'physical_audio_qualified": True' not in sources
