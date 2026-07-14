"""Lifecycle, route, instrumentation, and qualification adapters for Synth benchmarks.

The adapters in this module only call production Synth entry points. They do not
implement DSP, decode audio, emulate an SDL device, or turn an unavailable route
into a successful benchmark. Every route uses the same
prepare → warm → timed → synchronize → validate → teardown lifecycle.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Literal, cast


class SynthAdapterError(RuntimeError):
    """A benchmark route is invalid, unavailable, stale, or leaked resources."""


@dataclass(frozen=True, slots=True)
class Distribution:
    """An exact integer-sample distribution with deterministic nearest-rank quantiles."""

    count: int
    minimum: int | None
    p50: int | None
    p95: int | None
    p99: int | None
    maximum: int | None
    total: int

    @classmethod
    def from_samples(cls, samples: Sequence[int]) -> Distribution:
        values = sorted(samples)
        if not values:
            return cls(0, None, None, None, None, None, 0)

        def percentile(percent: int) -> int:
            index = max(0, (percent * len(values) + 99) // 100 - 1)
            return values[min(index, len(values) - 1)]

        return cls(
            len(values),
            values[0],
            percentile(50),
            percentile(95),
            percentile(99),
            values[-1],
            sum(values),
        )

    def as_dict(self) -> dict[str, int | None]:
        return {
            "count": self.count,
            "minimum": self.minimum,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "maximum": self.maximum,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class AvailableMetric:
    """A truthful metric value or an explicit unavailable result."""

    available: bool
    value: int | float | str | None
    source: str | None
    reason: str | None = None

    @classmethod
    def unavailable(cls, reason: str) -> AvailableMetric:
        return cls(False, None, None, reason)

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "value": self.value,
            "source": self.source,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ProcessSnapshot:
    """Low-overhead process counters available without starting an allocation tracer."""

    allocated_blocks: int | None
    peak_rss_bytes: int | None


def _process_snapshot() -> ProcessSnapshot:
    getallocatedblocks = cast(Callable[[], int] | None, getattr(sys, "getallocatedblocks", None))
    allocated_blocks = getallocatedblocks() if getallocatedblocks is not None else None
    try:
        import resource

        raw_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # macOS reports bytes; Linux and the BSDs used by CI report KiB.
        peak_rss_bytes = raw_rss if sys.platform == "darwin" else raw_rss * 1024
    except (ImportError, OSError, ValueError):
        peak_rss_bytes = None
    return ProcessSnapshot(allocated_blocks, peak_rss_bytes)


def _delta_metric(
    before: int | None,
    after: int | None,
    *,
    source: str,
    unavailable_reason: str,
) -> AvailableMetric:
    if before is None or after is None:
        return AvailableMetric.unavailable(unavailable_reason)
    return AvailableMetric(True, after - before, source)


@dataclass(frozen=True, slots=True)
class PhaseMeasurements:
    """Monotonic timings for the mandatory shared benchmark lifecycle."""

    prepare_ns: int
    warm_ns: int
    timed_ns: int
    synchronize_ns: int
    validate_ns: int
    teardown_ns: int

    def as_dict(self) -> dict[str, int]:
        return {
            "prepare_ns": self.prepare_ns,
            "warm_ns": self.warm_ns,
            "timed_ns": self.timed_ns,
            "synchronize_ns": self.synchronize_ns,
            "validate_ns": self.validate_ns,
            "teardown_ns": self.teardown_ns,
        }

    def distribution(self) -> Distribution:
        return Distribution.from_samples(tuple(self.as_dict().values()))


@dataclass(frozen=True, slots=True)
class AdapterIdentity:
    """Stable route and cache-state identity for a measured operation."""

    route: str
    cache_state: Literal["cold", "warm", "not-applicable"]
    work_units: int
    work_unit: str

    def __post_init__(self) -> None:
        if not self.route or self.work_units <= 0 or not self.work_unit:
            raise SynthAdapterError("adapter identity requires a route and positive work units")

    def as_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "cache_state": self.cache_state,
            "work_units": self.work_units,
            "work_unit": self.work_unit,
        }


@dataclass(frozen=True, slots=True)
class DeviceQualification:
    """Privacy-safe physical-device evidence; unavailable fields remain false/None."""

    requested: bool = False
    available: bool = False
    qualified: bool = False
    backend: str | None = None
    negotiated_format: str | None = None
    negotiated_sample_rate: int | None = None
    negotiated_channels: int | None = None
    queue_low_frames: int | None = None
    queue_high_frames: int | None = None
    underruns: int | None = None
    errors: tuple[str, ...] = ()
    stopped: bool = False
    reopened: bool = False
    pre_device_pcm_digest: str | None = None
    unavailable_reason: str | None = "physical audio was not requested"

    def __post_init__(self) -> None:
        if self.qualified:
            required = (
                self.requested,
                self.available,
                self.backend is not None,
                self.negotiated_format is not None,
                self.negotiated_sample_rate is not None,
                self.negotiated_channels is not None,
                self.queue_low_frames is not None,
                self.queue_high_frames is not None,
                self.underruns is not None,
                self.stopped,
                self.reopened,
                self.pre_device_pcm_digest is not None,
            )
            if not all(required) or self.errors or self.unavailable_reason is not None:
                raise SynthAdapterError(
                    "qualified physical audio requires complete negotiated, queue, stop, and "
                    "reopen evidence"
                )

    @classmethod
    def unavailable(cls, *, requested: bool, reason: str) -> DeviceQualification:
        return cls(requested=requested, unavailable_reason=reason)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "requested": self.requested,
            "available": self.available,
            "qualified": self.qualified,
            "backend": self.backend,
            "negotiated_format": self.negotiated_format,
            "negotiated_sample_rate": self.negotiated_sample_rate,
            "negotiated_channels": self.negotiated_channels,
            "queue_low_frames": self.queue_low_frames,
            "queue_high_frames": self.queue_high_frames,
            "underruns": self.underruns,
            "errors": list(self.errors),
            "stopped": self.stopped,
            "reopened": self.reopened,
            "pre_device_pcm_digest": self.pre_device_pcm_digest,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True, slots=True)
class AdapterInstrumentation:
    """Measurements captured around, but not injected into, the timed callback."""

    process_allocated_blocks_delta: AvailableMetric
    timed_allocated_blocks_delta: AvailableMetric
    process_peak_rss_delta_bytes: AvailableMetric
    timed_peak_rss_delta_bytes: AvailableMetric
    output_bytes: AvailableMetric
    cache: Mapping[str, AvailableMetric]
    block_time_ns: Distribution

    def as_dict(self) -> dict[str, object]:
        return {
            "process_allocated_blocks_delta": self.process_allocated_blocks_delta.as_dict(),
            "timed_allocated_blocks_delta": self.timed_allocated_blocks_delta.as_dict(),
            "process_peak_rss_delta_bytes": self.process_peak_rss_delta_bytes.as_dict(),
            "timed_peak_rss_delta_bytes": self.timed_peak_rss_delta_bytes.as_dict(),
            "output_bytes": self.output_bytes.as_dict(),
            "cache": {key: value.as_dict() for key, value in sorted(self.cache.items())},
            "block_time_ns": self.block_time_ns.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class AdapterRun[OutputT]:
    """Validated output and measurements from one complete adapter lifecycle."""

    output: OutputT
    phases: PhaseMeasurements
    identity: AdapterIdentity
    instrumentation: AdapterInstrumentation
    native_provenance: Mapping[str, object]
    device_qualification: DeviceQualification

    def diagnostics(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "identity": self.identity.as_dict(),
            "lifecycle": self.phases.as_dict(),
            "phase_time_ns": self.phases.distribution().as_dict(),
            "instrumentation": self.instrumentation.as_dict(),
            "native_provenance": dict(self.native_provenance),
            "device_qualification": self.device_qualification.as_dict(),
        }


@dataclass(slots=True)
class CallableSynthAdapter[ContextT, OutputT]:
    """Callbacks and metadata for one production Synth route."""

    prepare: Callable[[], ContextT]
    warm: Callable[[ContextT], None]
    timed: Callable[[ContextT], OutputT]
    synchronize: Callable[[ContextT, OutputT], None]
    validate: Callable[[ContextT, OutputT], None]
    teardown: Callable[[ContextT], None]
    identity: AdapterIdentity = field(
        default_factory=lambda: AdapterIdentity("custom", "not-applicable", 1, "operation")
    )
    output_size: Callable[[ContextT, OutputT], int | None] | None = None
    cache_metrics: Callable[[ContextT, OutputT], Mapping[str, AvailableMetric]] | None = None
    block_times: Callable[[ContextT, OutputT], Sequence[int]] | None = None
    provenance: Callable[[], Mapping[str, object]] | None = None
    device_qualification: Callable[[ContextT, OutputT], DeviceQualification] | None = None


def _measure[OutputT](action: Callable[[], OutputT]) -> tuple[OutputT, int]:
    started = perf_counter_ns()
    output = action()
    elapsed = perf_counter_ns() - started
    if elapsed < 0:
        raise SynthAdapterError("monotonic benchmark clock regressed")
    return output, elapsed


def _output_bytes[ContextT, OutputT](
    adapter: CallableSynthAdapter[ContextT, OutputT], context: ContextT, output: OutputT
) -> AvailableMetric:
    if adapter.output_size is not None:
        value = adapter.output_size(context, output)
        if value is None:
            return AvailableMetric.unavailable("adapter route does not expose output byte size")
        if value < 0:
            raise SynthAdapterError("adapter output byte size cannot be negative")
        return AvailableMetric(True, value, "adapter-exact-byte-count")
    if isinstance(output, bytes | bytearray | memoryview):
        return AvailableMetric(True, len(output), "python-buffer-length")
    return AvailableMetric.unavailable("output is not a byte buffer and no exact size probe exists")


def run_adapter[ContextT, OutputT](
    adapter: CallableSynthAdapter[ContextT, OutputT],
) -> AdapterRun[OutputT]:
    """Run the mandatory lifecycle exactly once and always tear down prepared state."""

    process_before = _process_snapshot()
    context, prepare_ns = _measure(adapter.prepare)
    warm_ns = timed_ns = synchronize_ns = validate_ns = teardown_ns = 0
    active_error: BaseException | None = None
    timed_before = ProcessSnapshot(None, None)
    timed_after = ProcessSnapshot(None, None)
    try:
        _, warm_ns = _measure(lambda: adapter.warm(context))
        timed_before = _process_snapshot()
        output, timed_ns = _measure(lambda: adapter.timed(context))
        timed_after = _process_snapshot()
        _, synchronize_ns = _measure(lambda: adapter.synchronize(context, output))
        _, validate_ns = _measure(lambda: adapter.validate(context, output))
        output_bytes = _output_bytes(adapter, context, output)
        cache = (
            dict(adapter.cache_metrics(context, output))
            if adapter.cache_metrics is not None
            else {
                "bytes": AvailableMetric.unavailable(
                    "production route exposes no public cache byte counter"
                ),
                "hits": AvailableMetric.unavailable(
                    "production route exposes no public cache hit counter"
                ),
                "misses": AvailableMetric.unavailable(
                    "production route exposes no public cache miss counter"
                ),
            }
        )
        block_times = tuple(adapter.block_times(context, output)) if adapter.block_times else ()
        qualification = (
            adapter.device_qualification(context, output)
            if adapter.device_qualification is not None
            else DeviceQualification.unavailable(
                requested=False, reason="adapter does not open a physical audio device"
            )
        )
    except BaseException as error:
        active_error = error
        raise
    finally:
        try:
            _, teardown_ns = _measure(lambda: adapter.teardown(context))
        except BaseException:
            if active_error is None:
                raise
    process_after = _process_snapshot()
    provenance = (
        dict(adapter.provenance())
        if adapter.provenance is not None
        else {
            "available": False,
            "reason": "adapter has no native runtime",
        }
    )
    return AdapterRun(
        output=output,
        phases=PhaseMeasurements(
            prepare_ns=prepare_ns,
            warm_ns=warm_ns,
            timed_ns=timed_ns,
            synchronize_ns=synchronize_ns,
            validate_ns=validate_ns,
            teardown_ns=teardown_ns,
        ),
        identity=adapter.identity,
        instrumentation=AdapterInstrumentation(
            process_allocated_blocks_delta=_delta_metric(
                process_before.allocated_blocks,
                process_after.allocated_blocks,
                source="sys.getallocatedblocks-process-boundary",
                unavailable_reason="sys.getallocatedblocks is unavailable",
            ),
            timed_allocated_blocks_delta=_delta_metric(
                timed_before.allocated_blocks,
                timed_after.allocated_blocks,
                source="sys.getallocatedblocks-timed-boundary",
                unavailable_reason="sys.getallocatedblocks is unavailable",
            ),
            process_peak_rss_delta_bytes=_delta_metric(
                process_before.peak_rss_bytes,
                process_after.peak_rss_bytes,
                source="resource.getrusage-ru_maxrss-process-boundary",
                unavailable_reason="peak RSS is unavailable on this platform",
            ),
            timed_peak_rss_delta_bytes=_delta_metric(
                timed_before.peak_rss_bytes,
                timed_after.peak_rss_bytes,
                source="resource.getrusage-ru_maxrss-timed-boundary",
                unavailable_reason="peak RSS is unavailable on this platform",
            ),
            output_bytes=output_bytes,
            cache=cache,
            block_time_ns=Distribution.from_samples(block_times),
        ),
        native_provenance=provenance,
        device_qualification=qualification,
    )


def runtime_provenance(runtime: Any) -> dict[str, object]:
    """Read and validate native Synth/Canvas provenance, rejecting known stale builds."""

    probe = getattr(runtime, "benchmark_provenance", None)
    if not callable(probe):
        raise SynthAdapterError(
            "Synth benchmark runtime lacks benchmark_provenance(); rebuild the Canvas extension"
        )
    raw = probe()
    if not isinstance(raw, Mapping):
        raise SynthAdapterError("native benchmark provenance must be a mapping")
    required = {
        "source_commit",
        "source_digest",
        "tree_digest",
        "profile",
        "features",
        "canvas_crate_version",
        "synth_crate_version",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise SynthAdapterError(
            "native benchmark provenance is malformed; missing " + ", ".join(missing)
        )
    expected_digest = os.environ.get("GUMMY_BENCHMARK_SOURCE_DIGEST")
    reported_digest = raw["source_digest"]
    if expected_digest and reported_digest != expected_digest:
        raise SynthAdapterError(
            "stale Canvas/Synth extension: native source digest does not match the benchmark "
            "snapshot; rebuild the release wheel"
        )
    profile = raw["profile"]
    return {
        "available": True,
        "source_commit": raw["source_commit"],
        "source_digest": reported_digest,
        "tree_digest": raw["tree_digest"],
        "profile": profile,
        "features": list(raw["features"]) if isinstance(raw["features"], list | tuple) else [],
        "canvas_crate_version": raw["canvas_crate_version"],
        "synth_crate_version": raw["synth_crate_version"],
        "comparable_release": profile == "release" and reported_digest != "unrecorded",
    }


def _wav_validator(payload: bytes, sample_rate: int) -> None:
    from .oracles import assert_wav_contract

    assert_wav_contract(payload, sample_rate=sample_rate)


def direct_rust_adapter(
    runtime: Any,
    *,
    event_payloads: Sequence[Mapping[str, object]],
    duration_seconds: float,
    sample_rate: int,
) -> CallableSynthAdapter[dict[str, object], bytes]:
    """Build a cold direct typed-PyO3 → gummy_synth render adapter."""

    events = [dict(event) for event in event_payloads]

    def prepare() -> dict[str, object]:
        return {"events": events, "duration": duration_seconds, "sample_rate": sample_rate}

    return CallableSynthAdapter(
        prepare=prepare,
        warm=lambda _context: runtime.synth_reset_diagnostics(),
        timed=lambda context: bytes(
            runtime.synth_render_plan_wav(
                context["events"], context["duration"], context["sample_rate"]
            )
        ),
        synchronize=lambda _context, _output: None,
        validate=lambda _context, output: _wav_validator(output, sample_rate),
        teardown=lambda context: context.clear(),
        identity=AdapterIdentity("direct-pyo3-typed-rust-render", "cold", len(events), "event"),
        provenance=lambda: runtime_provenance(runtime),
    )


def serialized_bridge_adapter(
    runtime: Any,
    *,
    serialized_plan: bytes,
    sample_rate: int,
    event_count: int,
) -> CallableSynthAdapter[dict[str, object], bytes]:
    """Build a cold serialized-PyO3 compile-and-render adapter."""

    def prepare() -> dict[str, object]:
        return {"payload": bytes(serialized_plan), "sample_rate": sample_rate}

    return CallableSynthAdapter(
        prepare=prepare,
        warm=lambda _context: runtime.synth_reset_diagnostics(),
        timed=lambda context: bytes(
            runtime.synth_render_serialized_plan_wav(context["payload"], context["sample_rate"])
        ),
        synchronize=lambda _context, _output: None,
        validate=lambda _context, output: _wav_validator(output, sample_rate),
        teardown=lambda context: context.clear(),
        identity=AdapterIdentity(
            "serialized-pyo3-compile-rust-render", "cold", event_count, "event"
        ),
        provenance=lambda: runtime_provenance(runtime),
    )


def compiled_rust_adapter(
    runtime: Any,
    *,
    serialized_plan: bytes,
    sample_rate: int,
    event_count: int,
) -> CallableSynthAdapter[dict[str, Any], bytes]:
    """Build a warm compiled-program → direct gummy_synth render adapter."""

    def prepare() -> dict[str, Any]:
        return {"payload": bytes(serialized_plan), "sample_rate": sample_rate}

    def warm(context: dict[str, Any]) -> None:
        context["program"] = runtime.CanvasSynthProgram.from_serialized(
            context["payload"], context["sample_rate"]
        )
        runtime.synth_reset_diagnostics()

    return CallableSynthAdapter(
        prepare=prepare,
        warm=warm,
        timed=lambda context: bytes(context["program"].render_wav()),
        synchronize=lambda _context, _output: None,
        validate=lambda _context, output: _wav_validator(output, sample_rate),
        teardown=lambda context: context.clear(),
        identity=AdapterIdentity("compiled-rust-program-render", "warm", event_count, "event"),
        provenance=lambda: runtime_provenance(runtime),
    )


@dataclass(frozen=True, slots=True)
class OfflineFileOutput:
    payload: bytes
    path: Path


def offline_file_adapter(
    runtime: Any,
    *,
    serialized_plan: bytes,
    sample_rate: int,
    event_count: int,
) -> CallableSynthAdapter[dict[str, Any], OfflineFileOutput]:
    """Build a compiled Rust render-to-temporary-file sink adapter."""

    def prepare() -> dict[str, Any]:
        temporary = tempfile.TemporaryDirectory(prefix="gummysnake-synth-bench-output-")
        return {
            "temporary": temporary,
            "path": Path(temporary.name) / "render.wav",
            "payload": bytes(serialized_plan),
        }

    def warm(context: dict[str, Any]) -> None:
        context["program"] = runtime.CanvasSynthProgram.from_serialized(
            context["payload"], sample_rate
        )
        runtime.synth_reset_diagnostics()

    def timed(context: dict[str, Any]) -> OfflineFileOutput:
        path = context["path"]
        payload = bytes(context["program"].render_wav_file(str(path)))
        return OfflineFileOutput(payload, path)

    def validate(_context: dict[str, Any], output: OfflineFileOutput) -> None:
        _wav_validator(output.payload, sample_rate)
        if output.path.read_bytes() != output.payload:
            raise SynthAdapterError("offline file sink bytes differ from returned WAV bytes")

    def teardown(context: dict[str, Any]) -> None:
        temporary = context["temporary"]
        temporary.cleanup()
        if context["path"].exists():
            raise SynthAdapterError("offline file sink leaked its temporary output")
        context.clear()

    return CallableSynthAdapter(
        prepare=prepare,
        warm=warm,
        timed=timed,
        synchronize=lambda _context, _output: None,
        validate=validate,
        teardown=teardown,
        identity=AdapterIdentity("compiled-rust-wav-file-sink", "warm", event_count, "event"),
        output_size=lambda _context, output: len(output.payload),
        provenance=lambda: runtime_provenance(runtime),
    )


@dataclass(frozen=True, slots=True)
class SimulatedRealtimeOutput:
    """Deterministic virtual-clock sink result over pre-rendered production PCM."""

    pcm: bytes
    blocks: tuple[bytes, ...]
    block_time_ns: tuple[int, ...]
    block_frames: tuple[int, ...]
    queue_low_frames: int
    queue_high_frames: int
    underruns: int
    deadline_misses: int


def simulated_realtime_adapter(
    wav_payload: bytes,
    *,
    block_frames: int,
) -> CallableSynthAdapter[dict[str, Any], SimulatedRealtimeOutput]:
    """Build a deterministic no-sleep PCM block sink; it is not device evidence."""

    if block_frames <= 0:
        raise SynthAdapterError("simulated realtime block_frames must be positive")
    from .oracles import decode_pcm_wav

    identity_pcm = decode_pcm_wav(wav_payload)
    block_count = max(1, (identity_pcm.frames + block_frames - 1) // block_frames)

    def prepare() -> dict[str, Any]:
        from .oracles import pcm_data

        pcm = identity_pcm
        bytes_per_frame = pcm.channels * pcm.sample_width
        return {
            "pcm": pcm_data(wav_payload),
            "bytes_per_frame": bytes_per_frame,
            "block_bytes": block_frames * bytes_per_frame,
        }

    def warm(context: dict[str, Any]) -> None:
        pcm = context["pcm"]
        block_bytes = context["block_bytes"]
        context["blocks"] = tuple(
            pcm[offset : offset + block_bytes] for offset in range(0, len(pcm), block_bytes)
        )

    def timed(context: dict[str, Any]) -> SimulatedRealtimeOutput:
        queue_frames = 0
        low_water = 0
        high_water = 0
        timings: list[int] = []
        frame_counts: list[int] = []
        consumed: list[bytes] = []
        bytes_per_frame = context["bytes_per_frame"]
        for block in context["blocks"]:
            started = perf_counter_ns()
            frames = len(block) // bytes_per_frame
            queue_frames += frames
            high_water = max(high_water, queue_frames)
            consumed.append(block)
            queue_frames -= frames
            low_water = min(low_water, queue_frames)
            frame_counts.append(frames)
            timings.append(perf_counter_ns() - started)
        return SimulatedRealtimeOutput(
            b"".join(consumed),
            tuple(context["blocks"]),
            tuple(timings),
            tuple(frame_counts),
            low_water,
            high_water,
            0,
            0,
        )

    def validate(context: dict[str, Any], output: SimulatedRealtimeOutput) -> None:
        if output.pcm != context["pcm"]:
            raise SynthAdapterError("simulated realtime sink changed PCM bytes")
        if output.underruns or output.deadline_misses:
            raise SynthAdapterError(
                "deterministic simulated sink reported an underrun or deadline miss"
            )
        if any(frames <= 0 or frames > block_frames for frames in output.block_frames):
            raise SynthAdapterError("simulated realtime sink emitted an invalid block size")

    return CallableSynthAdapter(
        prepare=prepare,
        warm=warm,
        timed=timed,
        synchronize=lambda _context, _output: None,
        validate=validate,
        teardown=lambda context: context.clear(),
        identity=AdapterIdentity(
            "deterministic-simulated-realtime-pcm-sink",
            "not-applicable",
            block_count,
            "pcm-block",
        ),
        output_size=lambda _context, output: len(output.pcm),
        block_times=lambda _context, output: output.block_time_ns,
    )


def physical_sdl_adapter(
    runtime: Any,
    *,
    pre_device_wav: bytes,
    allow_physical_device: bool = False,
) -> CallableSynthAdapter[None, object]:
    """Return the physical SDL route, failing closed until full device evidence exists.

    The current runtime can open and stop SDL playback, but it cannot report the
    negotiated format/rate/channels, queue watermarks, underruns, or reopen result
    required for benchmark qualification. Opening it would produce sound without
    sufficient evidence, so this adapter rejects the route before device access.
    """

    del runtime, pre_device_wav

    def prepare() -> None:
        if not allow_physical_device:
            raise SynthAdapterError(
                "physical SDL audio benchmark requires explicit allow_physical_device=True; "
                "no offline or simulated route will be substituted"
            )
        raise SynthAdapterError(
            "physical SDL audio benchmark is unavailable: the Canvas runtime does not expose "
            "negotiated format/rate/channels, queue watermarks, underruns, and stop/reopen "
            "diagnostics. No audio qualification was recorded."
        )

    return CallableSynthAdapter(
        prepare=prepare,
        warm=lambda _context: None,
        timed=lambda _context: object(),
        synchronize=lambda _context, _output: None,
        validate=lambda _context, _output: None,
        teardown=lambda _context: None,
        identity=AdapterIdentity("physical-sdl3-audio-device", "cold", 1, "device-cycle"),
        device_qualification=lambda _context, _output: DeviceQualification.unavailable(
            requested=True,
            reason="current runtime lacks mandatory physical-device observability",
        ),
    )


def merge_lifecycle_diagnostics[OutputT](
    diagnostics: Mapping[str, object], run: AdapterRun[OutputT]
) -> dict[str, object]:
    """Attach one lifecycle payload without overwriting production diagnostics."""

    result = dict(diagnostics)
    if "benchmark_lifecycle" in result:
        raise SynthAdapterError("benchmark diagnostics already contain benchmark_lifecycle")
    result["benchmark_lifecycle"] = run.diagnostics()
    return result


__all__ = [
    "AdapterIdentity",
    "AdapterInstrumentation",
    "AdapterRun",
    "AvailableMetric",
    "CallableSynthAdapter",
    "DeviceQualification",
    "Distribution",
    "OfflineFileOutput",
    "PhaseMeasurements",
    "SimulatedRealtimeOutput",
    "SynthAdapterError",
    "compiled_rust_adapter",
    "direct_rust_adapter",
    "merge_lifecycle_diagnostics",
    "offline_file_adapter",
    "physical_sdl_adapter",
    "run_adapter",
    "runtime_provenance",
    "serialized_bridge_adapter",
    "simulated_realtime_adapter",
]
