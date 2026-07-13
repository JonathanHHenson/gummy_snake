"""Private helpers for Rust-backed ECS physical system execution."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action
from gummysnake.ecs.physical import PhysicalPlanUnsupported, build_physical_payload
from gummysnake.ecs.runtime_views import _ScheduledSystem
from gummysnake.ecs.systems import PlanBuiltSystem
from gummysnake.ecs.world_helpers import (
    _contains_canvas_action,
    _contains_direct_udf_action,
    _is_direct_udf_action,
    _payload_has_input_state,
)
from gummysnake.ecs.world_runtime.physical_execution.canvas_dispatch import (
    refresh_rust_input_states,
)
from gummysnake.ecs.world_runtime.physical_execution.execution_reports import (
    execute_compiled_plan,
    execute_compiled_plans_to_canvas,
    record_physical_report,
)
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


_PHYSICAL_COUNTERS: tuple[str, ...] = (
    "spatial_indexes_built",
    "spatial_candidate_rows",
    "spatial_exact_rows",
    "spatial_false_positive_rows",
    "spatial_deduplicated_pairs",
    "spatial_algorithm_hash_grid",
    "spatial_algorithm_quadtree",
    "spatial_algorithm_octree",
    "spatial_algorithm_hilbert_curve",
    "spatial_index_reuses",
    "spatial_index_full_rebuilds",
    "spatial_index_incremental_updates",
    "spatial_parallel_chunks",
    "spatial_thread_scratch_reuses",
    "spatial_candidate_buffer_growths",
)
_SPATIAL_WARM_COUNTERS: tuple[str, ...] = (
    "spatial_indexes_built",
    "spatial_index_reuses",
    "spatial_index_full_rebuilds",
    "spatial_index_incremental_updates",
    "spatial_parallel_chunks",
    "spatial_thread_scratch_reuses",
    "spatial_candidate_buffer_growths",
)


def prepare_scheduled_physical_plan(world: EcsWorld, scheduled: _ScheduledSystem) -> None:
    """Compile and warm the Rust physical plan for a scheduled ECS system plan."""
    if not isinstance(scheduled.built, PlanBuiltSystem):
        return
    action = scheduled.built.plan.action
    if _is_direct_udf_action(action) or _contains_direct_udf_action(action):
        return
    set_physical_payload(scheduled, build_and_compile_payload(world, scheduled, scheduled.built))
    if not scheduled.physical_has_input_state and scheduled.physical_plan_handle is not None:
        # Spatial prewarming is an optimization only; execution will build any missing
        # caches on demand and surface real plan errors through the normal path.
        with suppress(AttributeError, ValueError):
            warm_spatial_indexes = cast(
                Callable[[int], dict[str, Any]],
                cast(Any, world._rust).warm_compiled_plan_spatial_indexes,
            )
            scheduled.physical_warm_report = warm_spatial_indexes(scheduled.physical_plan_handle)


def set_physical_payload(scheduled: _ScheduledSystem, payload: dict[str, Any]) -> None:
    """Attach a compiled bridge payload summary to a scheduled ECS system."""
    scheduled.physical_payload = payload
    scheduled.physical_payload_dynamic = bool(payload.get("dynamic", False))
    scheduled.physical_has_input_state = _payload_has_input_state(payload)
    scheduled.physical_warm_report = None


def require_plan_built(scheduled: _ScheduledSystem) -> PlanBuiltSystem:
    """Return the scheduled Rust plan metadata, or reject non-plan systems."""
    if not isinstance(scheduled.built, PlanBuiltSystem):
        raise SystemPlanError(
            f"ECS system {scheduled.handle.name!r} is a runtime Python system, not a Rust plan."
        )
    return scheduled.built


def build_and_compile_payload(
    world: EcsWorld, scheduled: _ScheduledSystem, built: PlanBuiltSystem
) -> dict[str, Any]:
    """Build a Python logical-plan payload and compile it into a Rust plan handle."""
    schema_fingerprint: int | None = None
    try:
        payload = build_physical_payload(world, built)
        schema_fingerprint = world._rust.schema_fingerprint()
        if scheduled.physical_plan_handle is not None:
            world._rust.release_compiled_plan(scheduled.physical_plan_handle)
            scheduled.physical_plan_handle = None
        summary = world._rust.compile_bridge_plan(payload)
        scheduled.physical_plan_handle = int(summary["handle"])
        scheduled.physical_schema_fingerprint = schema_fingerprint
        world._diagnostics["ecs_physical_plan_compiles"] += 1
        return payload
    except PhysicalPlanUnsupported as exc:
        message = (
            f"ECS system plan {scheduled.handle.name!r} cannot execute in Rust ECS: {exc}. "
            "Python fallback execution has been removed; use explicit @ecs.system or "
            "@ecs.udf boundaries for Python runtime work."
        )
        scheduled.physical_payload = None
        scheduled.physical_plan_handle = None
        scheduled.physical_warm_report = None
        scheduled.physical_schema_fingerprint = schema_fingerprint
        world._diagnostics["ecs_physical_plan_errors"] += 1
        raise SystemPlanError(message) from exc
    except (AttributeError, ValueError) as exc:
        scheduled.physical_payload = None
        scheduled.physical_plan_handle = None
        scheduled.physical_warm_report = None
        scheduled.physical_schema_fingerprint = schema_fingerprint
        world._diagnostics["ecs_physical_plan_compile_errors"] += 1
        raise SystemPlanError(
            f"ECS system {scheduled.handle.name!r} could not compile for Rust ECS: {exc}"
        ) from exc


def run_physical_systems_batch(world: EcsWorld, scheduled_systems: list[_ScheduledSystem]) -> None:
    """Execute several scheduled Rust ECS systems through one bridge call when safe."""

    if len(scheduled_systems) <= 1:
        _run_physical_systems_individually(world, scheduled_systems)
        return
    try:
        prepared = _prepare_physical_batch(world, scheduled_systems)
        if prepared is None:
            _run_physical_systems_individually(world, scheduled_systems)
            return
        reports = _execute_physical_batch(world, scheduled_systems, prepared.handles)
        if reports is None:
            _run_physical_systems_individually(world, scheduled_systems)
            return
    except (AttributeError, ValueError) as exc:
        _clear_batch_execution_state(scheduled_systems)
        world._diagnostics["ecs_physical_execution_errors"] += 1
        names = ", ".join(scheduled.handle.name for scheduled in scheduled_systems)
        raise SystemExecutionError(
            f"ECS systems {names!r} could not execute in Rust ECS batch: {exc}"
        ) from exc
    _record_physical_batch_reports(world, scheduled_systems, reports, prepared.warm_reports)


@dataclass(frozen=True)
class _PreparedPhysicalBatch:
    """Compiled Rust handles and warm reports for a compatible schedule phase."""

    handles: list[int]
    warm_reports: list[dict[str, Any] | None]


def _run_physical_systems_individually(
    world: EcsWorld, scheduled_systems: list[_ScheduledSystem]
) -> None:
    for scheduled in scheduled_systems:
        run_physical_system(world, scheduled)


def _prepare_physical_batch(
    world: EcsWorld, scheduled_systems: list[_ScheduledSystem]
) -> _PreparedPhysicalBatch | None:
    schema_fingerprint = world._rust.schema_fingerprint()
    handles: list[int] = []
    warm_reports: list[dict[str, Any] | None] = []
    for scheduled in scheduled_systems:
        if _refresh_scheduled_batch_plan(world, scheduled, schema_fingerprint):
            return None
        handle = _required_physical_plan_handle(scheduled)
        handles.append(handle)
        warm_reports.append(scheduled.physical_warm_report)
    return _PreparedPhysicalBatch(handles, warm_reports)


def _refresh_scheduled_batch_plan(
    world: EcsWorld, scheduled: _ScheduledSystem, schema_fingerprint: int
) -> bool:
    if scheduled.physical_payload_dynamic:
        return True
    built = require_plan_built(scheduled)
    if _needs_physical_recompile(scheduled, schema_fingerprint):
        set_physical_payload(scheduled, build_and_compile_payload(world, scheduled, built))
    else:
        world._diagnostics["ecs_steady_physical_plan_reuses"] += 1
    return scheduled.physical_has_input_state


def _needs_physical_recompile(scheduled: _ScheduledSystem, schema_fingerprint: int) -> bool:
    return (
        scheduled.physical_plan_handle is None
        or scheduled.physical_schema_fingerprint != schema_fingerprint
        or scheduled.physical_payload_dynamic
    )


def _required_physical_plan_handle(scheduled: _ScheduledSystem) -> int:
    if scheduled.physical_plan_handle is None:
        raise SystemPlanError(
            f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
        )
    return scheduled.physical_plan_handle


def _execute_physical_batch(
    world: EcsWorld, scheduled_systems: list[_ScheduledSystem], handles: list[int]
) -> list[dict[str, Any]] | None:
    include_writes = world._has_change_filtered_systems()
    if _batch_contains_canvas_actions(scheduled_systems):
        return execute_compiled_plans_to_canvas(world, handles, include_writes)
    return _execute_non_canvas_batch(world, handles, include_writes)


def _batch_contains_canvas_actions(scheduled_systems: list[_ScheduledSystem]) -> bool:
    return any(
        _contains_canvas_action(scheduled.built.plan.action) for scheduled in scheduled_systems
    )


def _execute_non_canvas_batch(
    world: EcsWorld, handles: list[int], include_writes: bool
) -> list[dict[str, Any]] | None:
    execute_sequential = getattr(world._rust, "execute_compiled_plans_sequential", None)
    if not callable(execute_sequential):
        return None
    return cast(list[dict[str, Any]], execute_sequential(handles, include_writes))


def _clear_batch_execution_state(scheduled_systems: list[_ScheduledSystem]) -> None:
    for scheduled in scheduled_systems:
        scheduled.physical_payload = None
        scheduled.physical_plan_handle = None
        scheduled.physical_warm_report = None


def _record_physical_batch_reports(
    world: EcsWorld,
    scheduled_systems: list[_ScheduledSystem],
    reports: list[dict[str, Any]],
    warm_reports: list[dict[str, Any] | None],
) -> None:
    for scheduled, report, warm_report in zip(
        scheduled_systems, reports, warm_reports, strict=True
    ):
        record_physical_report(world, report, warm_report=warm_report)
        scheduled.physical_warm_report = None


def run_physical_system(
    world: EcsWorld, scheduled: _ScheduledSystem, action: Action | None = None
) -> None:
    """Execute a scheduled system through its compiled Rust physical plan."""
    use_scheduled_cache = action is None or action is scheduled.built.plan.action
    temporary_handle: int | None = None
    temporary_has_input_state = False
    execution_payload: dict[str, Any] | None = None
    try:
        if use_scheduled_cache:
            built = require_plan_built(scheduled)
            schema_fingerprint = world._rust.schema_fingerprint()
            needs_recompile = (
                scheduled.physical_plan_handle is None
                or scheduled.physical_schema_fingerprint != schema_fingerprint
                or scheduled.physical_payload_dynamic
            )
            if needs_recompile:
                if scheduled.physical_payload_dynamic:
                    world._diagnostics["ecs_dynamic_change_plan_recompiles"] += 1
                set_physical_payload(scheduled, build_and_compile_payload(world, scheduled, built))
            else:
                world._diagnostics["ecs_steady_physical_plan_reuses"] += 1
            execution_payload = scheduled.physical_payload
            if scheduled.physical_plan_handle is None:
                raise SystemPlanError(
                    f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                )
            handle = scheduled.physical_plan_handle
        else:
            assert action is not None
            built = replace(require_plan_built(scheduled), plan=action.plan())
            payload = build_and_compile_payload(world, scheduled, built)
            execution_payload = payload
            temporary_handle = scheduled.physical_plan_handle
            if temporary_handle is None:
                raise SystemPlanError(
                    f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                )
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
            scheduled.physical_payload_dynamic = False
            temporary_has_input_state = _payload_has_input_state(payload)
            handle = temporary_handle

        if scheduled.physical_has_input_state or (
            not use_scheduled_cache and temporary_has_input_state
        ):
            refresh_rust_input_states(world, execution_payload)
        report = execute_compiled_plan(world, scheduled, handle)
    except (AttributeError, ValueError) as exc:
        if use_scheduled_cache:
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
            scheduled.physical_warm_report = None
        world._diagnostics["ecs_physical_execution_errors"] += 1
        raise SystemExecutionError(
            f"ECS system {scheduled.handle.name!r} could not execute in Rust ECS: {exc}"
        ) from exc
    finally:
        if temporary_handle is not None:
            world._rust.release_compiled_plan(temporary_handle)
    warm_report = scheduled.physical_warm_report if use_scheduled_cache else None
    record_physical_report(world, report, warm_report=warm_report)
    if use_scheduled_cache:
        scheduled.physical_warm_report = None
