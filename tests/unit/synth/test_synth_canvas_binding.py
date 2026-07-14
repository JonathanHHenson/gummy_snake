"""Regression coverage for the canvas-owned PyO3 synth adapter."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from gummysnake import synth as sy
from gummysnake.exceptions import ArgumentValidationError
from gummysnake.rust.canvas import canvas_abi_version, require_canvas_runtime


def _sine_event() -> dict[str, object]:
    return {
        "node_id": 1,
        "order": 0,
        "kind": "play",
        "time_seconds": 0.0,
        "value": 60,
        "opts": {"release": 0.01, "amp": 0.1},
        "synth_name": "_sine",
        "synth_opts": {},
        "fx_chain": [],
        "controls": [],
    }


def test_canvas_owned_synth_functions_preserve_names_outputs_and_value_errors() -> None:
    runtime = require_canvas_runtime()

    event_wav = runtime.synth_render_event_wav(_sine_event(), 8_000)
    plan_wav = runtime.synth_render_plan_wav([_sine_event()], 0.02, 8_000)

    assert event_wav.startswith(b"RIFF")
    assert plan_wav.startswith(b"RIFF")
    assert canvas_abi_version() == 21

    with pytest.raises(ValueError) as serialized_error:
        runtime.synth_render_serialized_plan_wav(b"", 8_000)
    assert str(serialized_error.value) == "ValueError: serialized synth physical plan is too short."

    with pytest.raises(ValueError) as duration_error:
        runtime.synth_render_plan_wav([], -0.01, 8_000)
    assert str(duration_error.value) == "synth plan render duration cannot be negative."


def test_canvas_compiled_program_reuses_one_validated_schedule_for_rendering() -> None:
    runtime = require_canvas_runtime()

    @sy.track(seed=320)
    def compiled_track() -> None:
        with sy.synth("_sine"):
            sy.play(60, sustain=0.01, release=0.01, amp=0.1)

    plan = compiled_track().physical_plan(duration=0.03)
    program = runtime.CanvasSynthProgram.from_serialized(plan.to_bytes(), 8_000)

    assert program.sample_rate == 8_000
    assert program.duration_frames == 240
    assert program.event_count == 1
    assert program.render_wav() == runtime.synth_render_serialized_plan_wav(plan.to_bytes(), 8_000)


def _parallel_events(count: int = 16) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for index in range(count):
        event = _sine_event()
        event.update(
            {
                "node_id": index + 1,
                "order": index,
                "time_seconds": index * 0.003,
                "value": 60 + index % 7,
                "opts": {
                    "attack": 0.005,
                    "sustain": 0.15,
                    "release": 0.1,
                    "amp": 0.05,
                },
            }
        )
        events.append(event)
    return events


def test_synth_workers_preserve_exact_wav_and_report_bounded_parallel_regions() -> None:
    runtime = require_canvas_runtime()
    events = _parallel_events()
    try:
        sy.configure_workers(1)
        expected = runtime.synth_render_plan_wav(events, 0.4, 48_000)
        for worker_count in (2, 4, 8, "auto"):
            sy.reset_synth_diagnostics()
            resolved = sy.configure_workers(worker_count)
            actual = runtime.synth_render_plan_wav(events, 0.4, 48_000)
            diagnostics = sy.synth_diagnostics()
            assert actual == expected
            assert diagnostics["worker_count"] == resolved
            assert diagnostics["parallel_regions"] == 0
            assert diagnostics["parallel_tasks"] == 0
            assert diagnostics["parallel_scratch_peak_bytes"] == 0
            assert diagnostics["worker_pool_initializations"] == 0
            assert diagnostics["causal_normaliser_contract_version"] == 1
            assert diagnostics["audio_queue_low_water_frames"] > 0
            assert (
                diagnostics["audio_queue_high_water_frames"]
                > diagnostics["audio_queue_low_water_frames"]
            )
            assert diagnostics["audio_active_voices"] == 0
    finally:
        sy.configure_workers("auto")


def test_synth_render_releases_gil_for_python_heartbeat() -> None:
    runtime = require_canvas_runtime()

    @sy.track(seed=320)
    def heartbeat_track() -> None:
        with sy.synth("_sine"):
            for index in range(24):
                sy.play(
                    60 + index % 7,
                    attack=0.005,
                    sustain=0.15,
                    release=0.1,
                    amp=0.05,
                )
                sy.sleep(0.003)

    payload = heartbeat_track().physical_plan(duration=0.5).to_bytes()
    running = threading.Event()
    stop = threading.Event()
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        running.set()
        while not stop.is_set():
            heartbeats += 1
            time.sleep(0)

    thread = threading.Thread(target=heartbeat, name="synth-gil-heartbeat")
    thread.start()
    assert running.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while heartbeats == 0 and time.monotonic() < deadline:
        time.sleep(0.001)
    baseline = heartbeats
    try:
        sy.reset_synth_diagnostics()
        runtime.synth_render_serialized_plan_wav(payload, 48_000)
    finally:
        stop.set()
        thread.join(timeout=1.0)
        sy.configure_workers("auto")
    assert not thread.is_alive()
    assert heartbeats > baseline
    diagnostics = sy.synth_diagnostics()
    assert diagnostics["gil_released_calls"] >= 1
    assert diagnostics["gil_released_compile_calls"] >= 1
    assert diagnostics["gil_released_render_calls"] >= 1


def test_rust_wav_file_binding_releases_gil_and_preserves_bytes(tmp_path: Path) -> None:
    runtime = require_canvas_runtime()
    plan_wav = runtime.synth_render_plan_wav(_parallel_events(4), 0.35, 16_000)
    path = tmp_path / "cached.wav"
    sy.reset_synth_diagnostics()

    runtime.synth_write_wav_file(plan_wav, str(path))

    assert path.read_bytes() == plan_wav
    assert sy.synth_diagnostics()["gil_released_wav_write_calls"] == 1


def test_sample_and_loaded_sound_decode_report_gil_release(tmp_path: Path) -> None:
    runtime = require_canvas_runtime()
    path = tmp_path / "decode.wav"
    path.write_bytes(runtime.synth_render_plan_wav(_parallel_events(2), 0.3, 8_000))
    sy.reset_synth_diagnostics()

    duration = runtime.synth_sample_duration(str(path))
    sound = runtime.CanvasSound.from_file(str(path))

    assert duration > 0.0
    assert sound.duration == pytest.approx(duration)
    assert sy.synth_diagnostics()["gil_released_decode_calls"] == 2


def test_track_save_uses_gil_released_rust_render_and_wav_write(tmp_path: Path) -> None:
    @sy.track(seed=320)
    def saved_track() -> None:
        with sy.synth("_sine"):
            sy.play(60, sustain=0.08, release=0.04, amp=0.05)

    output = tmp_path / "rendered.wav"
    sy.reset_synth_diagnostics()

    assert saved_track().save(output, duration=0.2, sample_rate=16_000) == output
    assert output.read_bytes().startswith(b"RIFF")
    diagnostics = sy.synth_diagnostics()
    assert diagnostics["gil_released_compile_calls"] == 1
    assert diagnostics["gil_released_render_calls"] == 1
    assert diagnostics["gil_released_wav_write_calls"] == 1


def test_public_worker_configuration_rejects_unbounded_values() -> None:
    for invalid in (True, 0, 3, 16, "default"):
        with pytest.raises(ArgumentValidationError, match="worker count"):
            sy.configure_workers(invalid)  # type: ignore[arg-type]


def test_canvas_synth_binding_rejects_unknown_dispatch_and_untyped_values() -> None:
    runtime = require_canvas_runtime()

    unknown_synth = _sine_event()
    unknown_synth["synth_name"] = "_unknown"
    with pytest.raises(ValueError, match="unsupported primitive synth"):
        runtime.synth_render_event_wav(unknown_synth, 8_000)

    unknown_fx = _sine_event()
    unknown_fx["fx_chain"] = [{"id": 1, "name": "unknown", "opts": {}}]
    with pytest.raises(ValueError, match="no dry-pass fallback"):
        runtime.synth_render_event_wav(unknown_fx, 8_000)

    unknown_chain = _sine_event()
    unknown_chain["fx_chain"] = [
        {
            "id": 1,
            "name": "_chain",
            "opts": {"ops": [{"op": "unknown_chain_op"}]},
        }
    ]
    with pytest.raises(ValueError, match="unsupported synth FX chain operation"):
        runtime.synth_render_event_wav(unknown_chain, 8_000)

    unsupported_value = _sine_event()
    unsupported_value["value"] = object()
    with pytest.raises(ValueError, match="synth payload values must be"):
        runtime.synth_render_event_wav(unsupported_value, 8_000)

    non_string_key = _sine_event()
    non_string_key["opts"] = {1: 2}
    with pytest.raises(ValueError, match="keys must be strings"):
        runtime.synth_render_event_wav(non_string_key, 8_000)

    non_finite = _sine_event()
    non_finite["opts"] = {"release": float("nan")}
    with pytest.raises(ValueError, match="finite"):
        runtime.synth_render_event_wav(non_finite, 8_000)

    unknown_key = _sine_event()
    unknown_key["unexpected"] = True
    with pytest.raises(ValueError, match="unsupported key"):
        runtime.synth_render_event_wav(unknown_key, 8_000)
