"""Bounded production-path workloads for the replacement Synth benchmark suite."""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, sleep
from typing import Any

from benchmarks.governance import ExecutionClass
from benchmarks.suites.registry import SuiteExecution

from .diagnostics import path_diagnostics, require_route
from .fixtures import fixture_manifest, generated_sample_files, validate_manifest
from .oracles import (
    SynthOracleError,
    assert_envelope_shape,
    assert_expected_failure,
    assert_frequency,
    assert_repeatable,
    assert_wav_contract,
    pcm_data,
    semantic_plan_digest,
)


class SynthWorkloadError(ValueError):
    """A static Synth workload declaration is unknown, unsafe, or internally inconsistent."""


_FX_OPTIONS: Mapping[str, Mapping[str, object]] = {
    "bitcrusher": {"sample_rate": 2_000, "bits": 6},
    "krush": {"gain": 5.0, "cutoff": 90, "res": 0.2},
    "reverb": {"room": 0.35, "damp": 0.4, "tail": 0.04},
    "gverb": {"room": 3.0, "release": 0.04, "spread": 0.7},
    "level": {"amp": 0.6},
    "echo": {"phase": 0.008, "decay": 0.024, "max_phase": 0.05},
    "slicer": {"phase": 0.012, "wave": 2},
    "panslicer": {"phase": 0.012, "wave": 2},
    "wobble": {"phase": 0.025, "cutoff_min": 45, "cutoff_max": 100},
    "ixi_techno": {"phase": 0.025, "cutoff_min": 45, "cutoff_max": 95},
    "compressor": {"threshold": 0.05, "slope_above": 0.2},
    "whammy": {"transpose": 7},
    "rlpf": {"cutoff": 80, "res": 0.5},
    "nrlpf": {"cutoff": 80, "res": 0.5},
    "rhpf": {"cutoff": 70, "res": 0.5},
    "nrhpf": {"cutoff": 70, "res": 0.5},
    "hpf": {"cutoff": 70},
    "nhpf": {"cutoff": 70},
    "lpf": {"cutoff": 80},
    "nlpf": {"cutoff": 80},
    "normaliser": {"level": 0.7},
    "distortion": {"distort": 0.6},
    "pan": {"pan": -0.65},
    "bpf": {"centre": 80, "res": 0.5},
    "nbpf": {"centre": 80, "res": 0.5},
    "rbpf": {"centre": 80, "res": 0.5},
    "nrbpf": {"centre": 80, "res": 0.5},
    "band_eq": {"freq": 80, "db": -8},
    "tanh": {"krunch": 8},
    "pitch_shift": {"pitch": 7},
    "ring_mod": {"freq": 38, "mod_amp": 0.8},
    "octaver": {"super_amp": 0.6, "sub_amp": 0.4, "subsub_amp": 0.2},
    "vowel": {"vowel_sound": 3, "voice": 2},
    "flanger": {"phase": 0.025, "delay": 2, "depth": 4, "feedback": 0.2},
}

_OSCILLATORS = (
    "sine",
    "saw",
    "pulse",
    "tri",
    "fm",
    "noise",
    "pnoise",
    "bnoise",
    "gnoise",
    "cnoise",
)

_ALLOWED_PARAMETERS: Mapping[str, frozenset[str]] = {
    "composition": frozenset(
        {"case_kind", "event_count", "depth", "work_units", "required_counters"}
    ),
    "serialization-bridge": frozenset(
        {
            "case_kind",
            "event_count",
            "sample_rate",
            "worker_count",
            "work_units",
            "required_counters",
        }
    ),
    "voices-filters-automation": frozenset(
        {
            "case_kind",
            "sample_rate",
            "polyphony",
            "layer_count",
            "work_units",
            "required_counters",
        }
    ),
    "sample-engine": frozenset(
        {
            "case_kind",
            "source_rate",
            "target_rate",
            "playback_rate",
            "work_units",
            "required_counters",
        }
    ),
    "fx-mix-output": frozenset({"case_kind", "sample_rate", "work_units", "required_counters"}),
    "streaming-sound": frozenset(
        {
            "case_kind",
            "sample_rate",
            "duration_ms",
            "block_frames",
            "work_units",
            "required_counters",
        }
    ),
    "failures-longevity": frozenset(
        {"case_kind", "sample_rate", "cycles", "work_units", "required_counters"}
    ),
}


