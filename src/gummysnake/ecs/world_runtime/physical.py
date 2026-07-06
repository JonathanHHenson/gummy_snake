"""Private helpers for Rust-backed ECS physical system execution."""

from __future__ import annotations

import copy
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action
from gummysnake.ecs.physical import PhysicalPlanUnsupported, build_physical_payload
from gummysnake.ecs.runtime_views import Entity, _ScheduledSystem
from gummysnake.ecs.schema_helpers import _event_payload_from_bridge
from gummysnake.ecs.systems import BuiltSystem
from gummysnake.ecs.world_helpers import (
    _contains_direct_udf_action,
    _current_delta_time,
    _current_key_down,
    _is_direct_udf_action,
    _payload_has_input_state,
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


def prepare_scheduled_physical_plan(world: EcsWorld, scheduled: _ScheduledSystem) -> None:
    """Compile and warm the Rust physical plan for a scheduled non-Python ECS system."""
    if scheduled.built.python:
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
            warm_spatial_indexes(scheduled.physical_plan_handle)


def set_physical_payload(scheduled: _ScheduledSystem, payload: dict[str, Any]) -> None:
    """Attach a compiled bridge payload summary to a scheduled ECS system."""
    scheduled.physical_payload = payload
    scheduled.physical_payload_dynamic = bool(payload.get("dynamic", False))
    scheduled.physical_has_input_state = _payload_has_input_state(payload)


def build_and_compile_payload(
    world: EcsWorld, scheduled: _ScheduledSystem, built: BuiltSystem
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
            f"ECS system {scheduled.handle.name!r} cannot execute in Rust ECS: {exc}. "
            "Python fallback execution has been removed; only explicit @ecs.udf actions "
            "may execute in Python."
        )
        scheduled.physical_payload = None
        scheduled.physical_plan_handle = None
        scheduled.physical_schema_fingerprint = schema_fingerprint
        world._diagnostics["ecs_physical_plan_errors"] += 1
        raise SystemPlanError(message) from exc
    except (AttributeError, ValueError) as exc:
        scheduled.physical_payload = None
        scheduled.physical_plan_handle = None
        scheduled.physical_schema_fingerprint = schema_fingerprint
        world._diagnostics["ecs_physical_plan_compile_errors"] += 1
        raise SystemPlanError(
            f"ECS system {scheduled.handle.name!r} could not compile for Rust ECS: {exc}"
        ) from exc


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
            schema_fingerprint = world._rust.schema_fingerprint()
            needs_recompile = (
                scheduled.physical_plan_handle is None
                or scheduled.physical_schema_fingerprint != schema_fingerprint
                or scheduled.physical_payload_dynamic
            )
            if needs_recompile:
                set_physical_payload(
                    scheduled, build_and_compile_payload(world, scheduled, scheduled.built)
                )
            execution_payload = scheduled.physical_payload
            if scheduled.physical_plan_handle is None:
                raise SystemPlanError(
                    f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                )
            handle = scheduled.physical_plan_handle
        else:
            assert action is not None
            built = replace(scheduled.built, plan=action.plan())
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
        report = world._rust.execute_compiled_plan(handle, world._has_change_filtered_systems())
    except (AttributeError, ValueError) as exc:
        if use_scheduled_cache:
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
        world._diagnostics["ecs_physical_execution_errors"] += 1
        raise SystemExecutionError(
            f"ECS system {scheduled.handle.name!r} could not execute in Rust ECS: {exc}"
        ) from exc
    finally:
        if temporary_handle is not None:
            world._rust.release_compiled_plan(temporary_handle)
    record_physical_report(world, report)


def record_physical_report(world: EcsWorld, report: dict[str, Any]) -> None:
    """Fold a Rust ECS execution report into Python diagnostics and frame state."""
    apply_physical_report(world, report)
    world._diagnostics["ecs_physical_system_runs"] += 1
    world._diagnostics["ecs_physical_rows_scanned"] += int(report.get("rows_scanned", 0))
    world._diagnostics["ecs_physical_fields_written"] += int(report.get("fields_written", 0))
    world._diagnostics["ecs_physical_resource_fields_written"] += int(
        report.get("resource_fields_written", 0)
    )
    world._diagnostics["ecs_events_emitted"] += int(report.get("events_emitted", 0))
    world._diagnostics["ecs_structural_commands_applied"] += int(
        report.get("structural_commands", 0)
    )
    for counter in _PHYSICAL_COUNTERS:
        world._diagnostics[f"ecs_{counter}"] += int(report.get(counter, 0))
    world._diagnostics["ecs_spatial_parallel_workers"] = max(
        int(world._diagnostics.get("ecs_spatial_parallel_workers", 0)),
        int(report.get("spatial_parallel_workers", 0)),
    )
    duplicate_writes = int(report.get("duplicate_writes", 0))
    if duplicate_writes:
        world._diagnostics["ecs_physical_duplicate_writes"] += duplicate_writes
        world.record_ambiguity(
            "ECS do_in_parallel()/Rust physical execution wrote the same field more "
            "than once; deterministic last-write-wins is used. Consider group_by(...).any()."
        )


def refresh_rust_input_states(world: EcsWorld, payload: dict[str, Any] | None) -> None:
    """Refresh Rust input-state resources required by a compiled physical plan."""
    if payload is None:
        return
    for expr in payload.get("expressions", ()):  # tiny input binding pass; not ECS execution
        if not isinstance(expr, dict) or expr.get("kind") != "input_state":
            continue
        name = str(expr.get("name", ""))
        code = expr.get("code")
        int_code = int(code) if code is not None else None
        if name == "dt":
            world._rust.set_input_state("dt", _current_delta_time(world))
        elif name == "key_down" and int_code is not None:
            world._rust.set_input_state("key_down", _current_key_down(world, int_code), int_code)


def apply_physical_report(world: EcsWorld, report: dict[str, Any]) -> None:
    """Apply component/resource/event mutations reported by Rust physical execution."""
    previous_defer_spatial = world._defer_spatial_invalidation
    previous_spatial_invalidated = world._spatial_invalidated_deferred
    world._defer_spatial_invalidation = True
    world._spatial_invalidated_deferred = False
    try:
        for write in report.get("component_writes", ()):
            component_type = world._component_type_for_schema(str(write["component"]))
            entity = Entity(int(write["index"]), int(write["generation"]), world._world_id)
            world._mark_component_changed(entity, component_type)
        for event in report.get("events", ()):
            event_type = world._component_type_for_schema(str(event["event_type"]))
            payload = _event_payload_from_bridge(event_type, event["payload"])
            world._events.setdefault(event_type, []).append(
                (world._ecs_frame, copy.deepcopy(payload))
            )
        for write in report.get("resource_writes", ()):
            world._component_type_for_schema(str(write["resource"]))
            world._note_resource_update()
    finally:
        invalidated = world._spatial_invalidated_deferred
        world._defer_spatial_invalidation = previous_defer_spatial
        world._spatial_invalidated_deferred = previous_spatial_invalidated or invalidated
        if invalidated and not previous_defer_spatial:
            world._spatial_invalidated_deferred = previous_spatial_invalidated
            world._invalidate_spatial_indexes()
