"""Bounded production-path workloads for the replacement Synth benchmark suite."""

from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, sleep
from typing import Any

from benchmarks.governance import ExecutionClass
from benchmarks.suites.registry import SuiteExecution

from .adapters import (
    CallableSynthAdapter,
    merge_lifecycle_diagnostics,
    physical_sdl_adapter,
    run_adapter,
    simulated_realtime_adapter,
)
from .diagnostics import path_diagnostics, require_route
from .fixtures import (
    fixture_manifest,
    generate_signal,
    generated_sample_files,
    packaged_sample_catalog,
    pcm_variant_catalog,
    pcm_wav_bytes,
    validate_manifest,
    validate_packaged_sample_catalog,
    validate_pcm_variant_manifest,
)
from .oracles import (
    SynthOracleError,
    assert_envelope_shape,
    assert_expected_failure,
    assert_frequency,
    assert_repeatable,
    assert_wav_contract,
    semantic_plan_digest,
)


class SynthWorkloadError(ValueError):
    """A static Synth workload declaration is unknown, unsafe, or internally inconsistent."""


def _availability(
    value: int | float | str | None,
    *,
    source: str | None,
    reason: str | None = None,
) -> dict[str, object]:
    """Represent a truthful metric without converting an unavailable probe to zero."""

    return {
        "available": reason is None,
        "value": value if reason is None else None,
        "source": source if reason is None else None,
        "reason": reason,
    }


def _allocated_blocks() -> int | None:
    probe = getattr(sys, "getallocatedblocks", None)
    if not callable(probe):
        return None
    value = probe()
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _measure_python_phase[ResultT](
    action: Callable[[], ResultT],
) -> tuple[ResultT, dict[str, object]]:
    """Measure elapsed time and the truthful net CPython allocation-block delta."""

    blocks_before = _allocated_blocks()
    started_ns = perf_counter_ns()
    result = action()
    elapsed_ns = perf_counter_ns() - started_ns
    blocks_after = _allocated_blocks()
    allocation_delta = (
        _availability(
            blocks_after - blocks_before,
            source="sys.getallocatedblocks-phase-boundary-net-delta",
        )
        if blocks_before is not None and blocks_after is not None
        else _availability(
            None,
            source=None,
            reason="sys.getallocatedblocks is unavailable on this Python implementation",
        )
    )
    return result, {
        "elapsed_ns": elapsed_ns,
        "python_allocated_blocks_net_delta": allocation_delta,
    }