def _integer(
    parameters: Mapping[str, object], name: str, *, minimum: int = 1, maximum: int = 1_000_000
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise SynthWorkloadError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(
    parameters: Mapping[str, object], name: str, *, minimum: float, maximum: float
) -> float:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise SynthWorkloadError(f"{name} must be numeric")
    try:
        result = float(value)
    except ValueError as error:
        raise SynthWorkloadError(f"{name} must be numeric") from error
    if not minimum <= result <= maximum:
        raise SynthWorkloadError(f"{name} must be in [{minimum}, {maximum}]")
    return result


def _expected_work_units(workload_id: str, case_kind: str, parameters: Mapping[str, object]) -> int:
    if workload_id == "composition":
        event_count = _integer(parameters, "event_count", maximum=65_536)
        if case_kind == "nested-expressions":
            depth = _integer(parameters, "depth", minimum=1, maximum=8)
            expanded_events = 2 ** (depth + 1)
            if event_count != expanded_events:
                raise SynthWorkloadError(
                    "nested-expressions event_count must equal its two-branch expanded event count"
                )
        return event_count
    if workload_id == "serialization-bridge" and case_kind in {
        "roundtrip",
        "direct-serialized-parity",
        "gil-heartbeat",
    }:
        return _integer(parameters, "event_count", maximum=16_384)
    if workload_id == "voices-filters-automation":
        if case_kind == "oscillator-polyphony":
            return len(_OSCILLATORS)
        if case_kind == "layers-envelopes-filters-automation":
            return _integer(parameters, "polyphony", maximum=12) * _integer(
                parameters, "layer_count", maximum=16
            )
    if workload_id == "sample-engine" and case_kind == "generated-wav-decode-resample-cache":
        return 20  # Nine cold/warm metadata pairs plus two rendered sample paths.
    if workload_id == "fx-mix-output":
        if case_kind == "all-practical-fx":
            return len(_FX_OPTIONS)
        if case_kind == "buses-output-normalization":
            return 4
    if workload_id == "streaming-sound":
        if case_kind == "public-sound-headless-state":
            return 14
        if case_kind == "simulated-realtime-block-sink":
            sample_rate = _integer(parameters, "sample_rate", maximum=96_000)
            duration_ms = _integer(parameters, "duration_ms", maximum=300_000)
            block_frames = _integer(parameters, "block_frames", maximum=16_384)
            frames = (sample_rate * duration_ms + 999) // 1_000
            return (frames + block_frames - 1) // block_frames
    if workload_id == "failures-longevity":
        if case_kind == "fail-closed-validation":
            return 16
        if case_kind == "bounded-longevity":
            return _integer(parameters, "cycles", maximum=1_000)
    raise SynthWorkloadError(f"unknown {workload_id} case_kind: {case_kind!r}")


def _validate_parameters(workload_id: str, parameters: Mapping[str, object]) -> tuple[str, int]:
    allowed = _ALLOWED_PARAMETERS.get(workload_id)
    if allowed is None:
        raise SynthWorkloadError(f"unknown Synth workload id: {workload_id!r}")
    unexpected = sorted(set(parameters) - allowed)
    if unexpected:
        raise SynthWorkloadError(
            f"{workload_id} has unexecuted or unsupported parameter(s): {', '.join(unexpected)}"
        )
    case_kind = parameters.get("case_kind")
    if not isinstance(case_kind, str) or not case_kind:
        raise SynthWorkloadError("Synth workload case_kind must be a non-empty string")
    work_units = _integer(parameters, "work_units", maximum=10_000_000)
    expected_work_units = _expected_work_units(workload_id, case_kind, parameters)
    if work_units != expected_work_units:
        raise SynthWorkloadError(
            f"{case_kind} requires work_units={expected_work_units}, got {work_units}"
        )
    counters = parameters.get("required_counters", [])
    if not isinstance(counters, list) or not all(isinstance(item, str) for item in counters):
        raise SynthWorkloadError("required_counters must be a list of strings")
    return case_kind, work_units


def _runtime() -> Any:
    from gummysnake.synth.synth_runtime.physical.rendering import _require_synth_runtime

    return _require_synth_runtime()


def _voice_track(
    synth_name: str,
    *,
    notes: object = 69,
    opts: Mapping[str, object] | None = None,
    fx_name: str | None = None,
    fx_opts: Mapping[str, object] | None = None,
) -> Any:
    from gummysnake import synth as sy

    @sy.track(seed=310)
    def benchmark_voice() -> None:
        with sy.synth(f"_{synth_name}"):
            if fx_name is None:
                sy.play(notes, **dict(opts or {}))
            else:
                with sy.fx(f"_{fx_name}", **dict(fx_opts or {})):
                    sy.play(notes, **dict(opts or {}))

    return benchmark_voice()


def _physical_voice_plan(
    synth_name: str,
    *,
    duration: float,
    notes: object = 69,
    opts: Mapping[str, object] | None = None,
    fx_name: str | None = None,
    fx_opts: Mapping[str, object] | None = None,
) -> Any:
    return _voice_track(
        synth_name,
        notes=notes,
        opts=opts,
        fx_name=fx_name,
        fx_opts=fx_opts,
    ).physical_plan(duration=duration)


def _composition(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    from gummysnake import synth as sy

    event_count = _integer(parameters, "event_count", maximum=65_536)
    depth = _integer(parameters, "depth", minimum=1, maximum=8)
    if case_kind == "flat-events":

        @sy.track(seed=310)
        def composition_flat() -> None:
            for index in range(event_count):
                sy.play(48 + index % 24, amp=0.2, release=0.005)
                sy.sleep(0.001)

        track = composition_flat()
    elif case_kind == "nested-expressions":

        def nested(level: int) -> None:
            if level == 0:
                value = sy.choose(sy.ring(60, 62, 64, 67)) + sy.tick("nested") % 2
                sy.play(
                    value,
                    amp=sy.rrand(0.1, 0.3),
                    pan=sy.choose([-0.5, 0.0, 0.5]),
                ).when(value >= 60)
                sy.sleep(0.002)
                return
            with sy.loop(times=2):
                nested(level - 1)

        @sy.track(seed=310)
        def composition_nested() -> None:
            with sy.thread(name="parallel-expression-branch"):
                nested(depth)
            nested(depth)

        track = composition_nested()
    elif case_kind == "source-templates":

        @sy.synth(name="benchmark-layer-template")
        def layer_template(note: object = 60, **opts: object) -> None:
            signal = (
                sy.synth_input(note, defaults={"release": 0.02}, **opts)
                .layer("sine", amp=0.55)
                .layer("saw", transpose=12, amp=0.2)
            )
            signal.output()

        @sy.fx(name="benchmark-fx-template")
        def fx_template(**opts: object) -> None:
            signal = sy.fx_input().filter(kind="low", cutoff=95).pan(pan=-0.2)
            sy.fx_output(signal, **opts)

        @sy.track(seed=310)
        def composition_templates() -> None:
            with (
                sy.synth("benchmark-layer-template", release=0.03),
                sy.fx("benchmark-fx-template", cutoff=82, mix=0.75),
            ):
                for index in range(event_count):
                    sy.play(60 + index % 7, amp=0.25)
                    sy.sleep(0.002)

        track = composition_templates()
    else:
        raise SynthWorkloadError(f"unknown composition case_kind: {case_kind!r}")
    plan = track.physical_plan(duration=max(0.05, event_count * 0.003))
    if not plan.events:
        raise SynthOracleError("composition workload expanded no events")
    digest = semantic_plan_digest(plan.to_dict())
    diagnostics = path_diagnostics(
        execution_class,
        ("python-public-track-api", "logical-plan", "physical-expansion", "semantic-digest"),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "plan_digest": digest,
            "event_count": len(plan.events),
            "control_count": len(plan.controls),
            "logical_node_count": len(track.logical_plan.nodes),
            "known_identity_policy": (
                "stable plan-local event and instance identifiers are seeded by the track"
            ),
        },
    )
    return SuiteExecution(
        diagnostics=diagnostics,
        summary={
            "events": len(plan.events),
            "controls": len(plan.controls),
            "plan_bytes": len(plan.to_bytes()),
            "digest": digest,
        },
    )


def _bridge_plan(event_count: int) -> Any:
    from gummysnake import synth as sy

    @sy.track(seed=310)
    def bridge_track() -> None:
        with sy.synth("_sine"):
            for index in range(event_count):
                handle = sy.play(
                    57 + index % 12,
                    attack=0.001,
                    sustain=0.04,
                    release=0.02,
                    amp=0.15,
                    metadata={"index": index, "values": [True, None, index]},
                )
                if index % 4 == 0:
                    sy.control(handle, pan=-0.25 + (index % 3) * 0.25)
                sy.sleep(0.002)

    return bridge_track().physical_plan(duration=max(0.05, event_count * 0.003))


def _serialized_render_heartbeat(
    runtime: Any,
    serialized_plan: bytes,
    sample_rate: int,
    semantic_digest: str,
    execution_class: ExecutionClass,
    work_units: int,
    event_count: int,
) -> SuiteExecution:
    """Measure Python progress while the synchronous native bridge renders a plan."""

    ready = threading.Event()
    measuring = threading.Event()
    stop = threading.Event()
    observed = {"ticks": 0, "max_pause_ns": 0, "last_tick_ns": 0}

    def heartbeat() -> None:
        last_tick_ns = 0
        ready.set()
        while not stop.is_set():
            if measuring.is_set():
                now_ns = perf_counter_ns()
                if last_tick_ns:
                    observed["max_pause_ns"] = max(observed["max_pause_ns"], now_ns - last_tick_ns)
                last_tick_ns = now_ns
                observed["last_tick_ns"] = now_ns
                observed["ticks"] += 1
            else:
                last_tick_ns = 0
            sleep(0)

    thread = threading.Thread(target=heartbeat, name="gummysnake-synth-bench-heartbeat")
    thread.start()
    if not ready.wait(timeout=1.0):
        stop.set()
        thread.join(timeout=1.0)
        raise SynthWorkloadError("Python heartbeat did not start before serialized Synth render")
    runtime.synth_reset_diagnostics()
    measuring.set()
    render_started_ns = perf_counter_ns()
    try:
        payload = bytes(runtime.synth_render_serialized_plan_wav(serialized_plan, sample_rate))
    finally:
        render_finished_ns = perf_counter_ns()
        render_elapsed_ns = render_finished_ns - render_started_ns
        if observed["last_tick_ns"]:
            observed["max_pause_ns"] = max(
                observed["max_pause_ns"], render_finished_ns - observed["last_tick_ns"]
            )
        measuring.clear()
        stop.set()
        thread.join(timeout=1.0)
    if thread.is_alive():
        raise SynthWorkloadError("Python heartbeat thread did not terminate after Synth render")
    if observed["ticks"] < 1 or observed["max_pause_ns"] <= 0:
        raise SynthOracleError(
            "serialized Synth render did not permit enough Python heartbeat progress to measure "
            "a scheduling pause"
        )
    signal = assert_wav_contract(payload, sample_rate=sample_rate)
    runtime_diagnostics = dict(runtime.synth_diagnostics())
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-heartbeat-thread",
            "serialized-pyo3-zlib-json",
            "gummy-synth-rust-dsp",
            "wav-memory-sink",
        ),
        work_units=work_units,
        details={
            "semantic_digest": semantic_digest,
            "pcm_digest": "sha256:" + sha256(payload).hexdigest(),
            "python_heartbeat_observations": observed["ticks"],
            "python_heartbeat_max_pause_ns": observed["max_pause_ns"],
            "python_heartbeat_render_elapsed_ns": render_elapsed_ns,
            "python_heartbeat_progressed": True,
            **runtime_diagnostics,
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "events": event_count,
            "wav_bytes": len(payload),
            "frames": signal.frames,
            "python_heartbeat_observations": observed["ticks"],
            "python_heartbeat_max_pause_ns": observed["max_pause_ns"],
        },
    )


