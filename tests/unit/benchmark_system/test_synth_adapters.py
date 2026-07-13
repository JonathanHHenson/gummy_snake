from __future__ import annotations

import pytest

from benchmarks.suites.synth.adapters import (
    CallableSynthAdapter,
    SynthAdapterError,
    merge_lifecycle_diagnostics,
    run_adapter,
)


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