def _metric_int(payload: Mapping[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SynthWorkloadError(f"metric {name!r} must be an integer")
    return value


def _metric_list(payload: Mapping[str, object], name: str) -> list[object]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise SynthWorkloadError(f"metric {name!r} must be a list")
    return value


def _elapsed_ns(measurement: Mapping[str, object]) -> int:
    value = measurement.get("elapsed_ns")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SynthWorkloadError("phase measurement omitted a non-negative elapsed_ns")
    return value


def _positive_int_list(
    parameters: Mapping[str, object],
    name: str,
    *,
    maximum: int,
) -> tuple[int, ...]:
    value = parameters.get(name)
    if not isinstance(value, list) or not value:
        raise SynthWorkloadError(f"{name} must be a non-empty list of positive integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= maximum:
            raise SynthWorkloadError(f"{name} values must be integers in [1, {maximum}]")
        result.append(item)
    if result != sorted(set(result)):
        raise SynthWorkloadError(f"{name} must be strictly increasing without duplicates")
    return tuple(result)


def _non_negative_int_list(
    parameters: Mapping[str, object],
    name: str,
    *,
    maximum: int,
) -> tuple[int, ...]:
    value = parameters.get(name)
    if not isinstance(value, list) or not value:
        raise SynthWorkloadError(f"{name} must be a non-empty list of non-negative integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= maximum:
            raise SynthWorkloadError(f"{name} values must be integers in [0, {maximum}]")
        result.append(item)
    if result != sorted(set(result)):
        raise SynthWorkloadError(f"{name} must be strictly increasing without duplicates")
    return tuple(result)


def _integer_list(
    parameters: Mapping[str, object],
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> tuple[int, ...]:
    value = parameters.get(name)
    if not isinstance(value, list) or not value:
        raise SynthWorkloadError(f"{name} must be a non-empty list of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise SynthWorkloadError(f"{name} values must be integers in [{minimum}, {maximum}]")
        result.append(item)
    if len(result) != len(set(result)):
        raise SynthWorkloadError(f"{name} must not contain duplicates")
    return tuple(result)


def _number_list(
    parameters: Mapping[str, object],
    name: str,
    *,
    minimum: float,
    maximum: float,
    allow_zero: bool = True,
) -> tuple[float, ...]:
    value = parameters.get(name)
    if not isinstance(value, list) or not value:
        raise SynthWorkloadError(f"{name} must be a non-empty numeric list")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float | str):
            raise SynthWorkloadError(f"{name} values must be numeric")
        try:
            number = float(item)
        except ValueError as error:
            raise SynthWorkloadError(f"{name} values must be numeric") from error
        if not math.isfinite(number) or not minimum <= number <= maximum:
            raise SynthWorkloadError(f"{name} values must be in [{minimum}, {maximum}]")
        if not allow_zero and number == 0.0:
            raise SynthWorkloadError(f"{name} values cannot be zero")
        result.append(number)
    if len(result) != len(set(result)):
        raise SynthWorkloadError(f"{name} must not contain duplicates")
    return tuple(result)


def _complexity_slope(points: Sequence[tuple[int, int]]) -> dict[str, object]:
    """Return an endpoint log/log slope, or explicit unavailability for unusable samples."""

    if len(points) < 2:
        return _availability(None, source=None, reason="at least two scale points are required")
    first_size, first_value = points[0]
    last_size, last_value = points[-1]
    if first_size <= 0 or last_size <= first_size or first_value <= 0 or last_value <= 0:
        return _availability(
            None, source=None, reason="slope inputs must be positive and increasing"
        )
    return _availability(
        math.log(last_value / first_value) / math.log(last_size / first_size),
        source="endpoint-log-log-slope",
    )


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
        {
            "case_kind",
            "event_count",
            "event_counts",
            "depth",
            "depths",
            "graph_sizes",
            "control_counts",
            "work_units",
            "required_counters",
        }
    ),
    "serialization-bridge": frozenset(
        {
            "case_kind",
            "event_count",
            "event_counts",
            "control_counts",
            "value_depths",
            "layer_counts",
            "fx_depths",
            "sample_path_counts",
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
            "sample_rates",
            "polyphony",
            "polyphonies",
            "layer_count",
            "layer_counts",
            "envelope_curves",
            "automation_counts",
            "work_units",
            "required_counters",
        }
    ),
    "sample-engine": frozenset(
        {
            "case_kind",
            "source_rate",
            "source_rates",
            "target_rate",
            "target_rates",
            "playback_rate",
            "playback_rates",
            "work_units",
            "required_counters",
        }
    ),
    "fx-mix-output": frozenset(
        {
            "case_kind",
            "sample_rate",
            "chain_depths",
            "bus_counts",
            "duration_seconds",
            "work_units",
            "required_counters",
        }
    ),
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
        if case_kind == "flat-scale-sweep":
            return sum(_positive_int_list(parameters, "event_counts", maximum=65_536))
        if case_kind == "nested-depth-sweep":
            depths = _positive_int_list(parameters, "depths", maximum=8)
            return 2 * sum(2 ** (depth + 1) for depth in depths)
        if case_kind == "lazy-expression-sweep":
            return sum(_positive_int_list(parameters, "graph_sizes", maximum=4_096))
        if case_kind == "template-cold-warm":
            return _integer(parameters, "event_count", maximum=4_096) + 8
        if case_kind == "schedule-control-sweep":
            event_counts = _positive_int_list(parameters, "event_counts", maximum=16_384)
            control_counts = _non_negative_int_list(parameters, "control_counts", maximum=16_384)
            return sum(event_counts) * 4 + sum(control_counts) + len(control_counts)
        if case_kind == "fresh-process-determinism":
            return 4
        event_count = _integer(parameters, "event_count", maximum=65_536)
        if case_kind == "nested-expressions":
            depth = _integer(parameters, "depth", minimum=1, maximum=8)
            expanded_events = 2 ** (depth + 1)
            if event_count != expanded_events:
                raise SynthWorkloadError(
                    "nested-expressions event_count must equal its two-branch expanded event count"
                )
        return event_count
    if workload_id == "serialization-bridge":
        if case_kind == "phase-shape-sweep":
            return (
                sum(_positive_int_list(parameters, "event_counts", maximum=16_384))
                + sum(_non_negative_int_list(parameters, "control_counts", maximum=16_384))
                + sum(_positive_int_list(parameters, "value_depths", maximum=32))
                + sum(_positive_int_list(parameters, "layer_counts", maximum=16))
                + sum(_non_negative_int_list(parameters, "fx_depths", maximum=64))
                + sum(_positive_int_list(parameters, "sample_path_counts", maximum=64))
            )
        if case_kind == "hostile-inputs":
            return 24
        if case_kind in {"roundtrip", "direct-serialized-parity", "gil-heartbeat"}:
            return _integer(parameters, "event_count", maximum=16_384)
    if workload_id == "voices-filters-automation":
        if case_kind == "voice-rate-polyphony-matrix":
            return (
                len(_OSCILLATORS)
                * len(_positive_int_list(parameters, "sample_rates", maximum=96_000))
                * len(_positive_int_list(parameters, "polyphonies", maximum=12))
            )
        if case_kind == "layer-envelope-filter-automation-matrix":
            rates = _positive_int_list(parameters, "sample_rates", maximum=96_000)
            polyphonies = _positive_int_list(parameters, "polyphonies", maximum=12)
            layers = _positive_int_list(parameters, "layer_counts", maximum=16)
            curves = _integer_list(parameters, "envelope_curves", minimum=-10, maximum=10)
            automation_counts = _non_negative_int_list(parameters, "automation_counts", maximum=64)
            return len(rates) * (
                len(polyphonies) * len(layers) + len(curves) * 2 + 6 + len(automation_counts)
            )
        if case_kind == "oscillator-polyphony":
            return len(_OSCILLATORS)
        if case_kind == "layers-envelopes-filters-automation":
            return _integer(parameters, "polyphony", maximum=12) * _integer(
                parameters, "layer_count", maximum=16
            )
    if workload_id == "sample-engine":
        if case_kind == "decode-metadata-matrix":
            return len(pcm_variant_catalog()) * 2 + len(packaged_sample_catalog()) * 2
        if case_kind == "resample-slice-playback-rate-matrix":
            return (
                len(_positive_int_list(parameters, "source_rates", maximum=96_000))
                * len(_positive_int_list(parameters, "target_rates", maximum=96_000))
                * len(
                    _number_list(
                        parameters,
                        "playback_rates",
                        minimum=-8.0,
                        maximum=8.0,
                        allow_zero=False,
                    )
                )
            )
        if case_kind == "generated-wav-decode-resample-cache":
            return 20  # Six generated + three FLAC cold/warm probes, then two sample renders.
    if workload_id == "fx-mix-output":
        if case_kind == "all-practical-fx":
            return len(_FX_OPTIONS)
        if case_kind == "buses-output-normalization":
            return 4
        if case_kind == "chain-bus-scaling-matrix":
            return sum(_positive_int_list(parameters, "chain_depths", maximum=8)) + sum(
                _positive_int_list(parameters, "bus_counts", maximum=32)
            )
        if case_kind == "stateful-memory-file-output-scales":
            return 2 * sum(_positive_int_list(parameters, "duration_seconds", maximum=60))
    if workload_id == "streaming-sound":
        if case_kind == "public-sound-headless-state":
            return 14
        if case_kind == "stateful-block-memory-file-parity":
            return 2
        if case_kind == "stateful-route-guards":
            return 3
        if case_kind == "simulated-realtime-block-sink":
            sample_rate = _integer(parameters, "sample_rate", maximum=96_000)
            duration_ms = _integer(parameters, "duration_ms", maximum=300_000)
            block_frames = _integer(parameters, "block_frames", maximum=16_384)
            frames = (sample_rate * duration_ms + 999) // 1_000
            return (frames + block_frames - 1) // block_frames
    if workload_id == "failures-longevity":
        if case_kind == "fail-closed-validation":
            return 21
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


def _composition_scale_sweep(
    event_counts: Sequence[int], execution_class: ExecutionClass, work_units: int
) -> SuiteExecution:
    from gummysnake import synth as sy

    points: list[dict[str, object]] = []
    for event_count in event_counts:

        @sy.track(seed=310)
        def flat_scale_track(event_count: int = event_count) -> None:
            for index in range(event_count):
                sy.play(48 + index % 24, amp=0.2, release=0.001)
                sy.sleep(0.0001)

        track, declaration = _measure_python_phase(flat_scale_track)
        plan, expansion = _measure_python_phase(
            lambda track=track, event_count=event_count: track.physical_plan(
                duration=max(0.01, event_count * 0.0002)
            )
        )
        plan_dict, normalization = _measure_python_phase(plan.to_dict)
        serialized, serialization = _measure_python_phase(plan.to_bytes)
        if len(plan.events) != event_count:
            raise SynthOracleError(
                f"flat composition scale {event_count} expanded {len(plan.events)} events"
            )
        points.append(
            {
                "declared_events": event_count,
                "expanded_events": len(plan.events),
                "logical_nodes": len(track.logical_plan.nodes),
                "logical_plan_shallow_bytes": sys.getsizeof(track.logical_plan)
                + sys.getsizeof(track.logical_plan.nodes)
                + sum(sys.getsizeof(node) for node in track.logical_plan.nodes),
                "normalized_top_level_keys": len(plan_dict),
                "serialized_bytes": len(serialized),
                "plan_digest": semantic_plan_digest(plan_dict),
                "declaration": declaration,
                "expansion_and_production_sort": expansion,
                "normalization": normalization,
                "serialization": serialization,
                "production_sort_ns": _availability(
                    None,
                    source=None,
                    reason="physical_plan() does not expose production sort as a separate phase",
                ),
            }
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-public-track-api",
            "flat-logical-declaration-scale-sweep",
            "physical-expansion-and-sort",
            "normalization-and-serialization",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "scale_points": points,
            "complexity_slopes": {
                "declaration_time": _complexity_slope(
                    [
                        (_metric_int(point, "declared_events"), _elapsed_ns(phase))
                        for point in points
                        if isinstance((phase := point["declaration"]), Mapping)
                    ]
                ),
                "expansion_time": _complexity_slope(
                    [
                        (_metric_int(point, "declared_events"), _elapsed_ns(phase))
                        for point in points
                        if isinstance((phase := point["expansion_and_production_sort"]), Mapping)
                    ]
                ),
                "serialized_bytes": _complexity_slope(
                    [
                        (
                            _metric_int(point, "declared_events"),
                            _metric_int(point, "serialized_bytes"),
                        )
                        for point in points
                    ]
                ),
            },
            "allocation_semantics": (
                "net CPython allocated-block deltas at phase boundaries; not allocation counts"
            ),
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "scale_count": len(points),
            "minimum_events": event_counts[0],
            "maximum_events": event_counts[-1],
            "declared_event_work": sum(event_counts),
            "rendered_audio": False,
        },
    )


def _nested_depth_sweep(
    depths: Sequence[int], execution_class: ExecutionClass, work_units: int
) -> SuiteExecution:
    from gummysnake import synth as sy

    points: list[dict[str, object]] = []
    for depth in depths:

        @sy.track
        def leaf(note: object = 60) -> None:
            sy.play(note, amp=0.2, release=0.001)
            sy.sleep(1.0)

        def nested(level: int) -> None:
            if level == 0:
                leaf(60)
                return
            with sy.loop(times=2):
                nested(level - 1)

        @sy.track(seed=310)
        def nested_track(depth: int = depth) -> None:
            with sy.thread(name="depth-sweep-branch"):
                nested(depth)
            nested(depth)

        expanded_count = 2 ** (depth + 1)

        @sy.track(seed=310)
        def directly_expanded_track(expanded_count: int = expanded_count) -> None:
            with sy.thread(name="direct-depth-sweep-branch"):
                for _ in range(expanded_count // 2):
                    sy.play(60, amp=0.2, release=0.001)
                    sy.sleep(1.0)
            for _ in range(expanded_count // 2):
                sy.play(60, amp=0.2, release=0.001)
                sy.sleep(1.0)

        nested_logical, nested_declaration = _measure_python_phase(nested_track)
        direct_logical, direct_declaration = _measure_python_phase(directly_expanded_track)
        duration = float(expanded_count)
        nested_plan, nested_expansion = _measure_python_phase(
            lambda nested_logical=nested_logical, duration=duration: nested_logical.physical_plan(
                duration=duration
            )
        )
        direct_plan, direct_expansion = _measure_python_phase(
            lambda direct_logical=direct_logical, duration=duration: direct_logical.physical_plan(
                duration=duration
            )
        )
        nested_schedule = [
            (event.time_seconds, event.value, dict(event.opts)) for event in nested_plan.events
        ]
        direct_schedule = [
            (event.time_seconds, event.value, dict(event.opts)) for event in direct_plan.events
        ]
        if nested_schedule != direct_schedule or len(nested_schedule) != expanded_count:
            raise SynthOracleError(
                f"nested depth {depth} differs from its directly expanded schedule"
            )
        points.append(
            {
                "depth": depth,
                "events_per_variant": expanded_count,
                "nested_logical_nodes": len(nested_logical.logical_plan.nodes),
                "direct_logical_nodes": len(direct_logical.logical_plan.nodes),
                "nested_declaration": nested_declaration,
                "direct_declaration": direct_declaration,
                "nested_expansion_and_sort": nested_expansion,
                "direct_expansion_and_sort": direct_expansion,
                "nested_plan_bytes": len(nested_plan.to_bytes()),
                "direct_plan_bytes": len(direct_plan.to_bytes()),
                "nested_digest": semantic_plan_digest(nested_plan.to_dict()),
                "direct_digest": semantic_plan_digest(direct_plan.to_dict()),
                "schedule_equivalent": True,
            }
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-loop-thread-track-call-nesting",
            "direct-expanded-reference",
            "physical-expansion-and-sort",
            "exact-schedule-comparison",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "depth_points": points,
            "production_sort_ns": _availability(
                None,
                source=None,
                reason="production expansion and sort are one public physical_plan() phase",
            ),
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "minimum_depth": depths[0],
            "maximum_depth": depths[-1],
            "variant_event_work": work_units,
            "schedule_equivalent": True,
        },
    )


def _lazy_expression_sweep(
    graph_sizes: Sequence[int], execution_class: ExecutionClass, work_units: int
) -> SuiteExecution:
    from gummysnake import synth as sy

    sample_path = validate_packaged_sample_catalog()["reviewed-minimal-flac"]
    points: list[dict[str, object]] = []
    family_names = (
        "arithmetic",
        "seeded-random",
        "choice-ring",
        "tick-look",
        "music",
        "conditions",
        "lazy-sleep-duration",
        "nested-containers",
        "track-call-binding-reuse",
    )
    for graph_size in graph_sizes:

        @sy.track
        def bound_pair(value: object, release: object) -> None:
            sy.play(value, release=release, amp=0.1)
            sy.play(value, release=release, amp=0.1)

        @sy.track(seed=310)
        def lazy_graph(graph_size: int = graph_size) -> None:
            notes = sy.ring(60, 62, 64, 67)
            duration = sy.sample_duration(sample_path) / 100.0
            for _ in range(graph_size):
                ticked = notes.tick("lazy-family")
                looked = notes.look("lazy-family")
                root = sy.choose(["c4", "e4"])
                chord_value = sy.choose(sy.chord(root, "minor"))
                random_offset = sy.rrand_i(0, 2) + sy.dice(2) - 1
                value = chord_value + ticked % 2 + random_offset
                condition = (looked >= 60) != sy.one_in(5)
                bound_pair(value, duration)
                sy.play(
                    sy.choose(sy.scale(root, "major_pentatonic", num_octaves=1)),
                    amp=sy.rand(0.25),
                    release=duration,
                    metadata={"nested": [{"look": looked, "choice": chord_value}]},
                ).when(condition)
                sy.sleep(sy.choose([0.0001, 0.0002]))

        track, declaration = _measure_python_phase(lazy_graph)
        plan, expansion = _measure_python_phase(
            lambda track=track, graph_size=graph_size: track.physical_plan(
                duration=max(0.02, graph_size * 0.001)
            )
        )
        repeated = lazy_graph().physical_plan(duration=max(0.02, graph_size * 0.001))
        digest = semantic_plan_digest(plan.to_dict())
        if semantic_plan_digest(repeated.to_dict()) != digest:
            raise SynthOracleError(
                f"lazy expression graph size {graph_size} was not deterministic for seed 310"
            )
        points.append(
            {
                "graph_size": graph_size,
                "logical_nodes": len(track.logical_plan.nodes),
                "events": len(plan.events),
                "controls": len(plan.controls),
                "declaration": declaration,
                "expansion_and_sort": expansion,
                "serialized_bytes": len(plan.to_bytes()),
                "plan_digest": digest,
            }
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-lazy-expression-families",
            "track-call-binding",
            "deterministic-physical-expansion",
            "semantic-digest",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "expression_families": list(family_names),
            "graph_points": points,
            "sample_duration_path": str(sample_path),
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "family_count": len(family_names),
            "minimum_graph_size": graph_sizes[0],
            "maximum_graph_size": graph_sizes[-1],
            "graph_work_units": sum(graph_sizes),
        },
    )


def _template_cold_warm(
    event_count: int, execution_class: ExecutionClass, work_units: int
) -> SuiteExecution:
    from gummysnake import synth as sy

    @sy.synth(name="benchmark-multi-output-template")
    def multi_output(note: object = 60, **opts: object) -> None:
        first = sy.synth_input(note, defaults={"release": 0.01}, **opts).layer("sine", amp=0.5)
        second = sy.synth_input(note, defaults={"release": 0.01}, **opts).layer(
            "saw", transpose=12, amp=0.2
        )
        first.output()
        second.output()

    @sy.fx(name="benchmark-active-fx-template")
    def active_fx(**opts: object) -> None:
        signal = sy.fx_input().filter(kind="low", cutoff=95).pan(pan=-0.15)
        sy.fx_output(signal, **opts)

    def build_source_track() -> Any:
        @sy.track(seed=310)
        def source_templates() -> None:
            with (
                sy.synth("benchmark-multi-output-template", release=0.02),
                sy.fx("benchmark-active-fx-template", cutoff=84, mix=0.7) as active,
            ):
                for index in range(event_count):
                    sy.play(60 + index % 7, amp=0.2)
                    if index in {event_count // 3, event_count * 2 // 3}:
                        sy.control(active, cutoff=72 + index % 20)
                    sy.sleep(0.0005)

        return source_templates()

    cold_track, source_cold = _measure_python_phase(build_source_track)
    cold_plan, source_expand_cold = _measure_python_phase(
        lambda: cold_track.physical_plan(duration=max(0.02, event_count * 0.001))
    )
    warm_track, source_warm = _measure_python_phase(build_source_track)
    warm_plan, source_expand_warm = _measure_python_phase(
        lambda: warm_track.physical_plan(duration=max(0.02, event_count * 0.001))
    )
    if semantic_plan_digest(cold_plan.to_dict()) != semantic_plan_digest(warm_plan.to_dict()):
        raise SynthOracleError("source synth/FX template expansion changed on immediate reuse")

    compiled_assets: list[dict[str, object]] = []
    for kind, name, path_fn, load_fn in (
        ("synth", "beep", sy.builtin_synth_path, sy.load_builtin_synth_plan),
        ("synth", "prophet", sy.builtin_synth_path, sy.load_builtin_synth_plan),
        ("fx", "lpf", sy.builtin_fx_path, sy.load_builtin_fx_plan),
        ("fx", "reverb", sy.builtin_fx_path, sy.load_builtin_fx_plan),
    ):
        path = path_fn(name)
        first_plan, first_load = _measure_python_phase(
            lambda name=name, load_fn=load_fn: load_fn(name)
        )
        second_plan, immediate_reload = _measure_python_phase(
            lambda name=name, load_fn=load_fn: load_fn(name)
        )
        if semantic_plan_digest(first_plan.to_dict()) != semantic_plan_digest(
            second_plan.to_dict()
        ):
            raise SynthOracleError(f"compiled {kind} template {name!r} changed on reload")
        compiled_assets.append(
            {
                "kind": kind,
                "name": name,
                "path": str(path),
                "file_bytes": path.stat().st_size,
                "first_file_decompress_load": first_load,
                "immediate_warm_os_reload": immediate_reload,
                "cache_semantics": (
                    "first call versus immediate reload; OS page-cache state is not controlled"
                ),
            }
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "source-synth-and-fx-definition",
            "multiple-output-and-active-fx-control-expansion",
            "compiled-template-file-load-and-decompress",
            "warm-reuse-digest",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "source_template": {
                "cold_declaration": source_cold,
                "cold_expansion": source_expand_cold,
                "warm_declaration": source_warm,
                "warm_expansion": source_expand_warm,
                "events": len(cold_plan.events),
                "controls": len(cold_plan.controls),
                "digest": semantic_plan_digest(cold_plan.to_dict()),
                "override_remapping_exercised": True,
                "multiple_outputs_exercised": True,
                "active_fx_handle_exercised": True,
            },
            "compiled_assets": compiled_assets,
            "template_cache_metrics": _availability(
                None,
                source=None,
                reason="public template loaders expose no cache hit/miss/byte counters",
            ),
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "source_events": len(cold_plan.events),
            "source_controls": len(cold_plan.controls),
            "compiled_template_loads": 8,
            "event_count": event_count,
        },
    )


def _schedule_control_sweep(
    event_counts: Sequence[int],
    control_counts: Sequence[int],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    from gummysnake import synth as sy

    schedules: list[dict[str, object]] = []
    for profile in ("dense", "sparse", "simultaneous", "open"):
        for event_count in event_counts:
            if profile == "open":

                @sy.track(seed=310, loop=True)
                def schedule_track() -> None:
                    sy.play(60, amp=0.1, release=0.001)
                    sy.sleep(1.0)

                duration = float(event_count)
            else:

                @sy.track(seed=310)
                def schedule_track(event_count: int = event_count, profile: str = profile) -> None:
                    for index in range(event_count):
                        sy.play(60 + index % 5, amp=0.1, release=0.001)
                        if profile == "dense":
                            sy.sleep(0.0001)
                        elif profile == "sparse":
                            sy.sleep(0.01)

                duration = max(0.02, event_count * (0.011 if profile == "sparse" else 0.001))
            track, declaration = _measure_python_phase(schedule_track)
            plan, expansion = _measure_python_phase(
                lambda track=track, duration=duration: track.physical_plan(duration=duration)
            )
            if len(plan.events) != event_count:
                raise SynthOracleError(
                    f"{profile} schedule expected {event_count} events, got {len(plan.events)}"
                )
            schedules.append(
                {
                    "profile": profile,
                    "event_count": event_count,
                    "open": profile == "open",
                    "declaration": declaration,
                    "expansion_and_sort": expansion,
                    "simultaneous_events": len({event.time_seconds for event in plan.events}) == 1,
                    "first_time": plan.events[0].time_seconds,
                    "last_time": plan.events[-1].time_seconds,
                    "serialized_bytes": len(plan.to_bytes()),
                    "digest": semantic_plan_digest(plan.to_dict()),
                }
            )

    controls: list[dict[str, object]] = []
    for control_count in control_counts:

        @sy.track(seed=310)
        def control_track(control_count: int = control_count) -> None:
            handle = sy.play(60, amp=0.1, release=0.01)
            for index in range(control_count):
                sy.control(handle, pan=-1.0 + 2.0 * (index % 17) / 16.0)

        track, declaration = _measure_python_phase(control_track)
        plan, expansion = _measure_python_phase(
            lambda track=track: track.physical_plan(duration=0.02)
        )
        if len(plan.events) != 1 or len(plan.controls) != control_count:
            raise SynthOracleError("control schedule count changed during physical expansion")
        target_ids = {control.target_id for control in plan.controls}
        if control_count and len(target_ids) != 1:
            raise SynthOracleError("same-scope controls did not preserve one target identity")
        controls.append(
            {
                "control_count": control_count,
                "event_count": len(plan.events),
                "target_count": len(target_ids),
                "same_time": len({control.time_seconds for control in plan.controls}) <= 1,
                "declaration": declaration,
                "expansion_and_sort": expansion,
                "serialized_bytes": len(plan.to_bytes()),
                "digest": semantic_plan_digest(plan.to_dict()),
            }
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "dense-sparse-simultaneous-open-finite-declarations",
            "event-and-control-target-expansion",
            "duration-boundary-and-production-sort",
            "semantic-digest",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "schedule_points": schedules,
            "control_points": controls,
            "target_scopes": ["node-handle", "active-fx-handle-covered-by-template-case"],
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "schedule_profiles": 4,
            "event_scale_count": len(event_counts),
            "control_scale_count": len(control_counts),
            "maximum_controls": control_counts[-1],
        },
    )


def _fresh_process_determinism(execution_class: ExecutionClass, work_units: int) -> SuiteExecution:
    script = """
import json
from benchmarks.suites.synth.oracles import semantic_plan_digest
from gummysnake import synth as sy

if {unrelated}:
    @sy.track(seed=999)
    def unrelated():
        for index in range(17):
            sy.play(40 + index, amp=0.1, release=0.001)
    unrelated().physical_plan(duration=0.02)

@sy.track(seed={seed})
def target():
    for index in range(32):
        sy.play(sy.choose([60, 62, 64]) + sy.rrand_i(0, 2), amp=0.1, release=0.001)
        sy.sleep(0.0001)
plan = target().physical_plan(duration=0.02)
print(json.dumps({{"digest": semantic_plan_digest(plan.to_dict()), "events": len(plan.events)}}))
"""

    def run_process(*, seed: int, unrelated: bool) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script.format(seed=seed, unrelated="True" if unrelated else "False"),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise SynthOracleError("fresh-process determinism probe did not return an object")
        return value

    baseline, baseline_phase = _measure_python_phase(lambda: run_process(seed=310, unrelated=False))
    repeated, repeated_phase = _measure_python_phase(lambda: run_process(seed=310, unrelated=False))
    with_history, history_phase = _measure_python_phase(
        lambda: run_process(seed=310, unrelated=True)
    )
    changed_seed, changed_seed_phase = _measure_python_phase(
        lambda: run_process(seed=311, unrelated=False)
    )
    if baseline != repeated or baseline != with_history:
        raise SynthOracleError(
            "seeded track normalized identity changed across fresh processes or build history"
        )
    if baseline.get("digest") == changed_seed.get("digest"):
        raise SynthOracleError("changed seed did not change stochastic normalized identity")

    from dataclasses import replace as dataclass_replace

    hostile_plan = _bridge_plan(1)
    nested: object = 0
    for _ in range(65):
        nested = {"nested": nested}
    hostile_failure = assert_expected_failure(
        lambda: dataclass_replace(hostile_plan, metadata={"value": nested}),
        tokens=("nesting", "depth", "limit"),
    )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "fresh-python-processes",
            "seeded-public-track-composition",
            "unrelated-build-history",
            "normalized-semantic-digest",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "baseline": baseline,
            "same_seed_repeat": repeated,
            "same_seed_after_unrelated_track": with_history,
            "changed_seed": changed_seed,
            "process_phase_measurements": [
                baseline_phase,
                repeated_phase,
                history_phase,
                changed_seed_phase,
            ],
            "hostile_value_depth_failure": hostile_failure,
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "fresh_processes": 4,
            "same_seed_stable": True,
            "unrelated_history_stable": True,
            "changed_seed_differs": True,
        },
    )


def _composition(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    if case_kind == "flat-scale-sweep":
        return _composition_scale_sweep(
            _positive_int_list(parameters, "event_counts", maximum=65_536),
            execution_class,
            work_units,
        )
    if case_kind == "nested-depth-sweep":
        return _nested_depth_sweep(
            _positive_int_list(parameters, "depths", maximum=8),
            execution_class,
            work_units,
        )
    if case_kind == "lazy-expression-sweep":
        return _lazy_expression_sweep(
            _positive_int_list(parameters, "graph_sizes", maximum=4_096),
            execution_class,
            work_units,
        )
    if case_kind == "template-cold-warm":
        return _template_cold_warm(
            _integer(parameters, "event_count", maximum=4_096),
            execution_class,
            work_units,
        )
    if case_kind == "schedule-control-sweep":
        return _schedule_control_sweep(
            _positive_int_list(parameters, "event_counts", maximum=16_384),
            _non_negative_int_list(parameters, "control_counts", maximum=16_384),
            execution_class,
            work_units,
        )
    if case_kind == "fresh-process-determinism":
        return _fresh_process_determinism(execution_class, work_units)

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
    serialization_metrics: Mapping[str, object],
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
            **serialization_metrics,
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


def _serialization_profile(
    plan: Any,
    *,
    label: str,
    item_count: int,
    runtime: Any,
) -> dict[str, object]:
    from gummysnake import synth as sy

    plan_dict, to_dict_phase = _measure_python_phase(plan.to_dict)
    json_payload, json_phase = _measure_python_phase(
        lambda: json.dumps(
            plan_dict,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    compressed, compress_phase = _measure_python_phase(lambda: zlib.compress(json_payload, level=9))
    decompressed, decompress_phase = _measure_python_phase(lambda: zlib.decompress(compressed))
    decoded, json_parse_phase = _measure_python_phase(
        lambda: json.loads(decompressed.decode("utf-8"))
    )
    typed_plan, typed_conversion_phase = _measure_python_phase(
        lambda: sy.PhysicalPlan.from_dict(decoded)
    )
    container, container_phase = _measure_python_phase(plan.to_bytes)
    roundtrip, full_roundtrip_phase = _measure_python_phase(
        lambda: sy.PhysicalPlan.from_bytes(container)
    )
    digest = semantic_plan_digest(plan_dict)
    if semantic_plan_digest(typed_plan.to_dict()) != digest:
        raise SynthOracleError(f"{label} JSON typed conversion changed plan semantics")
    if semantic_plan_digest(roundtrip.to_dict()) != digest:
        raise SynthOracleError(f"{label} container round trip changed plan semantics")
    if len(container) != 16 + len(compressed):
        raise SynthOracleError(f"{label} plan container byte accounting changed")

    runtime.synth_reset_diagnostics()
    _program, rust_compile_phase = _measure_python_phase(
        lambda: runtime.CanvasSynthProgram.from_serialized(container, plan.sample_rate)
    )
    rust_diagnostics = dict(runtime.synth_diagnostics())
    if int(rust_diagnostics.get("gil_released_compile_calls", 0)) < 1:
        raise SynthOracleError(f"{label} Rust compile did not report a GIL-released compile call")
    return {
        "label": label,
        "items": item_count,
        "events": len(plan.events),
        "controls": len(plan.controls),
        "value_depth_or_shape_items": item_count,
        "plan_digest": digest,
        "phases": {
            "python_to_dict_and_value_normalization": to_dict_phase,
            "python_json_serialize": json_phase,
            "python_zlib_compress": compress_phase,
            "python_zlib_decompress": decompress_phase,
            "python_json_parse": json_parse_phase,
            "python_typed_payload_conversion_and_validation": typed_conversion_phase,
            "python_plan_container": container_phase,
            "python_full_container_roundtrip": full_roundtrip_phase,
            "rust_decompress_parse_typed_validation_index_prepare": rust_compile_phase,
        },
        "bytes": {
            "json": len(json_payload),
            "compressed_body": len(compressed),
            "container": len(container),
            "decompressed": len(decompressed),
        },
        "compression_ratio": len(compressed) / max(1, len(json_payload)),
        "rust_compile_diagnostics": rust_diagnostics,
        "rust_split_phase_metrics": _availability(
            None,
            source=None,
            reason=(
                "CanvasSynthProgram exposes aggregate compile only; Rust decompression, JSON "
                "parse, typed conversion, validation, control indexing, and preparation are not "
                "split"
            ),
        ),
        "rust_allocation_metrics": _availability(
            None,
            source=None,
            reason="the public Synth diagnostics expose no Rust allocator counters",
        ),
        "bridge_copy_count": _availability(
            None,
            source=None,
            reason="the public PyO3 bridge exposes no runtime copy counter",
        ),
        "bridge_input_bytes": _availability(
            len(container), source="exact-Python-bytes-length-at-CanvasSynthProgram-input"
        ),
    }


def _serialization_shape_sweep(
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    from gummysnake import synth as sy

    event_counts = _positive_int_list(parameters, "event_counts", maximum=16_384)
    control_counts = _non_negative_int_list(parameters, "control_counts", maximum=16_384)
    value_depths = _positive_int_list(parameters, "value_depths", maximum=32)
    layer_counts = _positive_int_list(parameters, "layer_counts", maximum=16)
    fx_depths = _non_negative_int_list(parameters, "fx_depths", maximum=64)
    sample_path_counts = _positive_int_list(parameters, "sample_path_counts", maximum=64)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    sample_path = validate_packaged_sample_catalog()["reviewed-minimal-flac"]
    runtime = _runtime()

    def at_sample_rate(plan: Any) -> Any:
        return replace(plan, sample_rate=sample_rate)

    profiles: list[dict[str, object]] = []

    for event_count in event_counts:
        plan = at_sample_rate(_bridge_plan(event_count))
        profiles.append(
            _serialization_profile(
                plan,
                label=f"events-{event_count}",
                item_count=event_count,
                runtime=runtime,
            )
        )

    for control_count in control_counts:

        @sy.track(seed=310)
        def control_shape(control_count: int = control_count) -> None:
            handle = sy.play(60, amp=0.1, release=0.01)
            for index in range(control_count):
                sy.control(handle, pan=-1.0 + 2.0 * (index % 17) / 16.0)

        plan = at_sample_rate(control_shape().physical_plan(duration=0.02))
        profiles.append(
            _serialization_profile(
                plan,
                label=f"controls-{control_count}",
                item_count=control_count,
                runtime=runtime,
            )
        )

    base_plan = at_sample_rate(_bridge_plan(1))
    for value_depth in value_depths:
        nested: object = "leaf"
        for level in range(value_depth):
            nested = {"value": nested} if level % 2 == 0 else [nested]
        plan = replace(base_plan, metadata={"nested": nested, "repeated": ["same"] * 16})
        profiles.append(
            _serialization_profile(
                plan,
                label=f"value-depth-{value_depth}",
                item_count=value_depth,
                runtime=runtime,
            )
        )

    for layer_count in layer_counts:
        layers = [
            {
                "wave": ("sine", "saw", "pulse", "tri")[index % 4],
                "transpose": index % 12,
                "amp": 1.0 / layer_count,
                "opts": {"pulse_width": 0.4},
            }
            for index in range(layer_count)
        ]
        event = replace(base_plan.events[0], synth_name="_layered", opts={"layers": layers})
        plan = replace(base_plan, events=(event,))
        profiles.append(
            _serialization_profile(
                plan,
                label=f"layers-{layer_count}",
                item_count=layer_count,
                runtime=runtime,
            )
        )

    for fx_depth in fx_depths:
        fx_chain = tuple(
            sy.FxHandle(index + 1, "_lpf", {"cutoff": 70 + index % 30, "mix": 0.5})
            for index in range(fx_depth)
        )
        event = replace(base_plan.events[0], fx_chain=fx_chain)
        plan = replace(base_plan, events=(event,))
        profiles.append(
            _serialization_profile(
                plan,
                label=f"fx-depth-{fx_depth}",
                item_count=fx_depth,
                runtime=runtime,
            )
        )

    for path_count in sample_path_counts:

        @sy.track(seed=310)
        def sample_paths(path_count: int = path_count) -> None:
            for index in range(path_count):
                sy.sample(
                    sample_path,
                    amp=0.1,
                    metadata={"path_index": index, "repeated_path": str(sample_path)},
                )
                sy.sleep(0.0001)

        plan = at_sample_rate(sample_paths().physical_plan(duration=max(0.02, path_count * 0.001)))
        profiles.append(
            _serialization_profile(
                plan,
                label=f"sample-paths-{path_count}",
                item_count=path_count,
                runtime=runtime,
            )
        )

    phase_totals: dict[str, int] = {}
    for profile in profiles:
        phases = profile["phases"]
        if not isinstance(phases, Mapping):
            raise SynthWorkloadError("serialization profile omitted phase mappings")
        for name, measurement in phases.items():
            if isinstance(measurement, Mapping):
                phase_totals[name] = phase_totals.get(name, 0) + int(measurement["elapsed_ns"])
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-physical-plan-shape-sweeps",
            "independent-python-serialization-phases",
            "serialized-pyo3-aggregate-compile",
            "semantic-roundtrip-digests",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "profiles": profiles,
            "phase_totals_ns": phase_totals,
            "total_pre_dsp_latency_ns": sum(phase_totals.values()),
            "shape_axes": {
                "event_counts": list(event_counts),
                "control_counts": list(control_counts),
                "value_depths": list(value_depths),
                "layer_counts": list(layer_counts),
                "fx_depths": list(fx_depths),
                "sample_path_counts": list(sample_path_counts),
            },
            "python_allocation_semantics": (
                "net sys.getallocatedblocks deltas at each phase boundary"
            ),
            "gil_interval_semantics": (
                "public counters prove aggregate Rust compile releases the GIL; exact held "
                "intervals are unavailable and are not inferred from elapsed time"
            ),
        },
    )
    return SuiteExecution(
        diagnostics,
        {
            "serialization_profiles": len(profiles),
            "maximum_events": event_counts[-1],
            "maximum_controls": control_counts[-1],
            "maximum_value_depth": value_depths[-1],
            "maximum_layers": layer_counts[-1],
            "maximum_fx_depth": fx_depths[-1],
            "maximum_sample_paths": sample_path_counts[-1],
            "rendered_audio": False,
        },
    )


def _hostile_serialized_container(
    raw: bytes,
    *,
    magic: bytes = b"GSSPLAN\x01",
    compression: int = 1,
    declared_size: int | None = None,
) -> bytes:
    return struct.Struct(">8sII").pack(
        magic,
        compression,
        len(raw) if declared_size is None else declared_size,
    ) + zlib.compress(raw)


def _serialization_hostile_inputs(
    sample_rate: int, execution_class: ExecutionClass, work_units: int
) -> SuiteExecution:
    from gummysnake import synth as sy
    from gummysnake.synth.synth_runtime.values import foundation as synth_foundation

    base_plan = _bridge_plan(1)
    base_dict = base_plan.to_dict()
    serialized = base_plan.to_bytes()
    runtime = _runtime()
    failures: list[dict[str, object]] = []

    def record(label: str, operation: Callable[[], object], tokens: Sequence[str]) -> None:
        started_ns = perf_counter_ns()
        message = assert_expected_failure(operation, tokens=tokens)
        failures.append(
            {"label": label, "elapsed_ns": perf_counter_ns() - started_ns, "error": message}
        )

    record("short", lambda: sy.PhysicalPlan.from_bytes(b"short"), ("short",))
    record(
        "bad-header-version",
        lambda: sy.PhysicalPlan.from_bytes(b"BROKEN!!" + serialized[8:]),
        ("header", "invalid"),
    )
    record(
        "unsupported-compression",
        lambda: sy.PhysicalPlan.from_bytes(_hostile_serialized_container(b"{}", compression=99)),
        ("compression", "unsupported"),
    )
    record(
        "corrupt-zlib",
        lambda: sy.PhysicalPlan.from_bytes(serialized[:16] + b"not-zlib"),
        ("decompress", "zlib"),
    )
    record(
        "truncated-zlib",
        lambda: sy.PhysicalPlan.from_bytes(serialized[:-2]),
        ("truncated", "decompress", "size"),
    )
    record(
        "trailing-zlib-data",
        lambda: sy.PhysicalPlan.from_bytes(serialized + zlib.compress(b"trailing")),
        ("trailing",),
    )
    record(
        "invalid-json",
        lambda: sy.PhysicalPlan.from_bytes(_hostile_serialized_container(b"{")),
        ("json", "invalid"),
    )
    record(
        "json-non-object",
        lambda: sy.PhysicalPlan.from_bytes(_hostile_serialized_container(b"[]")),
        ("object",),
    )
    record(
        "unsupported-schema",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "schema": "future"}),
        ("schema", "unsupported"),
    )
    record(
        "nan-duration",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "duration_seconds": float("nan")}),
        ("finite", "duration"),
    )
    record(
        "infinite-duration",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "duration_seconds": float("inf")}),
        ("finite", "duration"),
    )
    record(
        "zero-rate",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "sample_rate": 0}),
        ("sample_rate", "[1"),
    )
    record(
        "unsupported-rate",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "sample_rate": 384_001}),
        ("sample_rate", "384000"),
    )
    negative_event = {**base_dict["events"][0], "time_seconds": -1.0}
    record(
        "negative-event-time",
        lambda: sy.PhysicalPlan.from_dict({**base_dict, "events": [negative_event]}),
        ("non-negative", "time_seconds"),
    )
    huge_event = {**base_dict["events"][0], "time_seconds": 1e12}
    record(
        "huge-event-time",
        lambda: sy.PhysicalPlan.from_dict(
            {**base_dict, "duration_seconds": 0.01, "events": [huge_event]}
        ),
        ("duration", "exceed"),
    )
    record(
        "output-frame-budget",
        lambda: replace(base_plan, duration_seconds=1_000_000.0),
        ("output budget", "frames"),
    )
    record(
        "unsupported-value",
        lambda: replace(base_plan, events=(replace(base_plan.events[0], value=object()),)),
        ("synth values", "serialized"),
    )
    record(
        "map-key-collision",
        lambda: replace(base_plan, events=(replace(base_plan.events[0], opts={1: "bad"}),)),
        ("keys must be strings", "not coerced"),
    )
    nested: object = 0
    for _ in range(65):
        nested = {"value": nested}
    record(
        "excessive-value-depth",
        lambda: replace(base_plan, metadata={"nested": nested}),
        ("nesting", "depth", "limit"),
    )
    declared_bomb = synth_foundation._GSS_HEADER.pack(
        synth_foundation._GSS_MAGIC,
        synth_foundation._GSS_COMPRESSION,
        synth_foundation._MAX_DECOMPRESSED_PLAN_BYTES + 1,
    )
    record(
        "declared-decompressed-size",
        lambda: sy.PhysicalPlan.from_bytes(declared_bomb),
        ("decompressed payload", "limit"),
    )
    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-hostile-riff-") as temporary:
        malformed_riff = Path(temporary) / "malformed.wav"
        malformed_riff.write_bytes(b"RIFF\xff\xff\xff\xffWAVEfmt ")
        record(
            "malformed-riff-resource",
            lambda: runtime.synth_sample_duration(str(malformed_riff)),
            ("decode", "wav", "sample"),
        )
    unknown_primitive = replace(
        base_plan,
        events=(replace(base_plan.events[0], synth_name="_unknown"),),
    ).to_bytes()
    record(
        "unknown-primitive",
        lambda: runtime.CanvasSynthProgram.from_serialized(unknown_primitive, sample_rate),
        ("unsupported", "primitive"),
    )
    unknown_fx = replace(
        base_plan,
        events=(
            replace(
                base_plan.events[0],
                fx_chain=(sy.FxHandle(1, "unknown", {}),),
            ),
        ),
    ).to_bytes()
    record(
        "unknown-fx",
        lambda: runtime.CanvasSynthProgram.from_serialized(unknown_fx, sample_rate),
        ("unsupported", "dry-pass"),
    )
    unknown_chain = replace(
        base_plan,
        events=(
            replace(
                base_plan.events[0],
                fx_chain=(sy.FxHandle(1, "_chain", {"ops": [{"op": "unknown"}]}),),
            ),
        ),
    ).to_bytes()
    record(
        "unknown-chain-operation",
        lambda: runtime.CanvasSynthProgram.from_serialized(unknown_chain, sample_rate),
        ("chain operation", "unsupported"),
    )
    if len(failures) != work_units:
        raise SynthWorkloadError(
            f"hostile-inputs executed {len(failures)} failures, expected work_units={work_units}"
        )
    diagnostics = path_diagnostics(
        execution_class,
        (
            "python-container-and-type-validation",
            "bounded-zlib-json-rejection",
            "serialized-pyo3-rust-validation",
            "no-parser-or-renderer-substitution",
        ),
        work_units=work_units,
        details={
            "rendered_audio": False,
            "failures": failures,
            "maximum_failure_elapsed_ns": max(_metric_int(item, "elapsed_ns") for item in failures),
            "preallocation_guards": [
                "compressed-size header",
                "declared decompressed-size header",
                "value nesting",
                "event/control/output budgets",
            ],
        },
    )
    return SuiteExecution(
        diagnostics,
        {"expected_failures": len(failures), "rendered_audio": False},
    )


