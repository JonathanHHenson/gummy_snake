"""Private helpers for ECS system scheduling and execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action, DefaultAction
from gummysnake.ecs.runtime_views import SystemHandle, _ScheduledSystem
from gummysnake.ecs.specs import ChangeTerm, QuerySpec
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.world_helpers import (
    _contains_direct_udf_action,
    _handle_matches,
    _is_direct_udf_action,
    _is_sequence_action,
)
from gummysnake.ecs.world_runtime.physical import (
    prepare_scheduled_physical_plan,
    run_physical_system,
)
from gummysnake.ecs.world_runtime.python_system import run_python_system
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def add_system(
    world: EcsWorld,
    system: SystemDefinition,
    *,
    order: int = 0,
    enabled: bool = True,
    name: str | None = None,
    before: tuple[SystemHandle | str, ...],
    after: tuple[SystemHandle | str, ...],
    run_if: object,
    set_name: str | None,
) -> SystemHandle:
    """Validate, compile, and schedule one ECS system."""
    if not isinstance(system, SystemDefinition):
        raise SystemPlanError("gs.add_system() expects a function decorated with @ecs.system.")
    built = system.build()
    system_name = name or built.name
    if any(s.handle.name == system_name for s in world._systems):
        raise SystemPlanError(f"ECS system name {system_name!r} is already registered.")
    handle = SystemHandle(world._next_system_id, system_name)
    world._next_system_id += 1
    scheduled = _ScheduledSystem(
        handle,
        built,
        int(order),
        bool(enabled),
        before=before,
        after=after,
        run_if=cast(Any, run_if),
        set_name=set_name,
    )
    prepare_scheduled_physical_plan(world, scheduled)
    world._systems.append(scheduled)
    world._systems = world._sorted_systems()
    world._has_change_filtered_systems_cache = None
    world._diagnostics["ecs_systems_registered"] = len(world._systems)
    world._diagnostics["ecs_schedule_rebuilds"] += 1
    return handle


def remove_system(world: EcsWorld, handle: SystemHandle | str) -> None:
    """Remove scheduled systems matching a handle or name."""
    removed = [s for s in world._systems if _handle_matches(s.handle, handle)]
    if not removed:
        raise SystemPlanError(f"Unknown ECS system {handle!r}.")
    for scheduled in removed:
        if scheduled.physical_plan_handle is not None:
            world._rust.release_compiled_plan(scheduled.physical_plan_handle)
    world._systems = [s for s in world._systems if not _handle_matches(s.handle, handle)]
    world._has_change_filtered_systems_cache = None
    world._diagnostics["ecs_systems_registered"] = len(world._systems)


def run_pre_draw_systems(world: EcsWorld) -> None:
    """Run one ECS pre-draw frame with change-frame bookkeeping."""
    world._diagnostics["ecs_pre_draw_runs"] += 1
    world._begin_change_frame()
    world._invalidate_spatial_indexes(clear_only=True)
    try:
        run_sorted_systems(world)
    finally:
        world._finalize_change_frame()


def run_sorted_systems(world: EcsWorld) -> None:
    """Run all enabled systems in sorted schedule order."""
    for scheduled in world._sorted_systems():
        if not world._system_enabled(scheduled):
            continue
        if not world._system_run_condition(scheduled):
            world._diagnostics["ecs_system_run_condition_skips"] += 1
            continue
        try:
            run_system_action(world, scheduled, scheduled.built.plan.action)
        except Exception as exc:
            if isinstance(exc, SystemPlanError | SystemExecutionError):
                raise
            raise SystemExecutionError(
                f"ECS system {scheduled.handle.name!r} failed: {exc}"
            ) from exc


def run_system_action(world: EcsWorld, scheduled: _ScheduledSystem, action: Action) -> None:
    """Execute one scheduled action tree through the appropriate runtime boundary."""
    if scheduled.built.python:
        run_python_system(world, scheduled)
        return
    if _is_direct_udf_action(action):
        udf_action = cast(DefaultAction, action)
        if udf_action.udf is None:
            raise SystemExecutionError("Malformed ECS UDF action.")
        udf_action.udf.execute_action(world, udf_action.udf_args)
        return
    if _contains_direct_udf_action(action):
        if _is_sequence_action(action):
            for child in cast(Any, action).children:
                run_system_action(world, scheduled, child)
            return
        raise SystemPlanError(
            "Python UDF actions can only appear as standalone actions or inside "
            "do_in_order() sequences; non-UDF ECS work still executes in Rust."
        )
    run_physical_system(world, scheduled, action)


def has_change_filtered_systems(world: EcsWorld) -> bool:
    """Return whether any scheduled system uses Added/Changed/Removed filters."""
    cached = world._has_change_filtered_systems_cache
    if cached is not None:
        return cached
    for scheduled in world._systems:
        for query in scheduled.built.queries:
            spec = query.spec
            if isinstance(spec, QuerySpec) and any(
                isinstance(term, ChangeTerm) for term in spec.terms
            ):
                world._has_change_filtered_systems_cache = True
                return True
    world._has_change_filtered_systems_cache = False
    return False