def _serialization_bridge(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    event_count = _integer(parameters, "event_count", maximum=16_384)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    base_plan = _bridge_plan(event_count)
    plan = type(base_plan)(
        base_plan.events,
        base_plan.controls,
        base_plan.duration_seconds,
        sample_rate,
        base_plan.metadata,
    )
    metadata = {"benchmark": "synth-v1", "nested": {"depth": [1, 2, 3]}}
    plan_dict = plan.to_dict(metadata=metadata)
    semantic_digest = semantic_plan_digest(plan_dict)
    serialized = plan.to_bytes(metadata=metadata)
    loaded = type(plan).from_bytes(serialized)
    if semantic_plan_digest(loaded.to_dict()) != semantic_plan_digest(
        plan.to_dict(metadata=metadata)
    ):
        raise SynthOracleError("physical plan serialization changed normalized semantics")
    runtime = _runtime()
    if case_kind == "roundtrip":
        diagnostics = path_diagnostics(
            execution_class,
            ("physical-plan", "to-dict", "json-zlib-container", "python-roundtrip"),
            work_units=work_units,
            details={"rendered_audio": False, "semantic_digest": semantic_digest},
        )
        return SuiteExecution(
            diagnostics,
            {
                "events": len(plan.events),
                "controls": len(plan.controls),
                "raw_dict_keys": len(plan_dict),
                "compressed_bytes": len(serialized),
            },
        )
    worker_count = parameters.get("worker_count", "auto")
    if isinstance(worker_count, bool) or worker_count not in {1, 2, 4, 8, "auto"}:
        raise SynthWorkloadError("worker_count must be one of 1, 2, 4, 8, or 'auto'")
    runtime.synth_set_worker_count(worker_count)
    try:
        if case_kind == "direct-serialized-parity":
            from gummysnake.synth.synth_runtime.physical.rendering import _event_payloads

            runtime.synth_reset_diagnostics()
            direct = bytes(
                runtime.synth_render_plan_wav(
                    _event_payloads(plan), plan.duration_seconds, sample_rate
                )
            )
            bridged = bytes(runtime.synth_render_serialized_plan_wav(plan.to_bytes(), sample_rate))
            runtime_diagnostics = dict(runtime.synth_diagnostics())
            digest = assert_repeatable(
                direct, bridged, label="direct and serialized PyO3 bridge routes"
            )
            signal = assert_wav_contract(bridged, sample_rate=sample_rate)
            diagnostics = path_diagnostics(
                execution_class,
                (
                    "python-physical-plan",
                    "direct-pyo3-typed-values",
                    "serialized-pyo3-zlib-json",
                    "gummy-synth-rust-dsp",
                    "wav-memory-sink",
                ),
                work_units=work_units,
                details={
                    "semantic_digest": semantic_digest,
                    "pcm_digest": digest,
                    **runtime_diagnostics,
                },
            )
            return SuiteExecution(
                diagnostics,
                {
                    "events": len(plan.events),
                    "controls": len(plan.controls),
                    "wav_bytes": len(bridged),
                    "frames": signal.frames,
                    "worker_count": runtime_diagnostics["worker_count"],
                    "parallel_regions": runtime_diagnostics["parallel_regions"],
                    "parallel_tasks": runtime_diagnostics["parallel_tasks"],
                },
            )
        if case_kind == "gil-heartbeat":
            return _serialized_render_heartbeat(
                runtime,
                plan.to_bytes(),
                sample_rate,
                semantic_digest,
                execution_class,
                work_units,
                len(plan.events),
            )
    finally:
        runtime.synth_set_worker_count("auto")
    raise SynthWorkloadError(f"unknown serialization case_kind: {case_kind!r}")


def _voices_filters_automation(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    polyphony = _integer(parameters, "polyphony", minimum=1, maximum=12)
    layer_count = _integer(parameters, "layer_count", minimum=1, maximum=16)
    summaries: dict[str, object] = {}
    digests: list[str] = []
    path: tuple[str, ...]
    if case_kind == "oscillator-polyphony":
        notes = [69 + index for index in range(polyphony)]
        for oscillator in _OSCILLATORS:
            plan = _physical_voice_plan(
                oscillator,
                duration=0.06,
                notes=notes,
                opts={"attack": 0.002, "sustain": 0.025, "release": 0.012, "amp": 0.25},
            )
            first = plan.render(sample_rate=sample_rate)
            second = plan.render(sample_rate=sample_rate)
            digests.append(assert_repeatable(first, second, label=f"{oscillator} oscillator"))
            summary = assert_wav_contract(first, sample_rate=sample_rate)
            summaries[oscillator] = summary.to_dict()
            if oscillator == "sine" and polyphony == 1:
                summaries["sine_frequency_hz"] = assert_frequency(
                    first, expected_hz=440.0, tolerance_hz=15.0
                )
        path = ("public-track", "serialized-pyo3", "rust-oscillator-voices", "wav-memory")
    elif case_kind == "layers-envelopes-filters-automation":
        waves = ("sine", "saw", "pulse", "tri", "noise", "fm")
        layers = [
            {
                "wave": waves[index % len(waves)],
                "transpose": (index % 5) * 0.1,
                "amp": 1.0 / layer_count,
                "opts": {"pulse_width": 0.35, "divisor": 2.0, "depth": 0.8},
            }
            for index in range(layer_count)
        ]
        from gummysnake import synth as sy

        @sy.track(seed=310)
        def automated_layers() -> None:
            with sy.synth("_layered"):
                handle = sy.play(
                    [60 + index for index in range(polyphony)],
                    layers=layers,
                    attack=0.012,
                    decay=0.008,
                    sustain=0.035,
                    release=0.02,
                    env_curve=3,
                    cutoff=105,
                    res=0.45,
                    amp=0.35,
                    pulse_width=0.35,
                )
                sy.sleep(0.018)
                sy.control(handle, note=67, pan=-0.5, cutoff=72, res=0.7, pulse_width=0.65)
                sy.sleep(0.018)
                sy.control(handle, note=64, pan=0.5, cutoff=96, amp=0.2)

        plan = automated_layers().physical_plan(duration=0.09)
        payload = plan.render(sample_rate=sample_rate)
        summary = assert_wav_contract(payload, sample_rate=sample_rate)
        summaries["layered"] = summary.to_dict()
        envelope_payload = _physical_voice_plan(
            "sine",
            duration=0.09,
            opts={
                "attack": 0.02,
                "decay": 0.0,
                "sustain": 0.04,
                "release": 0.02,
                "env_curve": 3,
                "amp": 0.25,
            },
        ).render(sample_rate=sample_rate)
        summaries["envelope"] = dict(assert_envelope_shape(envelope_payload))
        summaries["controls"] = len(plan.controls)
        digests.append(
            assert_repeatable(payload, plan.render(sample_rate=sample_rate), label="layered voice")
        )
        path = (
            "public-track",
            "serialized-pyo3",
            "rust-layered-voices",
            "adsr-filter-automation",
            "wav-memory",
        )
    else:
        raise SynthWorkloadError(f"unknown voice case_kind: {case_kind!r}")
    diagnostics = path_diagnostics(
        execution_class,
        path,
        work_units=work_units,
        details={"oracles": summaries, "repeat_digests": digests},
    )
    return SuiteExecution(
        diagnostics,
        {
            "oscillator_or_layer_cases": len(digests),
            "polyphony": polyphony,
            "layers": layer_count,
            "sample_rate": sample_rate,
        },
    )


def _sample_engine(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    if case_kind != "generated-wav-decode-resample-cache":
        raise SynthWorkloadError(f"unknown sample-engine case_kind: {case_kind!r}")
    source_rate = _integer(parameters, "source_rate", minimum=8_000, maximum=96_000)
    target_rate = _integer(parameters, "target_rate", minimum=8_000, maximum=96_000)
    playback_rate = _number(parameters, "playback_rate", minimum=-8.0, maximum=8.0)
    if playback_rate == 0.0:
        raise SynthWorkloadError("playback_rate cannot be zero")
    runtime = _runtime()
    validate_manifest()
    duration_results: dict[str, float] = {}
    render_summaries: dict[str, object] = {}
    with generated_sample_files(sample_rate=source_rate) as generated:
        for name, path in generated.paths.items():
            duration = float(runtime.synth_sample_duration(str(path)))
            repeated = float(runtime.synth_sample_duration(str(path)))
            if duration != repeated or not 0.12 <= duration <= 0.13:
                raise SynthOracleError(
                    f"sample duration/cache reuse mismatch for {name}: {duration}"
                )
            duration_results[name] = duration
        stereo_path = generated.paths["stereo-16bit"]
        from gummysnake import synth as sy

        @sy.track(seed=310)
        def generated_sample_track() -> None:
            sy.sample(
                stereo_path,
                start=0.125,
                finish=0.875,
                rate=playback_rate,
                attack=0.003,
                release=0.004,
                pan=0.2,
                cutoff=110,
                amp=0.6,
            )

        plan = generated_sample_track().physical_plan(duration=0.2)
        first = plan.render(sample_rate=target_rate)
        second = plan.render(sample_rate=target_rate)
        digest = assert_repeatable(first, second, label="generated sample decode/resample")
        render_summaries["sample"] = assert_wav_contract(first, sample_rate=target_rate).to_dict()
        root_removed_after_teardown = generated.root
    if root_removed_after_teardown.exists():
        raise SynthOracleError("generated sample temporary directory leaked after teardown")
    diagnostics = path_diagnostics(
        execution_class,
        (
            "runtime-generated-pcm-wav",
            "canonical-temporary-path",
            "rust-wav-decoder",
            "rust-rate-cache",
            "rust-sample-voice-resampler",
            "wav-memory-sink",
        ),
        work_units=work_units,
        details={
            "fixture_manifest": [entry.name for entry in fixture_manifest()],
            "duration_results": duration_results,
            "signal_oracles": render_summaries,
            "pcm_digest": digest,
            "cache_observation": "same canonical path requested twice; no public hit/miss counter",
            "temporary_files_removed": True,
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "decoded_assets": len(duration_results),
            "source_rate": source_rate,
            "target_rate": target_rate,
            "playback_rate": playback_rate,
            "sample_operations": 20,
            "wav_bytes": len(first),
        },
    )


def _fx_family_case(sample_rate: int) -> tuple[dict[str, object], int]:
    dry_plan = _physical_voice_plan(
        "saw",
        duration=0.07,
        opts={"attack": 0.001, "sustain": 0.025, "release": 0.012, "amp": 0.18},
    )
    dry = dry_plan.render(sample_rate=sample_rate)
    dry_digest = sha256(dry).hexdigest()
    summaries: dict[str, object] = {}
    for fx_name, fx_opts in _FX_OPTIONS.items():
        plan = _physical_voice_plan(
            "saw",
            duration=0.09,
            opts={"attack": 0.001, "sustain": 0.025, "release": 0.012, "amp": 0.18},
            fx_name=fx_name,
            fx_opts={**fx_opts, "mix": 1.0},
        )
        payload = plan.render(sample_rate=sample_rate)
        summary = assert_wav_contract(payload, sample_rate=sample_rate)
        if sha256(payload).hexdigest() == dry_digest:
            raise SynthOracleError(f"FX {fx_name!r} produced an exact dry no-op")
        summaries[fx_name] = {
            "digest": summary.digest,
            "frames": summary.frames,
            "peak": summary.peak,
            "bands": dict(summary.spectral_bands),
        }
    return summaries, len(dry)


def _bus_output_case(sample_rate: int) -> tuple[dict[str, object], int]:
    from gummysnake import synth as sy

    @sy.track(seed=310)
    def shared_bus() -> None:
        with (
            sy.synth("_saw"),
            sy.fx("_compressor", threshold=0.05, slope_above=0.2, mix=1.0) as compressor,
        ):
            sy.play(57, sustain=0.02, release=0.01, amp=0.7)
            sy.control(compressor, threshold=0.08)
            sy.play(64, sustain=0.02, release=0.01, amp=0.7)

    @sy.track(seed=310)
    def unique_buses() -> None:
        with sy.synth("_saw"):
            with sy.fx("_compressor", threshold=0.05, slope_above=0.2, mix=1.0):
                sy.play(57, sustain=0.02, release=0.01, amp=0.7)
            with sy.fx("_compressor", threshold=0.08, slope_above=0.2, mix=1.0):
                sy.play(64, sustain=0.02, release=0.01, amp=0.7)

    shared = shared_bus().render(duration=0.08, sample_rate=sample_rate)
    unique = unique_buses().render(duration=0.08, sample_rate=sample_rate)
    if shared == unique:
        raise SynthOracleError("shared and unique FX bus topologies produced identical PCM")
    loud_track = _voice_track(
        "sine",
        opts={"attack": 0.001, "sustain": 0.03, "release": 0.01, "amp": 8.0},
        fx_name="normaliser",
        fx_opts={"level": 0.8, "mix": 1.0},
    )
    loud = loud_track.render(duration=0.08, sample_rate=sample_rate)
    loud_summary = assert_wav_contract(loud, sample_rate=sample_rate)
    if loud_summary.peak > 0.99:
        raise SynthOracleError("output limiter exceeded its PCM ceiling")
    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-output-") as temporary:
        output = Path(temporary) / "bounded-output.wav"
        saved = loud_track.save(output, duration=0.08, sample_rate=sample_rate)
        file_payload = saved.read_bytes()
        if file_payload != loud:
            raise SynthOracleError("public Track.save WAV bytes differ from in-memory render")
    return (
        {
            "shared": assert_wav_contract(shared, sample_rate=sample_rate).to_dict(),
            "unique": assert_wav_contract(unique, sample_rate=sample_rate).to_dict(),
            "limited_normalised": loud_summary.to_dict(),
            "file_sink_removed": not output.exists(),
        },
        len(loud),
    )


def _fx_mix_output(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    path: tuple[str, ...]
    if case_kind == "all-practical-fx":
        oracles, output_bytes = _fx_family_case(sample_rate)
        path = (
            "public-track-fx-context",
            "serialized-pyo3",
            "rust-fx-family-dispatch",
            "rust-output-limiter",
            "wav-memory-sink",
        )
        summary = {"fx_operations": len(oracles), "wav_bytes": output_bytes}
    elif case_kind == "buses-output-normalization":
        oracles, output_bytes = _bus_output_case(sample_rate)
        path = (
            "public-track-fx-handles",
            "rust-shared-bus-tree",
            "normaliser-and-output-limiter",
            "wav-bytes-and-file-sinks",
        )
        summary = {"bus_topologies": 2, "output_bytes": output_bytes}
    else:
        raise SynthWorkloadError(f"unknown FX/output case_kind: {case_kind!r}")
    diagnostics = path_diagnostics(
        execution_class,
        path,
        work_units=work_units,
        details={
            "oracles": oracles,
            "fx_names": list(_FX_OPTIONS) if case_kind == "all-practical-fx" else [],
            "normaliser_contract": (
                "current whole-signal normaliser; causal streaming normaliser not exposed"
            ),
        },
    )
    return SuiteExecution(diagnostics, summary)


def _simulated_sink(payload: bytes, block_frames: int) -> Mapping[str, object]:
    pcm = pcm_data(payload)
    bytes_per_frame = 4
    block_bytes = block_frames * bytes_per_frame
    blocks = [pcm[offset : offset + block_bytes] for offset in range(0, len(pcm), block_bytes)]
    if b"".join(blocks) != pcm:
        raise SynthOracleError("simulated realtime block partition changed PCM bytes")
    queue = 0
    low_water = 1 << 30
    high_water = 0
    for block in blocks:
        queue += len(block) // bytes_per_frame
        high_water = max(high_water, queue)
        queue -= len(block) // bytes_per_frame
        low_water = min(low_water, queue)
    return {
        "blocks": len(blocks),
        "block_frames": block_frames,
        "queue_low_frames": 0 if low_water == 1 << 30 else low_water,
        "queue_high_frames": high_water,
        "underruns": 0,
        "deadline_clock": "deterministic-virtual-clock-no-sleep",
        "partition_digest": "sha256:" + sha256(pcm).hexdigest(),
    }


def _streaming_sound(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    duration_ms = _integer(parameters, "duration_ms", minimum=20, maximum=300_000)
    block_frames = _integer(parameters, "block_frames", minimum=16, maximum=16_384)
    duration = duration_ms / 1000.0
    track = _voice_track(
        "sine",
        opts={
            "attack": 0.005,
            "sustain": max(0.005, duration - 0.015),
            "release": 0.01,
            "amp": 0.3,
        },
        fx_name="echo",
        fx_opts={"phase": 0.01, "decay": 0.03, "max_phase": 0.05, "mix": 0.3},
    )
    if case_kind == "simulated-realtime-block-sink":
        require_route(execution_class, simulated=True)
        payload = track.render(duration=duration, sample_rate=sample_rate)
        signal = assert_wav_contract(payload, sample_rate=sample_rate)
        sink = _simulated_sink(payload, block_frames)
        diagnostics = path_diagnostics(
            execution_class,
            (
                "bounded-offline-rust-render",
                "exact-pcm-block-adapter",
                "deterministic-simulated-realtime-sink",
            ),
            work_units=work_units,
            details={
                "sink": dict(sink),
                "signal": signal.to_dict(),
                "not_measured": [
                    "device-open",
                    "queue-submission",
                    "audible-latency",
                    "dac-latency",
                ],
            },
        )
        return SuiteExecution(
            diagnostics,
            {"frames": signal.frames, "blocks": sink["blocks"], "wav_bytes": len(payload)},
        )
    require_route(execution_class)
    if case_kind != "public-sound-headless-state":
        raise SynthWorkloadError(f"unknown streaming/sound case_kind: {case_kind!r}")
    sound = track.to_sound("benchmark-generated.wav", duration=duration, sample_rate=sample_rate)
    encoded = sound.to_bytes()
    signal = assert_wav_contract(encoded, sample_rate=sample_rate)
    sound.volume(0.4)
    sound.rate(1.25)
    sound.pan(-0.3)
    sound.looping(True)
    sound.no_loop()
    sound.seek(min(duration / 2.0, 0.02))
    callback = sound.on_ended(lambda _: None)
    state = {
        "path": str(sound.path),
        "duration": sound.duration,
        "byte_len": sound.byte_len,
        "volume": sound.volume(),
        "rate": sound.rate(),
        "pan": sound.pan(),
        "looping": sound.looping(),
        "time": sound.time(),
        "playing": sound.is_playing(),
        "paused": sound.is_paused(),
        "callback_registered": callable(callback),
    }
    if state["playing"] or state["paused"] or state["looping"]:
        raise SynthOracleError(f"headless Sound state is inconsistent: {state}")
    sound.pause()
    sound.stop()
    sound.close()
    diagnostics = path_diagnostics(
        execution_class,
        ("track-to-sound", "memory-sound-source", "public-sound-headless-state", "explicit-bytes"),
        work_units=work_units,
        details={
            "state": state,
            "signal": signal.to_dict(),
            "playback_methods_exercised": False,
            "reason": "physical playback is not safe or qualified in a headless catalog case",
        },
    )
    return SuiteExecution(
        diagnostics,
        {"sound_state_operations": 14, "wav_bytes": len(encoded), "frames": signal.frames},
    )


def _failure_case(sample_rate: int) -> tuple[Sequence[str], int]:
    from gummysnake import synth as sy

    plan = _bridge_plan(2)
    serialized = plan.to_bytes()
    failures = [
        assert_expected_failure(
            lambda: sy.PhysicalPlan.from_bytes(b"short"), tokens=("short", "serialized")
        ),
        assert_expected_failure(
            lambda: sy.PhysicalPlan.from_bytes(b"BROKEN!!" + serialized[8:]),
            tokens=("header", "invalid"),
        ),
        assert_expected_failure(
            lambda: _runtime().synth_render_plan_wav([], -1.0, sample_rate),
            tokens=("negative", "duration"),
        ),
    ]

    @sy.track(seed=310)
    def missing_sample() -> None:
        sy.sample("benchmark-file-that-does-not-exist.wav")

    failures.append(
        assert_expected_failure(
            lambda: missing_sample().render(duration=0.02, sample_rate=sample_rate),
            tokens=("not found", "sample"),
        )
    )

    base_event: dict[str, object] = {
        "node_id": 1,
        "seed": 310,
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
    failures.extend(
        (
            assert_expected_failure(
                lambda: _runtime().synth_render_event_wav(
                    {**base_event, "synth_name": "_unknown"}, sample_rate
                ),
                tokens=("unsupported", "primitive"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_event_wav(
                    {
                        **base_event,
                        "fx_chain": [{"id": 1, "name": "unknown", "opts": {}}],
                    },
                    sample_rate,
                ),
                tokens=("dry-pass", "unsupported"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_event_wav(
                    {
                        **base_event,
                        "fx_chain": [
                            {
                                "id": 1,
                                "name": "_chain",
                                "opts": {"ops": [{"op": "unknown"}]},
                            }
                        ],
                    },
                    sample_rate,
                ),
                tokens=("chain operation", "unsupported"),
            ),
            assert_expected_failure(
                lambda: replace(
                    plan,
                    events=(replace(plan.events[0], value=object()), *plan.events[1:]),
                ).to_bytes(),
                tokens=("synth values", "serialized"),
            ),
            assert_expected_failure(
                lambda: replace(
                    plan,
                    events=(replace(plan.events[0], opts={1: "collision"}), *plan.events[1:]),
                ).to_bytes(),
                tokens=("keys must be strings", "not coerced"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_plan_wav([], float("nan"), sample_rate),
                tokens=("finite", "duration"),
            ),
        )
    )
    from gummysnake.synth.synth_runtime.values import foundation as synth_foundation

    declared_bomb = synth_foundation._GSS_HEADER.pack(
        synth_foundation._GSS_MAGIC,
        synth_foundation._GSS_COMPRESSION,
        synth_foundation._MAX_DECOMPRESSED_PLAN_BYTES + 1,
    )
    failures.append(
        assert_expected_failure(
            lambda: sy.PhysicalPlan.from_bytes(declared_bomb),
            tokens=("decompressed payload", "limit"),
        )
    )

    @sy.track
    def unsupported_sample_filter() -> None:
        sy.sample("loop_amen", "unknown_filter")

    failures.append(
        assert_expected_failure(
            unsupported_sample_filter,
            tokens=("sample filters", "not supported"),
        )
    )

    sound = _voice_track("sine", opts={"release": 0.01}).to_sound(
        duration=0.02, sample_rate=sample_rate
    )
    failures.extend(
        (
            assert_expected_failure(lambda: sound.volume(-1.0), tokens=("negative", "volume")),
            assert_expected_failure(lambda: sound.rate(0.0), tokens=("positive", "rate")),
            assert_expected_failure(lambda: sound.pan(2.0), tokens=("between", "pan")),
            assert_expected_failure(lambda: sound.seek(-1.0), tokens=("negative", "seek")),
        )
    )
    sound.close()
    return failures, len(serialized)


def _longevity_case(sample_rate: int, cycles: int) -> tuple[dict[str, object], int]:
    plan_digests: set[str] = set()
    pcm_digests: set[str] = set()
    total_bytes = 0
    for _ in range(cycles):
        plan = _physical_voice_plan(
            "sine",
            duration=0.04,
            opts={"attack": 0.001, "sustain": 0.015, "release": 0.008, "amp": 0.2},
            fx_name="lpf",
            fx_opts={"cutoff": 90, "mix": 0.7},
        )
        plan_digests.add(semantic_plan_digest(plan.to_dict()))
        payload = plan.render(sample_rate=sample_rate)
        assert_wav_contract(payload, sample_rate=sample_rate)
        pcm_digests.add("sha256:" + sha256(payload).hexdigest())
        total_bytes += len(payload) + len(plan.to_bytes())
    if len(plan_digests) != 1 or len(pcm_digests) != 1:
        raise SynthOracleError(
            "bounded longevity cycles changed deterministic plan or PCM identity"
        )
    return (
        {
            "cycles": cycles,
            "plan_digest": next(iter(plan_digests)),
            "pcm_digest": next(iter(pcm_digests)),
            "total_materialized_bytes": total_bytes,
            "resource_boundary": "fresh Python plan and returned WAV per cycle; gc owned by worker",
        },
        total_bytes,
    )


def _failures_longevity(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    cycles = _integer(parameters, "cycles", minimum=1, maximum=1_000)
    path: tuple[str, ...]
    if case_kind == "fail-closed-validation":
        failures, materialized = _failure_case(sample_rate)
        details: Mapping[str, object] = {
            "failures": list(failures),
            "closed_defect_classes": [
                "unknown primitive synth rejection",
                "unknown FX and chain-operation rejection",
                "unsupported value and non-string key rejection",
                "non-finite duration rejection",
                "declared decompressed-size limit rejection",
                "unsupported positional sample-filter rejection",
            ],
            "remaining_unenforced_defects": [
                "option-name/type validation is not yet exhaustive for every documented "
                "DSP operation",
                "decoded sample-file resource budgets are not yet comprehensive",
            ],
        }
        summary = {"expected_failures": len(failures), "materialized_bytes": materialized}
        path = ("python-validation", "pyo3-validation", "rust-errors", "no-alternate-engine")
    elif case_kind == "bounded-longevity":
        longevity, materialized = _longevity_case(sample_rate, cycles)
        details = longevity
        summary = {"cycles": cycles, "materialized_bytes": materialized}
        path = (
            "repeated-composition",
            "serialization",
            "rust-dsp-and-fx",
            "wav-memory-output",
            "worker-gc-boundary",
        )
    else:
        raise SynthWorkloadError(f"unknown failure/longevity case_kind: {case_kind!r}")
    diagnostics = path_diagnostics(execution_class, path, work_units=work_units, details=details)
    return SuiteExecution(diagnostics, summary)


_DISPATCHERS: Mapping[
    str,
    Callable[[str, Mapping[str, object], ExecutionClass, int], SuiteExecution],
] = {
    "composition": _composition,
    "serialization-bridge": _serialization_bridge,
    "voices-filters-automation": _voices_filters_automation,
    "sample-engine": _sample_engine,
    "fx-mix-output": _fx_mix_output,
    "streaming-sound": _streaming_sound,
    "failures-longevity": _failures_longevity,
}


def dispatch(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
) -> SuiteExecution:
    """Execute one cataloged bounded Synth case and return the shared suite contract."""

    case_kind, work_units = _validate_parameters(workload_id, parameters)
    try:
        dispatcher = _DISPATCHERS[workload_id]
    except KeyError as error:
        raise SynthWorkloadError(f"unknown Synth workload id: {workload_id!r}") from error
    result = dispatcher(case_kind, parameters, execution_class, work_units)
    if result.diagnostics.get("work_units") != work_units:
        raise SynthWorkloadError("Synth dispatcher diagnostics lost declared work-unit accounting")
    required_counters = parameters.get("required_counters", ())
    if not isinstance(required_counters, list) or not all(
        isinstance(counter, str) and counter for counter in required_counters
    ):
        raise SynthWorkloadError("required_counters must be a list of public counter names")
    missing = [counter for counter in required_counters if counter not in result.diagnostics]
    if missing:
        raise SynthWorkloadError(
            f"Synth workload omitted required diagnostic counter(s): {', '.join(missing)}"
        )
    return result


__all__ = ["SynthWorkloadError", "dispatch"]
