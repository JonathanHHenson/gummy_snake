from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.suites.synth.adapters import (
    AdapterIdentity,
    CallableSynthAdapter,
    DeviceQualification,
    SynthAdapterError,
    compiled_rust_adapter,
    direct_rust_adapter,
    merge_lifecycle_diagnostics,
    offline_file_adapter,
    physical_sdl_adapter,
    run_adapter,
    runtime_provenance,
    serialized_bridge_adapter,
    simulated_realtime_adapter,
)
from benchmarks.suites.synth.fixtures import generate_signal, pcm_wav_bytes
from benchmarks.suites.synth.oracles import assert_lifecycle_contract, pcm_data


def test_callable_adapter_runs_every_phase_once_and_separates_timed_work() -> None:
    calls: list[str] = []

    adapter = CallableSynthAdapter(
        prepare=lambda: calls.append("prepare") or {"warmed": False},
        warm=lambda context: (calls.append("warm"), context.__setitem__("warmed", True))[0],
        timed=lambda context: calls.append("timed") or int(context["warmed"]),
        synchronize=lambda _context, _output: calls.append("synchronize"),
        validate=lambda _context, output: calls.append("validate") if output == 1 else None,
        teardown=lambda _context: calls.append("teardown"),
    )

    run = run_adapter(adapter)

    assert run.output == 1
    assert calls == ["prepare", "warm", "timed", "synchronize", "validate", "teardown"]
    lifecycle = run.diagnostics()["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert set(lifecycle) == {
        "prepare_ns",
        "warm_ns",
        "timed_ns",
        "synchronize_ns",
        "validate_ns",
        "teardown_ns",
    }
    assert all(isinstance(value, int) and value >= 0 for value in lifecycle.values())
    assert run.identity == AdapterIdentity("custom", "not-applicable", 1, "operation")
    diagnostics = run.diagnostics()
    assert diagnostics["schema_version"] == 2
    assert_lifecycle_contract(diagnostics, expected_route="custom")
    instrumentation = diagnostics["instrumentation"]
    assert isinstance(instrumentation, dict)
    output_bytes = instrumentation["output_bytes"]
    cache = instrumentation["cache"]
    device = diagnostics["device_qualification"]
    assert isinstance(output_bytes, dict)
    assert isinstance(cache, dict)
    assert isinstance(cache["bytes"], dict)
    assert isinstance(device, dict)
    assert output_bytes["available"] is False
    assert cache["bytes"]["available"] is False
    assert device["qualified"] is False


def test_callable_adapter_tears_down_after_validation_failure_without_replacing_error() -> None:
    calls: list[str] = []

    adapter = CallableSynthAdapter(
        prepare=lambda: calls.append("prepare") or object(),
        warm=lambda _context: calls.append("warm"),
        timed=lambda _context: calls.append("timed") or b"pcm",
        synchronize=lambda _context, _output: calls.append("synchronize"),
        validate=lambda _context, _output: (_ for _ in ()).throw(ValueError("bad pcm")),
        teardown=lambda _context: calls.append("teardown"),
    )

    with pytest.raises(ValueError, match="bad pcm"):
        run_adapter(adapter)

    assert calls == ["prepare", "warm", "timed", "synchronize", "teardown"]


def test_lifecycle_diagnostics_cannot_silently_replace_a_prior_lifecycle_record() -> None:
    adapter = CallableSynthAdapter(
        prepare=lambda: None,
        warm=lambda _context: None,
        timed=lambda _context: b"pcm",
        synchronize=lambda _context, _output: None,
        validate=lambda _context, _output: None,
        teardown=lambda _context: None,
    )
    run = run_adapter(adapter)

    merged = merge_lifecycle_diagnostics({"route": "headless"}, run)
    assert merged["route"] == "headless"
    assert "benchmark_lifecycle" in merged
    with pytest.raises(SynthAdapterError, match="already contain"):
        merge_lifecycle_diagnostics(merged, run)


class _FakeProgram:
    payload = b""

    @classmethod
    def from_serialized(cls, _payload: bytes, _sample_rate: int) -> _FakeProgram:
        return cls()

    def render_wav(self) -> bytes:
        return self.payload

    def render_wav_file(self, path: str) -> bytes:
        Path(path).write_bytes(self.payload)
        return self.payload


