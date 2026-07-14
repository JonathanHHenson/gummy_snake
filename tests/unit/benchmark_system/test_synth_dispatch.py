from __future__ import annotations

from collections.abc import Mapping

import pytest

from benchmarks.governance import ExecutionClass
from benchmarks.suites.registry import SuiteExecution, dispatch
from benchmarks.suites.synth.diagnostics import SynthPathError
from benchmarks.suites.synth.workloads import SynthWorkloadError

_CASES: tuple[tuple[str, Mapping[str, object], ExecutionClass], ...] = (
    (
        "composition",
        {
            "case_kind": "flat-events",
            "event_count": 8,
            "depth": 1,
            "work_units": 8,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "nested-expressions",
            "event_count": 16,
            "depth": 3,
            "work_units": 16,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "source-templates",
            "event_count": 4,
            "depth": 1,
            "work_units": 4,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "flat-scale-sweep",
            "event_counts": [1, 8],
            "work_units": 9,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "nested-depth-sweep",
            "depths": [1, 2],
            "work_units": 24,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "lazy-expression-sweep",
            "graph_sizes": [1, 2],
            "work_units": 3,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "template-cold-warm",
            "event_count": 4,
            "work_units": 12,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "schedule-control-sweep",
            "event_counts": [2, 4],
            "control_counts": [0, 4],
            "work_units": 30,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "composition",
        {
            "case_kind": "fresh-process-determinism",
            "work_units": 4,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "serialization-bridge",
        {
            "case_kind": "phase-shape-sweep",
            "event_counts": [1, 2],
            "control_counts": [0, 2],
            "value_depths": [1, 2],
            "layer_counts": [1, 2],
            "fx_depths": [0, 1],
            "sample_path_counts": [1, 2],
            "sample_rate": 8_000,
            "work_units": 15,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "serialization-bridge",
        {
            "case_kind": "hostile-inputs",
            "sample_rate": 8_000,
            "work_units": 24,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "serialization-bridge",
        {
            "case_kind": "roundtrip",
            "event_count": 8,
            "sample_rate": 8_000,
            "work_units": 8,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "serialization-bridge",
        {
            "case_kind": "direct-serialized-parity",
            "event_count": 4,
            "sample_rate": 8_000,
            "work_units": 4,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "serialization-bridge",
        {
            "case_kind": "gil-heartbeat",
            "event_count": 24,
            "sample_rate": 8_000,
            "work_units": 24,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "voices-filters-automation",
        {
            "case_kind": "oscillator-polyphony",
            "sample_rate": 8_000,
            "polyphony": 1,
            "layer_count": 1,
            "work_units": 10,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "voices-filters-automation",
        {
            "case_kind": "layers-envelopes-filters-automation",
            "sample_rate": 8_000,
            "polyphony": 2,
            "layer_count": 3,
            "work_units": 6,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "sample-engine",
        {
            "case_kind": "generated-wav-decode-resample-cache",
            "source_rate": 8_000,
            "target_rate": 12_000,
            "playback_rate": "1.5",
            "work_units": 20,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "fx-mix-output",
        {
            "case_kind": "all-practical-fx",
            "sample_rate": 8_000,
            "work_units": 34,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "fx-mix-output",
        {
            "case_kind": "buses-output-normalization",
            "sample_rate": 8_000,
            "work_units": 4,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "streaming-sound",
        {
            "case_kind": "simulated-realtime-block-sink",
            "sample_rate": 8_000,
            "duration_ms": 100,
            "block_frames": 64,
            "work_units": 13,
            "required_counters": [],
        },
        ExecutionClass.SIMULATED_REALTIME,
    ),
    (
        "streaming-sound",
        {
            "case_kind": "public-sound-headless-state",
            "sample_rate": 8_000,
            "duration_ms": 40,
            "block_frames": 64,
            "work_units": 14,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "failures-longevity",
        {
            "case_kind": "fail-closed-validation",
            "sample_rate": 8_000,
            "cycles": 1,
            "work_units": 21,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "failures-longevity",
        {
            "case_kind": "bounded-longevity",
            "sample_rate": 8_000,
            "cycles": 3,
            "work_units": 3,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "voices-filters-automation",
        {
            "case_kind": "voice-rate-polyphony-matrix",
            "sample_rates": [8_000],
            "polyphonies": [1],
            "work_units": 10,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "voices-filters-automation",
        {
            "case_kind": "layer-envelope-filter-automation-matrix",
            "sample_rates": [8_000],
            "polyphonies": [1],
            "layer_counts": [2],
            "envelope_curves": [3],
            "automation_counts": [0, 1],
            "work_units": 11,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "sample-engine",
        {
            "case_kind": "decode-metadata-matrix",
            "work_units": 54,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "sample-engine",
        {
            "case_kind": "resample-slice-playback-rate-matrix",
            "source_rates": [8_000],
            "target_rates": [8_000],
            "playback_rates": ["1"],
            "work_units": 1,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "fx-mix-output",
        {
            "case_kind": "chain-bus-scaling-matrix",
            "sample_rate": 8_000,
            "chain_depths": [1],
            "bus_counts": [1],
            "work_units": 2,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "fx-mix-output",
        {
            "case_kind": "stateful-memory-file-output-scales",
            "sample_rate": 8_000,
            "duration_seconds": [1],
            "work_units": 2,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "streaming-sound",
        {
            "case_kind": "stateful-block-memory-file-parity",
            "sample_rate": 8_000,
            "duration_ms": 100,
            "block_frames": 64,
            "work_units": 2,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
    (
        "streaming-sound",
        {
            "case_kind": "stateful-route-guards",
            "sample_rate": 8_000,
            "duration_ms": 40,
            "block_frames": 64,
            "work_units": 3,
            "required_counters": [],
        },
        ExecutionClass.HEADLESS,
    ),
)


@pytest.mark.parametrize(("workload_id", "parameters", "execution_class"), _CASES)
def test_registry_dispatch_executes_every_synth_case_kind(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
) -> None:
    result = dispatch("synth", workload_id, parameters, execution_class)

    assert isinstance(result, SuiteExecution)
    assert result.summary
    assert result.diagnostics["work_units"] == parameters["work_units"]
    assert result.diagnostics["execution_class"] == execution_class.value
    assert result.diagnostics["physical_audio_requested"] is False
    assert result.diagnostics["physical_audio_qualified"] is False
    assert result.diagnostics["audibility_claimed"] is False
    device = result.diagnostics["device_qualification"]
    assert isinstance(device, dict)
    assert device["schema_version"] == 1
    assert device["requested"] is device["available"] is device["qualified"] is False
    assert result.diagnostics["path"]
    if workload_id == "serialization-bridge" and parameters["case_kind"] in {
        "roundtrip",
        "direct-serialized-parity",
        "gil-heartbeat",
    }:
        for name in (
            "python_to_dict_normalize_ns",
            "python_plan_container_ns",
            "serialized_validation_ns",
            "python_json_serialize_ns",
            "python_zlib_compress_ns",
            "python_json_bytes",
            "python_zlib_bytes",
            "native_plan_container_bytes",
            "pre_dsp_serialization_ns",
        ):
            value = result.diagnostics[name]
            assert isinstance(value, int)
            assert value >= 0
        assert isinstance(result.diagnostics["python_zlib_ratio"], float)
        assert result.diagnostics["python_zlib_ratio"] > 0.0
        if parameters["case_kind"] != "gil-heartbeat":
            lifecycle = result.diagnostics["benchmark_lifecycle"]
            assert isinstance(lifecycle, dict)
            assert lifecycle["schema_version"] == 2
    if parameters["case_kind"] == "direct-serialized-parity":
        for name in (
            "direct_payload_conversion",
            "direct_bridge_render",
            "serialized_bridge_compile_render",
        ):
            phase = result.diagnostics[name]
            assert isinstance(phase, dict)
            assert isinstance(phase["elapsed_ns"], int)
            assert phase["elapsed_ns"] >= 0
        copy_count = result.diagnostics["bridge_copy_count"]
        assert isinstance(copy_count, dict)
        assert copy_count["available"] is False
        serialized_input_bytes = result.diagnostics["serialized_bridge_input_bytes"]
        bridge_output_bytes = result.diagnostics["bridge_output_bytes"]
        assert isinstance(serialized_input_bytes, int)
        assert isinstance(bridge_output_bytes, int)
        assert serialized_input_bytes > 0
        assert bridge_output_bytes > 44
    if parameters["case_kind"] == "gil-heartbeat":
        observations = result.diagnostics["python_heartbeat_observations"]
        max_pause_ns = result.diagnostics["python_heartbeat_max_pause_ns"]
        render_elapsed_ns = result.diagnostics["python_heartbeat_render_elapsed_ns"]
        released_calls = result.diagnostics["gil_released_calls"]
        released_compile_calls = result.diagnostics["gil_released_compile_calls"]
        released_render_calls = result.diagnostics["gil_released_render_calls"]
        assert isinstance(observations, int)
        assert isinstance(max_pause_ns, int)
        assert isinstance(render_elapsed_ns, int)
        assert isinstance(released_calls, int)
        assert isinstance(released_compile_calls, int)
        assert isinstance(released_render_calls, int)
        assert observations >= 1
        assert max_pause_ns > 0
        assert render_elapsed_ns > 0
        assert released_calls >= 1
        assert released_compile_calls >= 1
        assert released_render_calls >= 1
    if parameters["case_kind"] == "flat-scale-sweep":
        points = result.diagnostics["scale_points"]
        assert isinstance(points, list)
        assert [point["declared_events"] for point in points] == [1, 8]
        assert all(point["expanded_events"] == point["declared_events"] for point in points)
        assert result.summary["rendered_audio"] is False
    if parameters["case_kind"] == "nested-depth-sweep":
        points = result.diagnostics["depth_points"]
        assert isinstance(points, list)
        assert [point["depth"] for point in points] == [1, 2]
        assert all(point["schedule_equivalent"] is True for point in points)
    if parameters["case_kind"] == "lazy-expression-sweep":
        families = result.diagnostics["expression_families"]
        assert isinstance(families, list)
        assert set(families) == {
            "arithmetic",
            "seeded-random",
            "choice-ring",
            "tick-look",
            "music",
            "conditions",
            "lazy-sleep-duration",
            "nested-containers",
            "track-call-binding-reuse",
        }
    if parameters["case_kind"] == "template-cold-warm":
        template = result.diagnostics["source_template"]
        assert isinstance(template, dict)
        assert template["multiple_outputs_exercised"] is True
        assert template["active_fx_handle_exercised"] is True
        compiled_assets = result.diagnostics["compiled_assets"]
        assert isinstance(compiled_assets, list)
        assert len(compiled_assets) == 4
    if parameters["case_kind"] == "schedule-control-sweep":
        assert result.summary["maximum_controls"] == 4
        schedule_points = result.diagnostics["schedule_points"]
        control_points = result.diagnostics["control_points"]
        assert isinstance(schedule_points, list)
        assert isinstance(control_points, list)
        assert len(schedule_points) == 8
        assert [point["control_count"] for point in control_points] == [
            0,
            4,
        ]
    if parameters["case_kind"] == "fresh-process-determinism":
        assert result.summary["same_seed_stable"] is True
        assert result.summary["unrelated_history_stable"] is True
        assert result.summary["changed_seed_differs"] is True
    if parameters["case_kind"] == "phase-shape-sweep":
        assert result.summary["serialization_profiles"] == 12
        assert result.summary["rendered_audio"] is False
        shape_axes = result.diagnostics["shape_axes"]
        profiles = result.diagnostics["profiles"]
        assert isinstance(shape_axes, dict)
        assert isinstance(profiles, list)
        assert set(shape_axes) == {
            "event_counts",
            "control_counts",
            "value_depths",
            "layer_counts",
            "fx_depths",
            "sample_path_counts",
        }
        for profile in profiles:
            assert isinstance(profile, dict)
            rust_diagnostics = profile["rust_compile_diagnostics"]
            bridge_copy_count = profile["bridge_copy_count"]
            assert isinstance(rust_diagnostics, dict)
            assert isinstance(bridge_copy_count, dict)
            assert rust_diagnostics["gil_released_compile_calls"] >= 1
            assert bridge_copy_count["available"] is False
    if parameters["case_kind"] == "hostile-inputs":
        assert result.summary == {"expected_failures": 24, "rendered_audio": False}
        failures = result.diagnostics["failures"]
        assert isinstance(failures, list)
        assert len(failures) == 24
    if parameters["case_kind"] == "simulated-realtime-block-sink":
        sink = result.diagnostics["sink"]
        assert isinstance(sink, dict)
        assert sink["underruns"] == sink["deadline_misses"] == 0
        assert sink["block_time_ns"]["count"] == sink["blocks"]
        assert sink["adapter_lifecycle"]["identity"]["route"] == (
            "deterministic-simulated-realtime-pcm-sink"
        )
    if parameters["case_kind"] == "generated-wav-decode-resample-cache":
        cache_identities = result.diagnostics["cache_identities"]
        assert isinstance(cache_identities, dict)
        assert len(cache_identities["cold"]) == len(cache_identities["warm"]) == 9
        cache_metrics = result.diagnostics["cache_metrics"]
        packaged_cases = result.diagnostics["packaged_sample_cases"]
        assert isinstance(cache_metrics, dict)
        assert isinstance(packaged_cases, list)
        assert cache_metrics["available"] is False
        assert set(packaged_cases) == {
            "reviewed-minimal-flac",
            "packaged-transient-flac",
            "packaged-loop-flac",
        }
    if parameters["case_kind"] == "voice-rate-polyphony-matrix":
        matrix = result.diagnostics["matrix"]
        assert isinstance(matrix, dict)
        assert len(matrix["cases"]) == 10
        assert matrix["sample_rates"] == [8_000]
        assert matrix["polyphonies"] == [1]
    if parameters["case_kind"] == "layer-envelope-filter-automation-matrix":
        matrix = result.diagnostics["matrix"]
        assert isinstance(matrix, dict)
        assert len(matrix["layers"]) == 1
        assert len(matrix["envelopes"]) == 2
        assert len(matrix["filters"]) == 6
        assert len(matrix["automation"]) == 2
    if parameters["case_kind"] == "decode-metadata-matrix":
        matrix = result.diagnostics["matrix"]
        assert isinstance(matrix, dict)
        assert len(matrix["pcm_cases"]) == 24
        assert len(matrix["flac_cases"]) == 3
        assert matrix["temporary_files_removed"] is True
    if parameters["case_kind"] == "resample-slice-playback-rate-matrix":
        matrix = result.diagnostics["matrix"]
        assert isinstance(matrix, dict)
        assert len(matrix["cases"]) == 1
        assert matrix["temporary_files_removed"] is True
    if parameters["case_kind"] == "chain-bus-scaling-matrix":
        oracles = result.diagnostics["oracles"]
        assert isinstance(oracles, dict)
        assert len(oracles["chain_cases"]) == 1
        assert len(oracles["bus_cases"]) == 1
    if parameters["case_kind"] == "stateful-memory-file-output-scales":
        oracles = result.diagnostics["oracles"]
        assert isinstance(oracles, dict)
        assert len(oracles["cases"]) == 1
        assert oracles["cases"][0]["exact_sink_parity"] is True
        assert oracles["temporary_files_removed"] is True
    if parameters["case_kind"] == "stateful-block-memory-file-parity":
        assert result.diagnostics["true_block_streaming"] is True
        assert result.diagnostics["exact_sink_parity"] is True
        assert result.diagnostics["temporary_files_removed"] is True
    if parameters["case_kind"] == "stateful-route-guards":
        guards = result.diagnostics["guards"]
        assert isinstance(guards, dict)
        assert guards["configurable_block_partition_available"] is False
        assert guards["block_session_diagnostics_available"] is False
        assert result.summary["physical_device_opened"] is False


def test_synth_dispatch_rejects_wrong_route_without_substitution() -> None:
    parameters = {
        "case_kind": "flat-events",
        "event_count": 4,
        "depth": 1,
        "work_units": 4,
        "required_counters": [],
    }

    with pytest.raises(SynthPathError, match="No alternate audio route"):
        dispatch("synth", "composition", parameters, ExecutionClass.SIMULATED_REALTIME)


def test_synth_dispatch_rejects_unexecuted_parameters() -> None:
    parameters = {
        "case_kind": "flat-events",
        "event_count": 4,
        "depth": 1,
        "work_units": 4,
        "required_counters": [],
        "legacy_scenario": "ignored",
    }

    with pytest.raises(SynthWorkloadError, match="unexecuted or unsupported"):
        dispatch("synth", "composition", parameters, ExecutionClass.HEADLESS)
