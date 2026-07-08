"""Private helpers for ECS system scheduling and execution."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, cast

from gummysnake.ecs.actions import Action, DefaultAction
from gummysnake.ecs.runtime_views import SystemHandle, _ScheduledSystem, _SystemSetConfig
from gummysnake.ecs.scheduling_helpers import (
    implicit_system_group_name,
    normalize_group_names,
    scheduled_system_group_names,
)
from gummysnake.ecs.specs import ChangeTerm, QuerySpec
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.world_helpers import (
    _contains_direct_canvas_barrier_action,
    _contains_direct_udf_action,
    _handle_matches,
    _is_direct_udf_action,
    _is_sequence_action,
)
from gummysnake.ecs.world_runtime.physical import (
    prepare_scheduled_physical_plan,
    run_physical_system,
    run_physical_systems_batch,
)
from gummysnake.ecs.world_runtime.python_system import run_python_system
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def add_system(
    world: EcsWorld,
    system: SystemDefinition,
    *,
    enabled: bool = True,
    name: str | None = None,
    before: tuple[str, ...],
    after: tuple[str, ...],
    run_if: Callable[[], bool] | None,
    group_name: str | Iterable[str] | None,
) -> SystemHandle:
    """Validate, compile, and schedule one ECS system."""
    if not isinstance(system, SystemDefinition):
        raise SystemPlanError("gs.add_system() expects a function decorated with @ecs.system.")
    built = system.build()
    system_name = name or built.name
    if any(s.handle.name == system_name for s in world._systems):
        raise SystemPlanError(f"ECS system name {system_name!r} is already registered.")
    explicit_group = group_name if group_name is not None else system.group
    scheduled_before = tuple(str(ref) for ref in (before or system.before))
    scheduled_after = tuple(str(ref) for ref in (after or system.after))
    if explicit_group is not None and (scheduled_before or scheduled_after):
        raise SystemPlanError(
            "ECS systems cannot declare before=... or after=... when group=... is provided; "
            "configure the group order with gs.group() or gs.order()."
        )
    resolved_groups = (
        normalize_group_names(explicit_group)
        if explicit_group is not None
        else (implicit_system_group_name(system_name),)
    )
    for resolved_group in resolved_groups:
        world._system_sets.setdefault(resolved_group, _SystemSetConfig())
    handle = SystemHandle(world._next_system_id, system_name)
    world._next_system_id += 1
    scheduled = _ScheduledSystem(
        handle,
        built,
        resolved_groups[0],
        bool(enabled),
        before=scheduled_before,
        after=scheduled_after,
        run_if=run_if,
        group_names=resolved_groups,
    )
    prepare_scheduled_physical_plan(world, scheduled)
    world._systems.append(scheduled)
    try:
        world._systems = world._sorted_systems()
    except Exception:
        world._systems = [
            registered for registered in world._systems if registered is not scheduled
        ]
        if scheduled.physical_plan_handle is not None:
            world._rust.release_compiled_plan(scheduled.physical_plan_handle)
        raise
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
    """Run one ECS frame with change-frame bookkeeping."""
    world._diagnostics["ecs_system_frame_runs"] += 1
    world._begin_change_frame()
    world._invalidate_spatial_indexes(clear_only=True)
    try:
        run_sorted_systems(world)
    finally:
        world._finalize_change_frame()


def run_sorted_systems(world: EcsWorld) -> None:
    """Run all enabled systems in sorted group order."""

    systems = world._sorted_systems()
    remaining_by_group: dict[str, int] = {}
    for scheduled in systems:
        for group_name in scheduled_system_group_names(scheduled):
            remaining_by_group[group_name] = remaining_by_group.get(group_name, 0) + 1
    active_groups: list[str] = []
    index = 0
    try:
        while index < len(systems):
            scheduled = systems[index]
            if not world._system_enabled(scheduled):
                _advance_group_hooks(world, scheduled, active_groups, remaining_by_group)
                index += 1
                continue
            if not world._system_run_condition(scheduled):
                world._diagnostics["ecs_system_run_condition_skips"] += 1
                _advance_group_hooks(world, scheduled, active_groups, remaining_by_group)
                index += 1
                continue
            _enter_group_hooks(world, scheduled, active_groups)
            try:
                if _can_batch_physical_system(scheduled):
                    if _contains_direct_canvas_barrier_action(scheduled.built.plan.action):
                        run_system_action(world, scheduled, scheduled.built.plan.action)
                        _advance_group_hooks(world, scheduled, active_groups, remaining_by_group)
                        index += 1
                        continue
                    batch = [scheduled]
                    index += 1
                    while index < len(systems):
                        candidate = systems[index]
                        if scheduled_system_group_names(candidate) != scheduled_system_group_names(
                            scheduled
                        ):
                            break
                        if not world._system_enabled(candidate):
                            _advance_group_hooks(
                                world, candidate, active_groups, remaining_by_group
                            )
                            index += 1
                            continue
                        if not world._system_run_condition(candidate):
                            world._diagnostics["ecs_system_run_condition_skips"] += 1
                            _advance_group_hooks(
                                world, candidate, active_groups, remaining_by_group
                            )
                            index += 1
                            continue
                        if not _can_batch_physical_system(candidate):
                            break
                        if _contains_direct_canvas_barrier_action(candidate.built.plan.action):
                            break
                        batch.append(candidate)
                        index += 1
                    run_physical_systems_batch(world, batch)
                    for batched in batch:
                        _advance_group_hooks(world, batched, active_groups, remaining_by_group)
                    continue
                run_system_action(world, scheduled, scheduled.built.plan.action)
                _advance_group_hooks(world, scheduled, active_groups, remaining_by_group)
                index += 1
            except Exception as exc:
                if "draw" in scheduled_system_group_names(scheduled):
                    raise
                if isinstance(exc, SystemPlanError | SystemExecutionError):
                    raise
                raise SystemExecutionError(
                    f"ECS system {scheduled.handle.name!r} failed: {exc}"
                ) from exc
    finally:
        for group_name in reversed(active_groups):
            _dispatch_group_hook(world, "after", group_name)


def _enter_group_hooks(
    world: EcsWorld, scheduled: _ScheduledSystem, active_groups: list[str]
) -> None:
    for group_name in scheduled_system_group_names(scheduled):
        if group_name not in active_groups:
            _dispatch_group_hook(world, "before", group_name)
            active_groups.append(group_name)


def _advance_group_hooks(
    world: EcsWorld,
    scheduled: _ScheduledSystem,
    active_groups: list[str],
    remaining_by_group: dict[str, int],
) -> None:
    for group_name in scheduled_system_group_names(scheduled):
        remaining_by_group[group_name] = max(0, remaining_by_group.get(group_name, 0) - 1)
    for group_name in reversed(tuple(active_groups)):
        if remaining_by_group.get(group_name, 0) <= 0:
            _dispatch_group_hook(world, "after", group_name)
            active_groups.remove(group_name)


def _can_batch_physical_system(scheduled: _ScheduledSystem) -> bool:
    action = scheduled.built.plan.action
    return (
        not scheduled.built.python
        and not _is_direct_udf_action(action)
        and not _contains_direct_udf_action(action)
    )


def _dispatch_group_hook(world: EcsWorld, phase: str, group_name: str) -> None:
    context = getattr(world, "context", None)
    if context is None:
        return
    context.plugins.dispatch_lifecycle(f"{phase}_{group_name}", context)


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
            for child in cast(DefaultAction, action).children:
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
