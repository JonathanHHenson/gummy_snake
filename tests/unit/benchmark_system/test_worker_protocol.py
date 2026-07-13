from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.governance import AuthorityError, ExecutionClass
from benchmarks.worker import (
    CapabilitySet,
    FreshWorker,
    WorkerError,
    WorkerRequest,
    WorkerResult,
    require_capabilities,
)
from benchmarks.worker import main as worker_main
from benchmarks.worker.protocol import PHASES, PROTOCOL_VERSION


def test_capabilities_fail_closed_for_missing_native_window() -> None:
    with pytest.raises(AuthorityError, match="native_window"):
        require_capabilities(
            ExecutionClass.NATIVE_INTERACTIVE, CapabilitySet(runtime=True, gpu=True)
        )


def test_capabilities_accept_a_real_native_window_route() -> None:
    require_capabilities(
        ExecutionClass.NATIVE_INTERACTIVE,
        CapabilitySet(runtime=True, gpu=True, native_window=True),
    )


def test_fresh_worker_requires_complete_single_jsonl_result(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    worker.write_text(
        """import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({
 'protocol_version': request['protocol_version'], 'request_id': request['request_id'], 'ok': True,
 'phases': {phase: 'ok' for phase in request['phases']}, 'elapsed_ns': 10,
 'elapsed_blocks_ns': [10], 'completed_work_units': request['work_units'],
 'diagnostics': {}, 'error': None
}))
"""
    )
    request = WorkerRequest("one", ExecutionClass.HEADLESS, "fill", 1, 1, 5, 10)
    result = FreshWorker((sys.executable, str(worker))).run(request)
    assert result.elapsed_ns == 10


def test_worker_result_rejects_coerced_types_unknown_fields_and_teardown_leaks() -> None:
    base: dict[str, object] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "strict",
        "ok": True,
        "phases": {phase: "ok" for phase in PHASES},
        "elapsed_ns": 10,
        "elapsed_blocks_ns": [10],
        "completed_work_units": 1,
        "diagnostics": {},
        "error": None,
    }
    with pytest.raises(WorkerError, match="envelope fields mismatch"):
        WorkerResult.from_dict({**base, "unexpected": True})
    with pytest.raises(WorkerError, match="exact JSON types"):
        WorkerResult.from_dict({**base, "ok": 1})

    request = WorkerRequest("strict", ExecutionClass.HEADLESS, "fill", 1, 1, 5, 1)
    phases = {phase: "ok" for phase in PHASES}
    phases["teardown"] = "failed"
    result = WorkerResult(
        request_id="strict",
        ok=False,
        phases=phases,
        elapsed_ns=10,
        completed_work_units=1,
        diagnostics={},
        elapsed_blocks_ns=(10,),
        error={"type": "ResourceLeak", "message": "canvas remained live"},
    )
    with pytest.raises(WorkerError, match="resource leak"):
        result.require_complete(request)


def test_worker_request_rejects_invalid_hash_seed_and_non_json_payload() -> None:
    with pytest.raises(WorkerError, match="seeds"):
        WorkerRequest("bad", ExecutionClass.HEADLESS, "fill", 1, 2**32, 5, 1)
    request = WorkerRequest(
        "bad-json", ExecutionClass.HEADLESS, "fill", 1, 1, 5, 1, {"value": float("nan")}
    )
    with pytest.raises(WorkerError, match="strict JSON"):
        request.to_jsonl()


def test_jsonl_worker_runs_static_canvas_dispatch_and_emits_one_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from benchmarks.suites.canvas import workloads

    calls: list[tuple[str, object]] = []

    def dispatch(workload_id: str, parameters: object, execution_class: object) -> object:
        calls.append((workload_id, execution_class))
        return SimpleNamespace(
            frame_count=1,
            plan=SimpleNamespace(frames=2, expected_draw_callbacks=1),
            pixels=b"rgba",
            physical_desktop_requested=False,
            diagnostics=SimpleNamespace(counters={"gpu_primitive_batches": 1}),
        )

    request = WorkerRequest(
        "worker-success",
        ExecutionClass.HEADLESS,
        "lifecycle-hidpi",
        1,
        2,
        5,
        1,
        {"parameters": {"frames": 1}, "warmup_runs": 1},
        timed_blocks=2,
    )
    monkeypatch.setattr(workloads, "dispatch", dispatch)
    monkeypatch.setattr(
        worker_main,
        "detect_capabilities",
        lambda: CapabilitySet(runtime=True, gpu=True),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(request.to_jsonl().decode()))

    assert worker_main.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["ok"] is True
    assert set(result["phases"].values()) == {"ok"}
    assert calls == [("lifecycle-hidpi", ExecutionClass.HEADLESS)] * 3
    assert len(result["elapsed_blocks_ns"]) == 2
    assert result["completed_work_units"] == 2


def test_jsonl_worker_capability_failure_is_a_single_failed_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = WorkerRequest(
        "worker-failure",
        ExecutionClass.NATIVE_INTERACTIVE,
        "lifecycle-hidpi",
        1,
        2,
        5,
        1,
        {"parameters": {"frames": 1}},
    )
    monkeypatch.setattr(
        worker_main, "detect_capabilities", lambda: CapabilitySet(runtime=True, gpu=True)
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(request.to_jsonl().decode()))

    assert worker_main.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["ok"] is False
    assert "native_window" in result["error"]["message"]
    assert "no fallback" in result["error"]["message"]
