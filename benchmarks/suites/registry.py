"""Static suite dispatch shared by smoke and isolated benchmark workers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..governance import ExecutionClass

REGISTERED_SUITE_IDS = frozenset({"canvas", "ecs", "synth"})


class SuiteDispatchError(RuntimeError):
    """A catalog selected an unknown suite or a workload failed its correctness contract."""


@dataclass(frozen=True, slots=True)
class SuiteExecution:
    """One completed bounded workload with suite-neutral diagnostics and summary values."""

    diagnostics: Mapping[str, object]
    summary: Mapping[str, object]


def _canvas(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
) -> SuiteExecution:
    from .canvas.workloads import dispatch

    run = dispatch(workload_id, parameters, execution_class)
    expected = run.plan.expected_draw_callbacks
    if run.frame_count != expected:
        raise SuiteDispatchError(
            f"Canvas frame count mismatch: expected {expected}, got {run.frame_count}"
        )
    return SuiteExecution(
        diagnostics={
            "renderer": run.diagnostics.as_record(),
            "physical_desktop_requested": run.physical_desktop_requested,
        },
        summary={"frames": run.frame_count, "pixel_bytes": len(run.pixels)},
    )


def dispatch(
    suite_id: str,
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
) -> SuiteExecution:
    """Execute a statically registered suite without dynamic plugin discovery."""

    if suite_id not in REGISTERED_SUITE_IDS:
        raise SuiteDispatchError(f"unknown static benchmark suite: {suite_id}")
    if suite_id == "canvas":
        return _canvas(workload_id, parameters, execution_class)
    if suite_id == "ecs":
        from .ecs.workloads import dispatch as dispatch_ecs

        return dispatch_ecs(workload_id, parameters, execution_class)
    from .synth.workloads import dispatch as dispatch_synth

    return dispatch_synth(workload_id, parameters, execution_class)
