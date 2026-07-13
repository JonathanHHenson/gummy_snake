"""Fresh-process, versioned JSONL protocol with explicit fail-closed phases."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..governance import ExecutionClass, capability_error

PROTOCOL_VERSION = 3
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
    audio: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def require_capabilities(execution_class: ExecutionClass, capabilities: CapabilitySet) -> None:
    """Validate routes before timing and never downgrade interactive/audio requests."""

    if not capabilities.runtime:
        raise capability_error("runtime")
    required: tuple[str, ...]
    if execution_class is ExecutionClass.NATIVE_INTERACTIVE:
        required = ("gpu", "native_window")
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
    suite_id: str = "canvas"
    timed_blocks: int = 1
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise WorkerError("unsupported worker request protocol version")
        if not self.request_id or not self.suite_id or not self.workload_id:
            raise WorkerError("worker request identity must not be empty")
        for value, label in (
            (self.seed, "seed"),
            (self.hash_seed, "hash_seed"),
            (self.timeout_seconds, "timeout_seconds"),
            (self.work_units, "work_units"),
            (self.timed_blocks, "timed_blocks"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise WorkerError(f"worker request {label} must be an integer")
        if self.seed < 0 or not 0 <= self.hash_seed <= 4_294_967_295:
            raise WorkerError("worker request seeds must be valid non-negative process seeds")
        if self.timeout_seconds <= 0 or self.work_units <= 0 or self.timed_blocks <= 0:
            raise WorkerError(
                "worker request timeout, work accounting, and timed block count must be positive"
            )
        if not isinstance(self.payload, Mapping) or not all(
            isinstance(key, str) for key in self.payload
        ):
            raise WorkerError("worker request payload must be an object with string keys")

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "suite_id": self.suite_id,
            "execution_class": self.execution_class.value,
            "workload_id": self.workload_id,
            "seed": self.seed,
            "hash_seed": self.hash_seed,
            "timeout_seconds": self.timeout_seconds,
            "work_units": self.work_units,
            "timed_blocks": self.timed_blocks,
            "payload": dict(self.payload),
            "phases": list(PHASES),
        }

    def to_jsonl(self) -> bytes:
        try:
            encoded = json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise WorkerError(f"worker request is not strict JSON: {error}") from error
        return (encoded + "\n").encode()


@dataclass(frozen=True, slots=True)
class WorkerResult:
    request_id: str
    ok: bool
    phases: Mapping[str, str]
    elapsed_ns: int | None
    completed_work_units: int
    diagnostics: Mapping[str, object]
    elapsed_blocks_ns: tuple[int, ...] = ()
    error: Mapping[str, object] | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise WorkerError("worker result protocol version mismatch")
        if not self.request_id or not isinstance(self.ok, bool):
            raise WorkerError("worker result identity and ok flag are invalid")
        if set(self.phases) != set(PHASES):
            raise WorkerError("worker result must report every declared phase exactly once")
        invalid_status = [
            phase for phase in PHASES if self.phases[phase] not in {"not-run", "ok", "failed"}
        ]
        if invalid_status:
            raise WorkerError(
                f"worker result has invalid phase status: {', '.join(invalid_status)}"
            )
        if (
            isinstance(self.completed_work_units, bool)
            or not isinstance(self.completed_work_units, int)
            or self.completed_work_units < 0
        ):
            raise WorkerError("worker completed work units must be a non-negative integer")
        if self.elapsed_ns is not None and (
            isinstance(self.elapsed_ns, bool)
            or not isinstance(self.elapsed_ns, int)
            or self.elapsed_ns < 0
        ):
            raise WorkerError("worker elapsed duration must be a non-negative integer or null")
        blocks = self.elapsed_blocks_ns
        if not blocks and self.elapsed_ns is not None:
            blocks = (self.elapsed_ns,)
            object.__setattr__(self, "elapsed_blocks_ns", blocks)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in blocks
        ):
            raise WorkerError("worker timed blocks must be non-negative integer nanoseconds")
        if self.elapsed_ns is not None and sum(blocks) != self.elapsed_ns:
            raise WorkerError("worker elapsed duration must equal the sum of timed blocks")
        if not all(isinstance(key, str) for key in self.diagnostics):
            raise WorkerError("worker diagnostics must use string keys")
        if self.ok:
            if self.error is not None:
                raise WorkerError("successful worker result must not include an error")
            incomplete = [phase for phase in PHASES if self.phases[phase] != "ok"]
            if incomplete:
                raise WorkerError("successful worker result must mark every phase ok")
            return
        phases = dict(self.phases)
        failed = [phase for phase in PHASES if phases[phase] == "failed"]
        if not failed:
            failed = [phase for phase in PHASES if phases[phase] != "ok"]
            if not failed:
                raise WorkerError("failed worker result must identify an incomplete phase")
            phases[failed[0]] = "failed"
            object.__setattr__(self, "phases", phases)
        non_teardown = PHASES[:-1]
        failed_before_teardown = [phase for phase in non_teardown if phases[phase] == "failed"]
        if len(failed_before_teardown) > 1:
            raise WorkerError("failed worker result must identify one primary failed phase")
        failed_phase = failed_before_teardown[0] if failed_before_teardown else "teardown"
        if failed_phase in non_teardown:
            if phases["teardown"] not in {"ok", "failed"}:
                raise WorkerError("failed worker result must report teardown completion or failure")
            index = non_teardown.index(failed_phase)
            if any(phases[phase] != "ok" for phase in non_teardown[:index]) or any(
                phases[phase] != "not-run" for phase in non_teardown[index + 1 :]
            ):
                raise WorkerError("failed worker phases must preserve lifecycle ordering")
        elif phases["teardown"] != "failed" or any(phases[phase] != "ok" for phase in non_teardown):
            raise WorkerError("teardown failure requires every prior phase to be complete")
        if self.error is None or set(self.error) not in (
            {"type", "message"},
            {"type", "message", "phase"},
        ):
            raise WorkerError("failed worker result requires type, message, and phase fields")
        error = dict(self.error)
        error.setdefault("phase", failed_phase)
        if error["phase"] != failed_phase or not all(
            isinstance(error[key], str) and error[key] for key in error
        ):
            raise WorkerError("failed worker result error fields must match the failed phase")
        object.__setattr__(self, "error", error)

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> WorkerResult:
        required = {
            "protocol_version",
            "request_id",
            "ok",
            "phases",
            "elapsed_ns",
            "elapsed_blocks_ns",
            "completed_work_units",
            "diagnostics",
            "error",
        }
        if set(raw) != required:
            missing = sorted(required - set(raw))
            extra = sorted(set(raw) - required)
            raise WorkerError(
                f"worker result envelope fields mismatch; missing={missing}, extra={extra}"
            )
        try:
            version = _integer(raw["protocol_version"], "protocol_version")
            phases = raw["phases"]
            diagnostics = raw["diagnostics"]
            error = raw["error"]
            if not isinstance(raw["request_id"], str) or not isinstance(raw["ok"], bool):
                raise WorkerError("worker result request_id and ok must have exact JSON types")
            if not isinstance(phases, Mapping) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in phases.items()
            ):
                raise WorkerError("worker result phases must be a string object")
            if not isinstance(diagnostics, Mapping) or not all(
                isinstance(key, str) for key in diagnostics
            ):
                raise WorkerError("worker result diagnostics must be an object with string keys")
            if error is not None and (
                not isinstance(error, Mapping) or not all(isinstance(key, str) for key in error)
            ):
                raise WorkerError("worker result error must be an object or null")
            return cls(
                request_id=raw["request_id"],
                ok=raw["ok"],
                phases=dict(phases),
                elapsed_ns=(
                    None if raw["elapsed_ns"] is None else _integer(raw["elapsed_ns"], "elapsed_ns")
                ),
                completed_work_units=_integer(raw["completed_work_units"], "completed_work_units"),
                diagnostics=dict(diagnostics),
                elapsed_blocks_ns=_integer_tuple(raw["elapsed_blocks_ns"], "elapsed_blocks_ns"),
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
        if self.phases["teardown"] != "ok":
            raise WorkerError("worker teardown did not complete without a resource leak")
        if not self.ok:
            assert self.error is not None
            raise WorkerError(
                f"worker failed in {self.error['phase']} ({self.error['type']}): "
                f"{self.error['message']}"
            )
        if self.completed_work_units != request.work_units * request.timed_blocks:
            raise WorkerError("worker did not account for exact declared work units")
        if self.elapsed_ns is None or len(self.elapsed_blocks_ns) != request.timed_blocks:
            raise WorkerError("worker did not provide every declared timed block")
        missing = [phase for phase in PHASES if self.phases[phase] != "ok"]
        if missing:
            raise WorkerError(f"worker did not complete required phases: {', '.join(missing)}")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerError(f"{label} must be an integer")
    return value


def _integer_tuple(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise WorkerError(f"{label} must be a list")
    return tuple(_integer(item, f"{label} item") for item in value)


class FreshWorker:
    """Run one request in one newly-created process; runners own workload dispatch."""

    def __init__(self, command: Sequence[str], *, cwd: Path | None = None) -> None:
        if not command:
            raise WorkerError("fresh worker command must not be empty")
        self.command = tuple(command)
        self.cwd = cwd

    def run(self, request: WorkerRequest) -> WorkerResult:
        environment = os.environ.copy()
        # Workers import benchmark code only from their tool-owned cwd and Gummy
        # Snake only from the installed wheel. A caller's source PYTHONPATH is not
        # a valid execution route for a release benchmark.
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PYTHONHASHSEED"] = str(request.hash_seed)
        environment["PYTHONSAFEPATH"] = "1"
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
        stderr = process.stderr.decode("utf-8", errors="replace")
        if process.returncode:
            raise WorkerError(f"worker exited {process.returncode}: {stderr.strip()}")
        if stderr.strip():
            raise WorkerError(f"worker emitted unexpected stderr: {stderr.strip()}")
        try:
            stdout = process.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorkerError("worker output must be UTF-8 JSONL") from error
        if not stdout.endswith("\n") or stdout.count("\n") != 1:
            raise WorkerError("worker must emit exactly one newline-terminated JSONL result")
        try:
            raw = json.loads(
                stdout,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    WorkerError(f"worker JSON contains non-finite value {value}")
                ),
            )
        except json.JSONDecodeError as error:
            raise WorkerError(f"worker emitted invalid JSONL: {error}") from error
        if not isinstance(raw, Mapping):
            raise WorkerError("worker result must be a JSON object")
        result = WorkerResult.from_dict(raw)
        result.require_complete(request)
        return result
