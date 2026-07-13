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
            "work_units": 16,
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
    assert result.diagnostics["path"]
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
