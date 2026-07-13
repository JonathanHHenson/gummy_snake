"""Executable fail-closed JSONL worker for registered static benchmark suites."""

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
            suite_id=str(raw["suite_id"]),
            workload_id=str(raw["workload_id"]),
            seed=_integer(raw["seed"], "seed"),
            hash_seed=_integer(raw["hash_seed"], "hash_seed"),
            timeout_seconds=_integer(raw["timeout_seconds"], "timeout_seconds"),
            work_units=_integer(raw["work_units"], "work_units"),
            payload=dict(payload),
            timed_blocks=_integer(raw["timed_blocks"], "timed_blocks"),
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
    """Execute every required phase against the selected production suite."""

    phases = {phase: "not-run" for phase in PHASES}
    diagnostics: dict[str, object] = {}
    completed = 0
    elapsed_ns: int | None = None
    elapsed_blocks_ns: list[int] = []
    try:
        # Import through the static suite boundary. It validates the known suite and
        # workload set and imports Gummy Snake only when actual execution begins.
        from ..suites.registry import dispatch

        phases["prepare"] = "ok"
        require_capabilities(request.execution_class, detect_capabilities())
        phases["precondition"] = "ok"
        parameters = _parameters(request)
        for _ in range(_warmup_runs(request)):
            dispatch(request.suite_id, request.workload_id, parameters, request.execution_class)
        phases["warmup"] = "ok"

        last_run = None
        for _ in range(request.timed_blocks):
            started = perf_counter_ns()
            # Each bounded dispatcher invocation is one independent timed block.
            # The process remains alive across its declared blocks so process-level
            # variation is not confused with block-level variation.
            last_run = dispatch(
                request.suite_id,
                request.workload_id,
                parameters,
                request.execution_class,
            )
            elapsed_blocks_ns.append(perf_counter_ns() - started)
            completed += request.work_units
        elapsed_ns = sum(elapsed_blocks_ns)
        phases["timed"] = "ok"

        # `dispatch` returns only after its bounded public sketch run has completed.
        # This phase records that completion boundary without substituting a renderer sync.
        if last_run is None:
            raise WorkerError("timed phase completed no declared work")
        phases["synchronize"] = "ok"
        phases["validate"] = "ok"
        diagnostics = {
            **dict(last_run.diagnostics),
            "summary": dict(last_run.summary),
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
            tuple(elapsed_blocks_ns),
        )
    except Exception as error:
        if phases["teardown"] != "ok":
            try:
                gc.collect()
                phases["teardown"] = "ok"
            except Exception:
                phases["teardown"] = "failed"
        return WorkerResult(
            request_id=request.request_id,
            ok=False,
            phases=phases,
            elapsed_ns=elapsed_ns,
            completed_work_units=completed,
            diagnostics=diagnostics,
            elapsed_blocks_ns=tuple(elapsed_blocks_ns),
            error={"type": type(error).__name__, "message": str(error)},
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
                "elapsed_blocks_ns": list(result.elapsed_blocks_ns),
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