def _serialization_bridge(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    sample_rate = _integer(parameters, "sample_rate", minimum=8_000, maximum=96_000)
    if case_kind == "phase-shape-sweep":
        return _serialization_shape_sweep(parameters, execution_class, work_units)
    if case_kind == "hostile-inputs":
        return _serialization_hostile_inputs(sample_rate, execution_class, work_units)

    event_count = _integer(parameters, "event_count", maximum=16_384)
    base_plan = _bridge_plan(event_count)
    plan = type(base_plan)(
        base_plan.events,
        base_plan.controls,
        base_plan.duration_seconds,
        sample_rate,
        base_plan.metadata,
    )
    metadata = {"benchmark": "synth-v1", "nested": {"depth": [1, 2, 3]}}
    serialization_state: dict[str, object] = {}
    prepared_plan_dict: Mapping[str, object] | None = None

    def prepare_serialization() -> dict[str, object]:
        serialization_state["plan"] = plan
        return serialization_state

    def warm_serialization(state: dict[str, object]) -> None:
        nonlocal prepared_plan_dict
        prepared_plan_dict = plan.to_dict(metadata=metadata)
        state["plan_dict"] = prepared_plan_dict

    def serialize_plan(_state: dict[str, object]) -> bytes:
        return plan.to_bytes(metadata=metadata)

    def validate_serialization(state: dict[str, object], payload: bytes) -> None:
        loaded = type(plan).from_bytes(payload)
        plan_dict = state["plan_dict"]
        if not isinstance(plan_dict, Mapping):
            raise SynthWorkloadError("serialization adapter lost its prepared plan dictionary")
        if semantic_plan_digest(loaded.to_dict()) != semantic_plan_digest(plan_dict):
            raise SynthOracleError("physical plan serialization changed normalized semantics")

    serialization_run = run_adapter(
        CallableSynthAdapter(
            prepare=prepare_serialization,
            warm=warm_serialization,
            timed=serialize_plan,
            synchronize=lambda _state, _payload: None,
            validate=validate_serialization,
            teardown=lambda state: state.clear(),
        )
    )
    if prepared_plan_dict is None:
        raise SynthWorkloadError("serialization adapter did not prepare its plan dictionary")
    semantic_digest = semantic_plan_digest(prepared_plan_dict)
    json_started_ns = perf_counter_ns()
    json_payload = json.dumps(
        prepared_plan_dict,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    json_elapsed_ns = perf_counter_ns() - json_started_ns
    zlib_started_ns = perf_counter_ns()
    zlib_payload = zlib.compress(json_payload)
    zlib_elapsed_ns = perf_counter_ns() - zlib_started_ns
    serialized = serialization_run.output
    serialization_metrics: dict[str, object] = {
        "python_to_dict_normalize_ns": serialization_run.phases.warm_ns,
        "python_plan_container_ns": serialization_run.phases.timed_ns,
        "serialized_validation_ns": serialization_run.phases.validate_ns,
        "python_json_serialize_ns": json_elapsed_ns,
        "python_zlib_compress_ns": zlib_elapsed_ns,
        "python_json_bytes": len(json_payload),
        "python_zlib_bytes": len(zlib_payload),
        "native_plan_container_bytes": len(serialized),
        "python_zlib_ratio": len(zlib_payload) / max(1, len(json_payload)),
        "pre_dsp_serialization_ns": (
            serialization_run.phases.prepare_ns
            + serialization_run.phases.warm_ns
            + serialization_run.phases.timed_ns
            + serialization_run.phases.synchronize_ns
            + serialization_run.phases.validate_ns
        ),
    }
    runtime = _runtime()
    if case_kind == "roundtrip":
        diagnostics = merge_lifecycle_diagnostics(
            path_diagnostics(
                execution_class,
                ("physical-plan", "to-dict", "json-zlib-container", "python-roundtrip"),
                work_units=work_units,
                details={
                    "rendered_audio": False,
                    "semantic_digest": semantic_digest,
                    **serialization_metrics,
                },
            ),
            serialization_run,
        )
        return SuiteExecution(
            diagnostics,
            {
                "events": len(plan.events),
                "controls": len(plan.controls),
                "raw_dict_keys": len(prepared_plan_dict),
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
            event_payloads, direct_payload_phase = _measure_python_phase(
                lambda: _event_payloads(plan)
            )
            direct, direct_bridge_phase = _measure_python_phase(
                lambda: bytes(
                    runtime.synth_render_plan_wav(
                        event_payloads, plan.duration_seconds, sample_rate
                    )
                )
            )
            bridged, serialized_bridge_phase = _measure_python_phase(
                lambda: bytes(runtime.synth_render_serialized_plan_wav(serialized, sample_rate))
            )
            runtime_diagnostics = dict(runtime.synth_diagnostics())
            digest = assert_repeatable(
                direct, bridged, label="direct and serialized PyO3 bridge routes"
            )
            signal = assert_wav_contract(bridged, sample_rate=sample_rate)
            diagnostics = merge_lifecycle_diagnostics(
                path_diagnostics(
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
                        "direct_payload_conversion": direct_payload_phase,
                        "direct_bridge_render": direct_bridge_phase,
                        "serialized_bridge_compile_render": serialized_bridge_phase,
                        "bridge_copy_count": _availability(
                            None,
                            source=None,
                            reason="public PyO3 diagnostics expose no copy counter",
                        ),
                        "direct_python_payload_items": len(event_payloads),
                        "serialized_bridge_input_bytes": len(serialized),
                        "bridge_output_bytes": len(bridged),
                        **serialization_metrics,
                        **runtime_diagnostics,
                    },
                ),
                serialization_run,
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
                serialized,
                sample_rate,
                semantic_digest,
                serialization_metrics,
                execution_class,
                work_units,
                len(plan.events),
            )
    finally:
        runtime.synth_set_worker_count("auto")
    raise SynthWorkloadError(f"unknown serialization case_kind: {case_kind!r}")


def _voice_rate_polyphony_matrix(
    sample_rates: Sequence[int],
    polyphonies: Sequence[int],
) -> tuple[dict[str, object], list[tuple[int, int]]]:
    cases: list[dict[str, object]] = []
    scaling: dict[int, int] = {polyphony: 0 for polyphony in polyphonies}
    for sample_rate in sample_rates:
        for polyphony in polyphonies:
            notes = [57 + index for index in range(polyphony)]
            for oscillator in _OSCILLATORS:
                plan = _physical_voice_plan(
                    oscillator,
                    duration=0.045,
                    notes=notes,
                    opts={
                        "attack": 0.001,
                        "sustain": 0.018,
                        "release": 0.008,
                        "amp": 0.18,
                    },
                )
                first, phase = _measure_python_phase(
                    lambda plan=plan, sample_rate=sample_rate: plan.render(sample_rate=sample_rate)
                )
                second = plan.render(sample_rate=sample_rate)
                digest = assert_repeatable(
                    first,
                    second,
                    label=f"{oscillator}/{sample_rate}/{polyphony}",
                )
                summary = assert_wav_contract(first, sample_rate=sample_rate)
                scaling[polyphony] += _elapsed_ns(phase)
                cases.append(
                    {
                        "oscillator": oscillator,
                        "sample_rate": sample_rate,
                        "polyphony": polyphony,
                        "digest": digest,
                        "frames": summary.frames,
                        "peak": summary.peak,
                        "rms": summary.rms,
                        "render": phase,
                    }
                )
    return (
        {
            "cases": cases,
            "sample_rates": list(sample_rates),
            "polyphonies": list(polyphonies),
            "oscillators": list(_OSCILLATORS),
            "polyphony_elapsed_slope": _complexity_slope(sorted(scaling.items())),
            "unavailable_hot_path_counters": {
                "available": False,
                "reason": (
                    "public Synth diagnostics do not expose per-voice phase, coefficient-update, "
                    "temporary-byte, or control-lookup counters"
                ),
            },
        },
        sorted(scaling.items()),
    )


def _layer_envelope_filter_automation_matrix(
    sample_rates: Sequence[int],
    polyphonies: Sequence[int],
    layer_counts: Sequence[int],
    envelope_curves: Sequence[int],
    automation_counts: Sequence[int],
) -> dict[str, object]:
    from gummysnake import synth as sy

    layer_cases: list[dict[str, object]] = []
    envelope_cases: list[dict[str, object]] = []
    filter_cases: list[dict[str, object]] = []
    automation_cases: list[dict[str, object]] = []
    waves = ("sine", "saw", "pulse", "tri", "noise", "fm")
    filter_profiles = (
        ("lpf", {"cutoff": 78, "mix": 1.0}),
        ("rlpf", {"cutoff": 78, "res": 0.7, "mix": 1.0}),
        ("hpf", {"cutoff": 58, "mix": 1.0}),
        ("rhpf", {"cutoff": 58, "res": 0.7, "mix": 1.0}),
        ("wobble", {"phase": 0.012, "cutoff_min": 45, "cutoff_max": 100, "mix": 1.0}),
        ("nrlpf", {"cutoff": 82, "res": 0.55, "mix": 1.0}),
    )
    for sample_rate in sample_rates:
        for polyphony in polyphonies:
            for layer_count in layer_counts:
                layers = [
                    {
                        "wave": waves[index % len(waves)],
                        "transpose": (index % 5) - 2,
                        "amp": 1.0 / layer_count,
                        "opts": {"pulse_width": 0.35, "divisor": 2.0, "depth": 0.8},
                    }
                    for index in range(layer_count)
                ]

                @sy.track(seed=310)
                def layered_matrix_track(
                    polyphony: int = polyphony,
                    layers: list[dict[str, object]] = layers,
                ) -> None:
                    with sy.synth("_layered"):
                        sy.play(
                            [57 + index for index in range(polyphony)],
                            layers=layers,
                            attack=0.002,
                            sustain=0.018,
                            release=0.008,
                            amp=0.22,
                        )

                plan = layered_matrix_track().physical_plan(duration=0.05)
                first = plan.render(sample_rate=sample_rate)
                digest = assert_repeatable(
                    first,
                    plan.render(sample_rate=sample_rate),
                    label=f"layers/{sample_rate}/{polyphony}/{layer_count}",
                )
                layer_cases.append(
                    {
                        "sample_rate": sample_rate,
                        "polyphony": polyphony,
                        "layers": layer_count,
                        "digest": digest,
                        "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
                    }
                )
        for curve in envelope_curves:
            for profile, stages in (
                ("zero-edges", (0.0, 0.0, 0.04, 0.0, 0.05)),
                ("nonzero-stages", (0.02, 0.0, 0.04, 0.02, 0.09)),
            ):
                attack, decay, sustain, release, render_duration = stages
                plan = _physical_voice_plan(
                    "sine",
                    duration=render_duration,
                    opts={
                        "attack": attack,
                        "decay": decay,
                        "sustain": sustain,
                        "release": release,
                        "env_curve": curve,
                        "amp": 0.22,
                    },
                )
                first = plan.render(sample_rate=sample_rate)
                envelope_cases.append(
                    {
                        "sample_rate": sample_rate,
                        "curve": curve,
                        "profile": profile,
                        "digest": assert_repeatable(
                            first,
                            plan.render(sample_rate=sample_rate),
                            label=f"envelope/{sample_rate}/{curve}/{profile}",
                        ),
                        "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
                        "shape": (
                            dict(assert_envelope_shape(first))
                            if curve == 3 and profile == "nonzero-stages"
                            else None
                        ),
                    }
                )
        for filter_name, filter_opts in filter_profiles:
            plan = _physical_voice_plan(
                "saw",
                duration=0.065,
                opts={"attack": 0.001, "sustain": 0.025, "release": 0.01, "amp": 0.2},
                fx_name=filter_name,
                fx_opts=filter_opts,
            )
            first = plan.render(sample_rate=sample_rate)
            filter_cases.append(
                {
                    "sample_rate": sample_rate,
                    "filter": filter_name,
                    "digest": assert_repeatable(
                        first,
                        plan.render(sample_rate=sample_rate),
                        label=f"filter/{sample_rate}/{filter_name}",
                    ),
                    "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
                }
            )
        for control_count in automation_counts:

            @sy.track(seed=310)
            def automated_matrix_track(control_count: int = control_count) -> None:
                with sy.synth("_pulse"):
                    handle = sy.play(
                        60,
                        attack=0.001,
                        sustain=0.045,
                        release=0.012,
                        amp=0.18,
                        pulse_width=0.3,
                        cutoff=100,
                        res=0.2,
                    )
                    for index in range(control_count):
                        sy.control(
                            handle,
                            note=60 + index % 8,
                            note_slide=0.001,
                            amp=0.12 + (index % 3) * 0.03,
                            amp_slide=0.001,
                            pan=-0.75 + (index % 7) * 0.25,
                            pan_slide=0.001,
                            pulse_width=0.2 + (index % 5) * 0.12,
                            pulse_width_slide=0.001,
                            cutoff=55 + index % 55,
                            cutoff_slide=0.001,
                            res=0.1 + (index % 5) * 0.15,
                            res_slide=0.001,
                        )
                        if index:
                            sy.sleep(0.0002)

            plan = automated_matrix_track().physical_plan(duration=0.08)
            if len(plan.controls) != control_count:
                raise SynthOracleError(
                    f"automation matrix expected {control_count} controls, got {len(plan.controls)}"
                )
            first = plan.render(sample_rate=sample_rate)
            automation_cases.append(
                {
                    "sample_rate": sample_rate,
                    "control_count": control_count,
                    "digest": assert_repeatable(
                        first,
                        plan.render(sample_rate=sample_rate),
                        label=f"automation/{sample_rate}/{control_count}",
                    ),
                    "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
                    "same_frame_later_control_wins_declared_order": control_count >= 2,
                }
            )
    return {
        "layers": layer_cases,
        "envelopes": envelope_cases,
        "filters": filter_cases,
        "automation": automation_cases,
        "filter_coefficient_updates": _availability(
            None,
            source=None,
            reason="the public runtime does not expose filter coefficient-update counters",
        ),
        "automation_lookups": _availability(
            None,
            source=None,
            reason="the public runtime does not expose control cursor lookup counters",
        ),
    }


def _voices_filters_automation(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    if case_kind == "voice-rate-polyphony-matrix":
        sample_rates = _positive_int_list(parameters, "sample_rates", maximum=96_000)
        polyphonies = _positive_int_list(parameters, "polyphonies", maximum=12)
        matrix, scaling = _voice_rate_polyphony_matrix(sample_rates, polyphonies)
        return SuiteExecution(
            path_diagnostics(
                execution_class,
                (
                    "public-track",
                    "serialized-pyo3",
                    "stateful-rust-oscillator-voices",
                    "stateful-block-wav-memory-sink",
                ),
                work_units=work_units,
                details={"matrix": matrix, "polyphony_elapsed_points": scaling},
            ),
            {
                "matrix_renders": len(_OSCILLATORS) * len(sample_rates) * len(polyphonies),
                "sample_rates": len(sample_rates),
                "polyphonies": len(polyphonies),
            },
        )
    if case_kind == "layer-envelope-filter-automation-matrix":
        sample_rates = _positive_int_list(parameters, "sample_rates", maximum=96_000)
        polyphonies = _positive_int_list(parameters, "polyphonies", maximum=12)
        layer_counts = _positive_int_list(parameters, "layer_counts", maximum=16)
        envelope_curves = _integer_list(parameters, "envelope_curves", minimum=-10, maximum=10)
        automation_counts = _non_negative_int_list(parameters, "automation_counts", maximum=64)
        matrix = _layer_envelope_filter_automation_matrix(
            sample_rates,
            polyphonies,
            layer_counts,
            envelope_curves,
            automation_counts,
        )
        return SuiteExecution(
            path_diagnostics(
                execution_class,
                (
                    "public-track",
                    "serialized-pyo3",
                    "stateful-layer-envelope-filter-control-dsp",
                    "stateful-block-wav-memory-sink",
                ),
                work_units=work_units,
                details={"matrix": matrix},
            ),
            {
                "layer_cases": len(_metric_list(matrix, "layers")),
                "envelope_cases": len(_metric_list(matrix, "envelopes")),
                "filter_cases": len(_metric_list(matrix, "filters")),
                "automation_cases": len(_metric_list(matrix, "automation")),
            },
        )
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


def _decode_metadata_matrix() -> dict[str, object]:
    from gummysnake import synth as sy

    validate_pcm_variant_manifest()
    runtime = _runtime()
    sy.reset_synth_diagnostics()
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-decode-matrix-") as temporary:
        root = Path(temporary)
        for case in pcm_variant_catalog():
            fixture = generate_signal(
                case.signal_kind,
                sample_rate=case.sample_rate,
                duration_seconds=case.duration_seconds,
            )
            payload = pcm_wav_bytes(
                fixture,
                sample_width=case.sample_width,
                force_mono=case.force_mono,
            )
            path = root / f"{case.name}.wav"
            path.write_bytes(payload)
            first = float(runtime.synth_sample_duration(str(path)))
            second = float(runtime.synth_sample_duration(str(path)))
            expected = fixture.frames / fixture.sample_rate
            if first != second or abs(first - expected) > 1.0 / fixture.sample_rate:
                raise SynthOracleError(
                    f"PCM metadata duration mismatch for {case.name}: {first} != {expected}"
                )
            cases.append(
                {
                    "name": case.name,
                    "sample_rate": case.sample_rate,
                    "sample_width": case.sample_width,
                    "channels": 1 if case.force_mono else fixture.channels,
                    "frames": fixture.frames,
                    "bytes": len(payload),
                    "digest": "sha256:" + sha256(payload).hexdigest(),
                    "duration": first,
                    "cold_warm_exact": True,
                }
            )
        if len(tuple(root.iterdir())) != len(pcm_variant_catalog()):
            raise SynthOracleError("PCM decode matrix did not materialize every declared fixture")
    packaged_paths = validate_packaged_sample_catalog()
    packaged: list[dict[str, object]] = []
    for case in packaged_sample_catalog():
        path = packaged_paths[case.name]
        first = float(runtime.synth_sample_duration(str(path)))
        second = float(runtime.synth_sample_duration(str(path)))
        if first != second or abs(first - case.expected_duration_seconds) > 1e-12:
            raise SynthOracleError(f"FLAC metadata duration mismatch for {case.name}")
        packaged.append(
            {
                "name": case.name,
                "bytes": case.byte_length,
                "digest": "sha256:" + case.sha256,
                "duration": first,
                "cold_warm_exact": True,
            }
        )
    runtime_diagnostics = dict(sy.synth_diagnostics())
    expected_decode_calls = (len(cases) + len(packaged)) * 2
    if _metric_int(runtime_diagnostics, "gil_released_decode_calls") < expected_decode_calls:
        raise SynthOracleError("public decode diagnostics omitted metadata decode calls")
    return {
        "pcm_cases": cases,
        "flac_cases": packaged,
        "runtime_diagnostics": runtime_diagnostics,
        "cache_metrics": _availability(
            None,
            source=None,
            reason="the public sample cache exposes no hit, miss, eviction, lock, or byte counters",
        ),
        "temporary_files_removed": not root.exists(),
    }


def _resample_slice_playback_rate_matrix(
    source_rates: Sequence[int],
    target_rates: Sequence[int],
    playback_rates: Sequence[float],
) -> dict[str, object]:
    from gummysnake import synth as sy

    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-resample-matrix-") as temporary:
        root = Path(temporary)
        for source_rate in source_rates:
            source = generate_signal(
                "asymmetric-stereo", sample_rate=source_rate, duration_seconds=0.032
            )
            source_payload = pcm_wav_bytes(source)
            source_path = root / f"source-{source_rate}.wav"
            source_path.write_bytes(source_payload)
            source_digest = "sha256:" + sha256(source_payload).hexdigest()
            for target_rate in target_rates:
                for playback_rate in playback_rates:

                    @sy.track(seed=310)
                    def sample_matrix_track(
                        source_path: Path = source_path,
                        playback_rate: float = playback_rate,
                    ) -> None:
                        sy.sample(
                            source_path,
                            start=0.125,
                            finish=0.875,
                            rate=playback_rate,
                            attack=0.001,
                            release=0.002,
                            amp=0.5,
                            pan=0.2,
                        )

                    plan = sample_matrix_track().physical_plan(duration=0.3)
                    first = plan.render(sample_rate=target_rate)
                    second = plan.render(sample_rate=target_rate)
                    summary = assert_wav_contract(first, sample_rate=target_rate)
                    if "sha256:" + sha256(source_path.read_bytes()).hexdigest() != source_digest:
                        raise SynthOracleError("sample resampling mutated the source asset")
                    cases.append(
                        {
                            "source_rate": source_rate,
                            "target_rate": target_rate,
                            "playback_rate": playback_rate,
                            "reverse": playback_rate < 0.0,
                            "slice": [0.125, 0.875],
                            "source_digest": source_digest,
                            "pcm_digest": assert_repeatable(
                                first,
                                second,
                                label=(f"sample/{source_rate}/{target_rate}/{playback_rate:g}"),
                            ),
                            "signal": summary.to_dict(),
                        }
                    )
    return {
        "cases": cases,
        "source_rates": list(source_rates),
        "target_rates": list(target_rates),
        "playback_rates": list(playback_rates),
        "temporary_files_removed": not root.exists(),
        "anti_alias_metric": _availability(
            None,
            source=None,
            reason=(
                "the public runtime exposes exact PCM for review but no resampler passband/alias "
                "diagnostic counter"
            ),
        ),
    }


def _sample_engine(
    case_kind: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
    work_units: int,
) -> SuiteExecution:
    require_route(execution_class)
    if case_kind == "decode-metadata-matrix":
        matrix = _decode_metadata_matrix()
        return SuiteExecution(
            path_diagnostics(
                execution_class,
                (
                    "runtime-generated-pcm-wav-and-packaged-flac",
                    "public-sample-duration",
                    "rust-decoders",
                    "public-decode-diagnostics",
                ),
                work_units=work_units,
                details={"matrix": matrix},
            ),
            {
                "pcm_assets": len(_metric_list(matrix, "pcm_cases")),
                "flac_assets": len(_metric_list(matrix, "flac_cases")),
                "decode_calls": work_units,
            },
        )
    if case_kind == "resample-slice-playback-rate-matrix":
        source_rates = _positive_int_list(parameters, "source_rates", maximum=96_000)
        target_rates = _positive_int_list(parameters, "target_rates", maximum=96_000)
        playback_rates = _number_list(
            parameters,
            "playback_rates",
            minimum=-8.0,
            maximum=8.0,
            allow_zero=False,
        )
        matrix = _resample_slice_playback_rate_matrix(source_rates, target_rates, playback_rates)
        return SuiteExecution(
            path_diagnostics(
                execution_class,
                (
                    "runtime-generated-stereo-pcm",
                    "public-sample-event",
                    "stateful-rust-sample-reader-and-resampler",
                    "stateful-block-wav-memory-sink",
                ),
                work_units=work_units,
                details={"matrix": matrix},
            ),
            {
                "matrix_renders": len(_metric_list(matrix, "cases")),
                "temporary_files_removed": True,
            },
        )
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
    packaged_paths = validate_packaged_sample_catalog()
    packaged_cases = {case.name: case for case in packaged_sample_catalog()}
    generated_case_names = (
        "mono-8bit",
        "mono-16bit",
        "stereo-16bit",
        "stereo-32bit",
        "transients-8bit",
        "transients-32bit",
    )
    cold_identities: list[str] = []
    warm_identities: list[str] = []
    with generated_sample_files(sample_rate=source_rate) as generated:
        decoder_cases = {
            **{name: generated.paths[name] for name in generated_case_names},
            **packaged_paths,
        }
        for name, path in decoder_cases.items():
            duration = float(runtime.synth_sample_duration(str(path)))
            repeated = float(runtime.synth_sample_duration(str(path)))
            packaged = name in packaged_cases
            expected_duration = (
                packaged_cases[name].expected_duration_seconds if packaged else 0.125
            )
            duration_tolerance = 1e-12 if packaged else 1.0 / source_rate
            if duration != repeated or abs(duration - expected_duration) > duration_tolerance:
                raise SynthOracleError(
                    f"sample duration/cache reuse mismatch for {name}: {duration}"
                )
            duration_results[name] = duration
            cold_identities.append(f"cold:{name}")
            warm_identities.append(f"warm:{name}")
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
            "packaged_sample_cases": [case.name for case in packaged_sample_catalog()],
            "duration_results": duration_results,
            "signal_oracles": render_summaries,
            "pcm_digest": digest,
            "cache_identities": {"cold": cold_identities, "warm": warm_identities},
            "cache_metrics": {
                "available": False,
                "reason": "production sample cache exposes no public byte/hit/miss counters",
            },
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


def _chain_bus_scaling_matrix(
    sample_rate: int,
    chain_depths: Sequence[int],
    bus_counts: Sequence[int],
) -> dict[str, object]:
    from gummysnake import synth as sy

    chain_cases: list[dict[str, object]] = []
    bus_cases: list[dict[str, object]] = []
    chain_fx = (
        ("_lpf", {"cutoff": 92, "mix": 0.8}),
        ("_distortion", {"distort": 0.35, "mix": 0.35}),
        ("_echo", {"phase": 0.006, "decay": 0.018, "max_phase": 0.03, "mix": 0.25}),
        ("_compressor", {"threshold": 0.1, "slope_above": 0.4, "mix": 0.8}),
    )
    for depth in chain_depths:

        @sy.track(seed=310)
        def chain_track(depth: int = depth) -> None:
            with sy.synth("_saw"), ExitStack() as stack:
                for index in range(depth):
                    name, options = chain_fx[index % len(chain_fx)]
                    stack.enter_context(sy.fx(name, **options))
                sy.play(60, attack=0.001, sustain=0.025, release=0.015, amp=0.18)

        plan = chain_track().physical_plan(duration=0.09)
        first = plan.render(sample_rate=sample_rate)
        chain_cases.append(
            {
                "depth": depth,
                "digest": assert_repeatable(
                    first,
                    plan.render(sample_rate=sample_rate),
                    label=f"fx-chain-depth-{depth}",
                ),
                "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
            }
        )
    for bus_count in bus_counts:

        @sy.track(seed=310)
        def bus_track(bus_count: int = bus_count) -> None:
            with sy.synth("_sine"):
                for index in range(bus_count):
                    with sy.fx(
                        "_rlpf",
                        cutoff=60 + index % 35,
                        res=0.2 + (index % 4) * 0.15,
                        mix=0.8,
                    ):
                        sy.play(
                            48 + index % 24,
                            attack=0.001,
                            sustain=0.012,
                            release=0.006,
                            amp=0.18 / max(1, bus_count),
                        )

        plan = bus_track().physical_plan(duration=0.07)
        first = plan.render(sample_rate=sample_rate)
        bus_cases.append(
            {
                "buses": bus_count,
                "events": len(plan.events),
                "digest": assert_repeatable(
                    first,
                    plan.render(sample_rate=sample_rate),
                    label=f"fx-buses-{bus_count}",
                ),
                "signal": assert_wav_contract(first, sample_rate=sample_rate).to_dict(),
            }
        )
    return {
        "chain_cases": chain_cases,
        "bus_cases": bus_cases,
        "scratch_and_bus_bytes": _availability(
            None,
            source=None,
            reason=(
                "stateful renderer scratch and bus high-water counters are not exposed to Python"
            ),
        ),
    }


def _stateful_memory_file_output_scales(
    sample_rate: int,
    durations: Sequence[int],
) -> dict[str, object]:
    from gummysnake import synth as sy

    cases: list[dict[str, object]] = []
    sy.reset_synth_diagnostics()
    with tempfile.TemporaryDirectory(prefix="gummysnake-stateful-output-") as temporary:
        root = Path(temporary)
        for duration in durations:

            @sy.track(seed=310)
            def output_track(duration: int = duration) -> None:
                with sy.synth("_sine"), sy.fx("_lpf", cutoff=90, mix=0.75):
                    sy.play(
                        57,
                        attack=0.002,
                        sustain=max(0.01, duration - 0.012),
                        release=0.01,
                        amp=0.18,
                    )

            memory_track = output_track()
            memory, memory_phase = _measure_python_phase(
                lambda memory_track=memory_track, duration=duration: memory_track.render(
                    duration=duration, sample_rate=sample_rate
                )
            )
            output = root / f"stateful-{duration}s.wav"
            file_track = output_track()
            _, file_phase = _measure_python_phase(
                lambda file_track=file_track, output=output, duration=duration: file_track.save(
                    output, duration=duration, sample_rate=sample_rate
                )
            )
            file_payload = output.read_bytes()
            digest = assert_repeatable(memory, file_payload, label=f"memory/file-{duration}s")
            signal = assert_wav_contract(memory, sample_rate=sample_rate)
            cases.append(
                {
                    "duration_seconds": duration,
                    "frames": signal.frames,
                    "bytes": len(memory),
                    "digest": digest,
                    "memory_render": memory_phase,
                    "streaming_file_render": file_phase,
                    "exact_sink_parity": True,
                }
            )
    runtime_diagnostics = dict(sy.synth_diagnostics())
    if _metric_int(runtime_diagnostics, "gil_released_render_calls") < len(durations) * 2:
        raise SynthOracleError("stateful output scales omitted public render diagnostics")
    if _metric_int(runtime_diagnostics, "gil_released_wav_write_calls") < len(durations):
        raise SynthOracleError("stateful file scales omitted public WAV-write diagnostics")
    return {
        "cases": cases,
        "runtime_diagnostics": runtime_diagnostics,
        "temporary_files_removed": not root.exists(),
        "renderer_contract": (
            "canonical StatefulBlockRenderer feeds both the memory WAV and incremental file sink"
        ),
        "block_partition_diagnostics": _availability(
            None,
            source=None,
            reason=(
                "Python exposes the canonical default block renderer but not configurable block "
                "partitions or per-session BlockRenderDiagnostics"
            ),
        ),
    }


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
            "stateful-rust-shared-bus-tree",
            "running-peak-normaliser-and-stateful-output-limiter",
            "stateful-block-wav-bytes-and-file-sinks",
        )
        summary = {"bus_topologies": 2, "output_bytes": output_bytes}
    elif case_kind == "chain-bus-scaling-matrix":
        chain_depths = _positive_int_list(parameters, "chain_depths", maximum=8)
        bus_counts = _positive_int_list(parameters, "bus_counts", maximum=32)
        oracles = _chain_bus_scaling_matrix(sample_rate, chain_depths, bus_counts)
        output_bytes = 0
        path = (
            "public-track-fx-contexts",
            "stateful-rust-nested-chain-and-bus-graph",
            "stateful-block-wav-memory-sink",
        )
        summary = {
            "chain_depths": len(chain_depths),
            "bus_scales": len(bus_counts),
            "processor_instances": work_units,
        }
    elif case_kind == "stateful-memory-file-output-scales":
        durations = _positive_int_list(parameters, "duration_seconds", maximum=60)
        oracles = _stateful_memory_file_output_scales(sample_rate, durations)
        output_bytes = sum(
            int(case["bytes"])
            for case in _metric_list(oracles, "cases")
            if isinstance(case, Mapping)
        )
        path = (
            "public-track-render-and-save",
            "serialized-pyo3-compiled-program",
            "canonical-stateful-block-renderer",
            "memory-and-streaming-file-wav-sinks",
        )
        summary = {
            "duration_scales": list(durations),
            "rendered_audio_seconds": work_units,
            "output_bytes": output_bytes,
        }
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
                "stateful running-peak FX normaliser; the separate versioned causal lookahead "
                "normaliser is not selected by the public renderer"
            ),
        },
    )
    return SuiteExecution(diagnostics, summary)


