"""Fresh-process, versioned JSONL protocol with explicit fail-closed phases."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..governance import ExecutionClass, capability_error

PROTOCOL_VERSION = 1
PHASES = (
    "prepare",
    "precondition",
    "warmup",
    "timed",
    "synchronize",
    "validate",
    "diagnostics",
    "teardown",
)


class WorkerError(RuntimeError):
    """A worker could not be started, did not speak the protocol, or failed a phase."""


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    runtime: bool = False
    gpu: bool = False
    native_window: bool = False
    physical_desktop: bool = False
    display: bool = False
    audio: bool = False
    exclusive_machine_lock: bool = False
    native_present_submission: bool = False
    platform_present_feedback: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def require_capabilities(execution_class: ExecutionClass, capabilities: CapabilitySet) -> None:
    """Validate routes before timing and never downgrade interactive/audio requests."""

    if not capabilities.runtime:
        raise capability_error("runtime")
    required: tuple[str, ...]
    if execution_class is ExecutionClass.NATIVE_INTERACTIVE:
        required = (
            "gpu",
            "native_window",
            "physical_desktop",
            "display",
            "exclusive_machine_lock",
            "native_present_submission",
        )
    elif execution_class is ExecutionClass.NATIVE_AUDIO:
        required = ("audio",)
    elif execution_class in (ExecutionClass.HEADLESS, ExecutionClass.AUTHORITATIVE):
        required = ("gpu",)
    else:
        required = ()
    for name in required:
        if not getattr(capabilities, name):
            raise capability_error(name, f"required by {execution_class.value}")


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    request_id: str
    execution_class: ExecutionClass
    workload_id: str
    seed: int
    hash_seed: int
    timeout_seconds: int
    work_units: int
    payload: Mapping[str, object] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise WorkerError("unsupported worker request protocol version")
        if (
            not self.request_id
            or not self.workload_id
            or self.timeout_seconds <= 0
            or self.work_units <= 0
        ):
            raise WorkerError("worker request has invalid identity, timeout, or work accounting")

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "execution_class": self.execution_class.value,
            "workload_id": self.workload_id,
            "seed": self.seed,
            "hash_seed": self.hash_seed,
            "timeout_seconds": self.timeout_seconds,
            "work_units": self.work_units,
            "payload": dict(self.payload),
            "phases": list(PHASES),
        }

    def to_jsonl(self) -> bytes:
        return (json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True, slots=True)
class WorkerResult:
    request_id: str
    ok: bool
    phases: Mapping[str, str]
    elapsed_ns: int | None
    completed_work_units: int
    diagnostics: Mapping[str, object]
    error: Mapping[str, object] | None = None
    protocol_version: int = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> WorkerResult:
        try:
            version = _integer(raw["protocol_version"], "protocol_version")
            if version != PROTOCOL_VERSION:
                raise WorkerError("worker result protocol version mismatch")
            phases = raw["phases"]
            diagnostics = raw.get("diagnostics", {})
            error = raw.get("error")
            if not isinstance(phases, Mapping) or not isinstance(diagnostics, Mapping):
                raise WorkerError("worker result phases and diagnostics must be objects")
            if error is not None and not isinstance(error, Mapping):
                raise WorkerError("worker result error must be an object")
            return cls(
                request_id=str(raw["request_id"]),
                ok=bool(raw["ok"]),
                phases={str(key): str(value) for key, value in phases.items()},
                elapsed_ns=(
                    None
                    if raw.get("elapsed_ns") is None
                    else _integer(raw["elapsed_ns"], "elapsed_ns")
                ),
                completed_work_units=_integer(raw["completed_work_units"], "completed_work_units"),
                diagnostics=dict(diagnostics),
                error=None if error is None else dict(error),
                protocol_version=version,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, WorkerError):
                raise
            raise WorkerError(f"invalid worker result: {error}") from error

    def require_complete(self, request: WorkerRequest) -> None:
        if self.request_id != request.request_id:
            raise WorkerError("worker response request id mismatch")
        if not self.ok:
            raise WorkerError(f"worker failed: {self.error or 'unspecified failure'}")
        if self.completed_work_units != request.work_units:
            raise WorkerError("worker did not account for exact declared work units")
        if self.elapsed_ns is None or self.elapsed_ns < 0:
            raise WorkerError("worker did not provide a valid timed duration")
        missing = [phase for phase in PHASES if self.phases.get(phase) != "ok"]
        if missing:
            raise WorkerError(f"worker did not complete required phases: {', '.join(missing)}")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerError(f"{label} must be an integer")
    return value


class FreshWorker:
    """Run one request in one newly-created process; runners own workload dispatch."""

    def __init__(self, command: Sequence[str], *, cwd: Path | None = None) -> None:
        if not command:
            raise WorkerError("fresh worker command must not be empty")
        self.command = tuple(command)
        self.cwd = cwd

    def run(self, request: WorkerRequest) -> WorkerResult:
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = str(request.hash_seed)
        try:
            process = subprocess.run(
                self.command,
                input=request.to_jsonl(),
                capture_output=True,
                cwd=self.cwd,
                env=environment,
                timeout=request.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise WorkerError(f"worker timed out after {request.timeout_seconds}s") from error
        if process.returncode:
            stderr = process.stderr.decode(errors="replace").strip()
            raise WorkerError(f"worker exited {process.returncode}: {stderr}")
        lines = [line for line in process.stdout.decode("utf-8").splitlines() if line]
        if len(lines) != 1:
            raise WorkerError("worker must emit exactly one JSONL result")
        try:
            result = WorkerResult.from_dict(json.loads(lines[0]))
        except json.JSONDecodeError as error:
            raise WorkerError(f"worker emitted invalid JSONL: {error}") from error
        result.require_complete(request)
        return result
