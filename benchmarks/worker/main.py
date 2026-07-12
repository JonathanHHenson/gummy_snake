"""Executable fail-closed JSONL worker for the static Canvas catalog."""

from __future__ import annotations

import gc
import json
import sys
from collections.abc import Mapping, Sequence
from time import perf_counter_ns

from ..governance import ExecutionClass
from .protocol import (
    PHASES,
    CapabilitySet,
    WorkerError,
    WorkerRequest,
    WorkerResult,
    require_capabilities,
)


def _request_from_mapping(raw: Mapping[str, object]) -> WorkerRequest:
    """Decode one protocol request without accepting undeclared execution routes."""

    try:
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise WorkerError("worker request payload must be an object")
        return WorkerRequest(
            request_id=str(raw["request_id"]),
            execution_class=ExecutionClass(str(raw["execution_class"])),
            workload_id=str(raw["workload_id"]),
            seed=_integer(raw["seed"], "seed"),
            hash_seed=_integer(raw["hash_seed"], "hash_seed"),
            timeout_seconds=_integer(raw["timeout_seconds"], "timeout_seconds"),
            work_units=_integer(raw["work_units"], "work_units"),
            payload=dict(payload),
            protocol_version=_integer(raw["protocol_version"], "protocol_version"),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, WorkerError):
            raise
        raise WorkerError(f"invalid worker request: {error}") from error


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerError(f"{label} must be an integer")
    return value


def detect_capabilities() -> CapabilitySet:
    """Probe the installed Canvas capabilities required for local recording.

    Native-interactive workloads require the real native window route. They are never
    rerouted to headless rendering when that route is unavailable.
    """

    try:
        from gummysnake.rust.canvas import (
            canvas_gpu_available,
            canvas_native_window_available,
            require_canvas_runtime,
        )

        require_canvas_runtime()
        gpu = canvas_gpu_available()
        native_window = canvas_native_window_available()
    except Exception:
        return CapabilitySet()
    return CapabilitySet(runtime=True, gpu=gpu, native_window=native_window)


def _parameters(request: WorkerRequest) -> Mapping[str, object]:
    raw = request.payload.get("parameters", {})
    if not isinstance(raw, Mapping):
        raise WorkerError("worker payload parameters must be an object")
    return raw


def _warmup_runs(request: WorkerRequest) -> int:
    value = request.payload.get("warmup_runs", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkerError("worker payload warmup_runs must be a non-negative integer")
    return value


def run_request(request: WorkerRequest) -> WorkerResult:
    """Execute every required phase against real public Canvas APIs exactly once per unit."""

    phases = {phase: "not-run" for phase in PHASES}
    diagnostics: dict[str, object] = {}
    completed = 0
    elapsed_ns: int | None = None
    try:
        # Import through the static suite boundary. It validates the known workload
        # set and imports Gummy Snake only when actual execution begins.
        from ..suites.canvas import dispatch

        phases["prepare"] = "ok"
        require_capabilities(request.execution_class, detect_capabilities())
        phases["precondition"] = "ok"
        parameters = _parameters(request)
        for _ in range(_warmup_runs(request)):
            dispatch(request.workload_id, parameters, request.execution_class)
        phases["warmup"] = "ok"

        last_run = None
        started = perf_counter_ns()
        # One bounded dispatcher invocation accounts for the catalog's declared
        # inner work (frames, draw records, or feature operations). Repeating it
        # here would change the workload rather than sample the same block.
        last_run = dispatch(request.workload_id, parameters, request.execution_class)
        completed = request.work_units
        elapsed_ns = perf_counter_ns() - started
        phases["timed"] = "ok"

        # `dispatch` returns only after its bounded public sketch run has completed.
        # This phase records that completion boundary without substituting a renderer sync.
        if last_run is None:
            raise WorkerError("timed phase completed no declared work")
        phases["synchronize"] = "ok"
        expected = last_run.plan.expected_draw_callbacks
        if last_run.frame_count != expected:
            actual = last_run.frame_count
            raise WorkerError(f"Canvas frame count mismatch: expected {expected}, got {actual}")
        phases["validate"] = "ok"
        diagnostics = {
            "frame_count": last_run.frame_count,
            "pixel_bytes": len(last_run.pixels),
            "physical_desktop_requested": last_run.physical_desktop_requested,
            "renderer": dict(last_run.diagnostics.counters),
        }
        phases["diagnostics"] = "ok"
        del last_run
        gc.collect()
        phases["teardown"] = "ok"
        return WorkerResult(
            request.request_id,
            True,
            phases,
            elapsed_ns,
            completed,
            diagnostics,
        )
    except Exception as error:
        if phases["teardown"] != "ok":
            try:
                gc.collect()
                phases["teardown"] = "ok"
            except Exception:
                phases["teardown"] = "failed"
        return WorkerResult(
            request.request_id,
            False,
            phases,
            elapsed_ns,
            completed,
            diagnostics,
            {"type": type(error).__name__, "message": str(error)},
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Read one JSONL request and emit exactly one JSONL result."""

    if argv:
        print("benchmark worker accepts JSONL only on standard input", file=sys.stderr)
        return 2
    lines = [line for line in sys.stdin.read().splitlines() if line]
    if len(lines) != 1:
        print("benchmark worker requires exactly one JSONL request", file=sys.stderr)
        return 2
    try:
        raw = json.loads(lines[0])
        if not isinstance(raw, Mapping):
            raise WorkerError("worker request must be an object")
        result = run_request(_request_from_mapping(raw))
    except (json.JSONDecodeError, WorkerError, ValueError) as error:
        print(f"benchmark worker: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "protocol_version": result.protocol_version,
                "request_id": result.request_id,
                "ok": result.ok,
                "phases": dict(result.phases),
                "elapsed_ns": result.elapsed_ns,
                "completed_work_units": result.completed_work_units,
                "diagnostics": dict(result.diagnostics),
                "error": None if result.error is None else dict(result.error),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution is subprocess-owned
    raise SystemExit(main())