def _simulated_sink(payload: bytes, block_frames: int) -> Mapping[str, object]:
    run = run_adapter(simulated_realtime_adapter(payload, block_frames=block_frames))
    output = run.output
    return {
        "blocks": len(output.blocks),
        "block_frames": block_frames,
        "block_frame_distribution": {
            "minimum": min(output.block_frames),
            "maximum": max(output.block_frames),
            "total": sum(output.block_frames),
        },
        "block_time_ns": run.instrumentation.block_time_ns.as_dict(),
        "queue_low_frames": output.queue_low_frames,
        "queue_high_frames": output.queue_high_frames,
        "underruns": output.underruns,
        "deadline_misses": output.deadline_misses,
        "deadline_clock": "deterministic-virtual-clock-no-sleep",
        "partition_digest": "sha256:" + sha256(output.pcm).hexdigest(),
        "adapter_lifecycle": run.diagnostics(),
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
    voice_opts = {
        "attack": 0.005,
        "sustain": max(0.005, duration - 0.015),
        "release": 0.01,
        "amp": 0.3,
    }
    fx_opts = {"phase": 0.01, "decay": 0.03, "max_phase": 0.05, "mix": 0.3}
    track = _voice_track(
        "sine",
        opts=voice_opts,
        fx_name="echo",
        fx_opts=fx_opts,
    )
    if case_kind == "simulated-realtime-block-sink":
        require_route(execution_class, simulated=True)
        payload = track.render(duration=duration, sample_rate=sample_rate)
        signal = assert_wav_contract(payload, sample_rate=sample_rate)
        sink = _simulated_sink(payload, block_frames)
        diagnostics = path_diagnostics(
            execution_class,
            (
                "bounded-stateful-rust-render-to-complete-wav",
                "post-render-pcm-partition-adapter",
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
    if case_kind == "stateful-block-memory-file-parity":
        memory = track.render(duration=duration, sample_rate=sample_rate)
        with tempfile.TemporaryDirectory(prefix="gummysnake-stateful-stream-") as temporary:
            output = Path(temporary) / "stateful-stream.wav"
            file_track = _voice_track("sine", opts=voice_opts, fx_name="echo", fx_opts=fx_opts)
            file_track.save(output, duration=duration, sample_rate=sample_rate)
            file_payload = output.read_bytes()
        digest = assert_repeatable(memory, file_payload, label="stateful memory/file stream")
        signal = assert_wav_contract(memory, sample_rate=sample_rate)
        diagnostics = path_diagnostics(
            execution_class,
            (
                "public-track-render-and-save",
                "serialized-pyo3-compiled-program",
                "canonical-stateful-block-renderer",
                "memory-and-incremental-file-wav-sinks",
            ),
            work_units=work_units,
            details={
                "signal": signal.to_dict(),
                "pcm_digest": digest,
                "exact_sink_parity": True,
                "temporary_files_removed": not output.exists(),
                "true_block_streaming": True,
                "block_partition_control": _availability(
                    None,
                    source=None,
                    reason=(
                        "public Track APIs use the canonical default block size but do not expose "
                        "arbitrary partition selection"
                    ),
                ),
            },
        )
        return SuiteExecution(
            diagnostics,
            {"sink_routes": 2, "frames": signal.frames, "wav_bytes": len(memory)},
        )
    if case_kind == "stateful-route-guards":
        payload = track.render(duration=duration, sample_rate=sample_rate)
        runtime = _runtime()
        plan = track.physical_plan(duration=duration)
        program = runtime.CanvasSynthProgram.from_serialized(plan.to_bytes(), sample_rate)
        native_failure = assert_expected_failure(
            lambda: run_adapter(physical_sdl_adapter(runtime, pre_device_wav=payload)),
            tokens=("allow_physical_device",),
        )
        guards = {
            "configurable_block_partition_available": callable(
                getattr(program, "render_block", None)
            ),
            "block_session_diagnostics_available": callable(
                getattr(program, "block_diagnostics", None)
            ),
            "native_device_guard": native_failure,
            "rolling_headless_route_available": False,
            "rolling_reason": (
                "public rolling Track.play is a native-device route; no deterministic headless "
                "rolling sink is exposed"
            ),
        }
        if (
            guards["configurable_block_partition_available"]
            or guards["block_session_diagnostics_available"]
        ):
            raise SynthOracleError(
                "stateful route guard is stale; expose and benchmark the new API"
            )
        return SuiteExecution(
            path_diagnostics(
                execution_class,
                (
                    "public-track-and-compiled-program-inspection",
                    "physical-sdl-adapter-pre-open-guard",
                    "no-offline-or-simulated-substitution",
                ),
                work_units=work_units,
                details={"guards": guards},
            ),
            {"guarded_routes": 3, "physical_device_opened": False},
        )
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
    failures.extend(
        (
            assert_expected_failure(
                lambda: _runtime().synth_render_plan_wav([], float("inf"), sample_rate),
                tokens=("finite", "duration"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_plan_wav([], 0.01, 0),
                tokens=("sample rate", "greater than zero", "range"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_plan_wav([], 1_000_000_000.0, sample_rate),
                tokens=("frame", "limit", "duration", "large"),
            ),
            assert_expected_failure(
                lambda: _runtime().synth_render_event_wav(
                    {**base_event, "opts": {"release": 0.01, "unknown_option": 1}},
                    sample_rate,
                ),
                tokens=("unsupported", "option"),
            ),
        )
    )
    with tempfile.TemporaryDirectory(prefix="gummysnake-malformed-sample-") as temporary:
        malformed = Path(temporary) / "malformed.wav"
        malformed.write_bytes(b"RIFF\x00\x00\x00\x00WAVEbroken")
        failures.append(
            assert_expected_failure(
                lambda: _runtime().synth_sample_duration(str(malformed)),
                tokens=("decode", "wav", "sample"),
            )
        )
    return failures, len(serialized)


def _longevity_case(sample_rate: int, cycles: int) -> tuple[dict[str, object], int]:
    from gummysnake import synth as sy

    plan_digests: set[str] = set()
    pcm_digests: set[str] = set()
    total_bytes = 0
    file_cycles = 0
    blocks_before = _allocated_blocks()
    sy.reset_synth_diagnostics()
    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-longevity-") as temporary:
        root = Path(temporary)
        file_interval = max(1, cycles // 6)
        for cycle in range(cycles):
            track = _voice_track(
                "sine",
                opts={"attack": 0.001, "sustain": 0.015, "release": 0.008, "amp": 0.2},
                fx_name="lpf",
                fx_opts={"cutoff": 90, "mix": 0.7},
            )
            plan = track.physical_plan(duration=0.04)
            plan_bytes = plan.to_bytes()
            plan_digests.add(semantic_plan_digest(plan.to_dict()))
            if cycle % file_interval == 0:
                output = root / f"cycle-{cycle}.wav"
                track.save(output, duration=0.04, sample_rate=sample_rate)
                payload = output.read_bytes()
                output.unlink()
                file_cycles += 1
            else:
                payload = plan.render(sample_rate=sample_rate)
            assert_wav_contract(payload, sample_rate=sample_rate)
            pcm_digests.add("sha256:" + sha256(payload).hexdigest())
            total_bytes += len(payload) + len(plan_bytes)
        if tuple(root.iterdir()):
            raise SynthOracleError("bounded longevity left output files behind")
    blocks_after = _allocated_blocks()
    if len(plan_digests) != 1 or len(pcm_digests) != 1:
        raise SynthOracleError(
            "bounded longevity cycles changed deterministic plan or PCM identity"
        )
    runtime_diagnostics = dict(sy.synth_diagnostics())
    if _metric_int(runtime_diagnostics, "gil_released_render_calls") < cycles:
        raise SynthOracleError("bounded longevity omitted public render diagnostics")
    allocation_delta = (
        _availability(
            blocks_after - blocks_before,
            source="sys.getallocatedblocks-bounded-longevity-boundary-net-delta",
        )
        if blocks_before is not None and blocks_after is not None
        else _availability(
            None,
            source=None,
            reason="sys.getallocatedblocks is unavailable on this Python implementation",
        )
    )
    return (
        {
            "cycles": cycles,
            "file_sink_cycles": file_cycles,
            "memory_sink_cycles": cycles - file_cycles,
            "plan_digest": next(iter(plan_digests)),
            "pcm_digest": next(iter(pcm_digests)),
            "total_materialized_bytes": total_bytes,
            "python_allocated_blocks_net_delta": allocation_delta,
            "runtime_diagnostics": runtime_diagnostics,
            "temporary_files_removed": not root.exists(),
            "resource_boundary": (
                "fresh public Track/plan and one returned or file WAV per cycle; Rust DSP "
                "workspace is block-bounded but per-session byte counters are not exposed"
            ),
            "unavailable_resource_counters": {
                "available": False,
                "reason": (
                    "compiled-program, template, sample-cache, FX scratch, queue, handle, thread, "
                    "and current-RSS counters are not exposed by public Synth diagnostics"
                ),
            },
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
            "stateful-wav-memory-and-streaming-file-output",
            "worker-resource-boundary",
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
