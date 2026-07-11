"""Self-contained Canvas benchmark fixtures, oracles, and workload dispatcher."""

from .workloads import (
    CanvasWorkloadError,
    ExecutionRouteError,
    WorkloadPlan,
    WorkloadRun,
    build_workload,
    dispatch,
)

__all__ = [
    "CanvasWorkloadError",
    "ExecutionRouteError",
    "WorkloadPlan",
    "WorkloadRun",
    "build_workload",
    "dispatch",
]