class _FakeRuntime:
    CanvasSynthProgram = _FakeProgram

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        _FakeProgram.payload = payload
        self.reset_calls = 0

    def synth_reset_diagnostics(self) -> None:
        self.reset_calls += 1

    def synth_render_plan_wav(
        self, _events: object, _duration: object, _sample_rate: object
    ) -> bytes:
        return self.payload

    def synth_render_serialized_plan_wav(self, _payload: object, _sample_rate: object) -> bytes:
        return self.payload

    def benchmark_provenance(self) -> dict[str, object]:
        return {
            "source_commit": "abc123",
            "source_digest": "sha256:fixture",
            "tree_digest": "sha256:tree",
            "profile": "release",
            "features": ["extension-module"],
            "canvas_crate_version": "1.0.0",
            "synth_crate_version": "1.0.0",
        }


def test_direct_serialized_compiled_and_file_routes_are_explicit_and_clean() -> None:
    payload = pcm_wav_bytes(generate_signal("sine", sample_rate=8_000, duration_seconds=0.02))
    runtime = _FakeRuntime(payload)
    routes = (
        run_adapter(
            direct_rust_adapter(
                runtime,
                event_payloads=({"kind": "play"},),
                duration_seconds=0.02,
                sample_rate=8_000,
            )
        ),
        run_adapter(
            serialized_bridge_adapter(
                runtime, serialized_plan=b"plan", sample_rate=8_000, event_count=1
            )
        ),
        run_adapter(
            compiled_rust_adapter(
                runtime, serialized_plan=b"plan", sample_rate=8_000, event_count=1
            )
        ),
        run_adapter(
            offline_file_adapter(runtime, serialized_plan=b"plan", sample_rate=8_000, event_count=1)
        ),
    )

    assert [run.identity.route for run in routes] == [
        "direct-pyo3-typed-rust-render",
        "serialized-pyo3-compile-rust-render",
        "compiled-rust-program-render",
        "compiled-rust-wav-file-sink",
    ]
    assert [run.identity.cache_state for run in routes] == ["cold", "cold", "warm", "warm"]
    assert routes[0].output == routes[1].output == routes[2].output == payload
    file_output = routes[3].output
    assert file_output.payload == payload
    assert not file_output.path.exists()
    for run in routes:
        assert run.native_provenance["comparable_release"] is True
        assert_lifecycle_contract(run.diagnostics(), expected_route=run.identity.route)


def test_simulated_realtime_route_preserves_pcm_and_reports_block_distributions() -> None:
    payload = pcm_wav_bytes(
        generate_signal("asymmetric-stereo", sample_rate=8_000, duration_seconds=0.021)
    )

    run = run_adapter(simulated_realtime_adapter(payload, block_frames=64))

    output = run.output
    assert output.pcm == pcm_data(payload)
    assert b"".join(output.blocks) == output.pcm
    assert sum(output.block_frames) == 168
    assert max(output.block_frames) == 64
    assert output.underruns == output.deadline_misses == 0
    distribution = run.instrumentation.block_time_ns
    assert distribution.count == len(output.blocks) == 3
    assert distribution.maximum is not None and distribution.maximum >= 0
    assert run.device_qualification.qualified is False


def test_physical_sdl_route_fails_before_device_access_and_never_qualifies() -> None:
    payload = pcm_wav_bytes(generate_signal("sine"))
    runtime = object()

    with pytest.raises(SynthAdapterError, match="explicit allow_physical_device"):
        run_adapter(physical_sdl_adapter(runtime, pre_device_wav=payload))
    with pytest.raises(SynthAdapterError, match="No audio qualification was recorded"):
        run_adapter(
            physical_sdl_adapter(runtime, pre_device_wav=payload, allow_physical_device=True)
        )

    unavailable = DeviceQualification.unavailable(requested=True, reason="no device diagnostics")
    assert unavailable.requested is True
    assert unavailable.available is unavailable.qualified is False
    assert unavailable.as_dict()["negotiated_format"] is None


def test_runtime_provenance_rejects_stale_and_malformed_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeRuntime(pcm_wav_bytes(generate_signal("sine")))
    assert runtime_provenance(runtime)["comparable_release"] is True

    monkeypatch.setenv("GUMMY_BENCHMARK_SOURCE_DIGEST", "sha256:other")
    with pytest.raises(SynthAdapterError, match="stale Canvas/Synth extension"):
        runtime_provenance(runtime)
    monkeypatch.delenv("GUMMY_BENCHMARK_SOURCE_DIGEST")

    monkeypatch.setattr(runtime, "benchmark_provenance", lambda: {"profile": "release"})
    with pytest.raises(SynthAdapterError, match="malformed"):
        runtime_provenance(runtime)
