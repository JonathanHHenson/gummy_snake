"""Private helpers for ECS world diagnostics and frame-local state."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gummysnake.ecs.runtime_views import Entity, SystemHandle, _ScheduledSystem, _SystemSetConfig
from gummysnake.ecs.scheduling_helpers import (
    scheduled_system_group_names,
    sorted_system_groups,
    validate_group_name,
)
from gummysnake.ecs.world_helpers import _handle_matches
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def configure(
    world: EcsWorld, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
) -> None:
    """Update ECS diagnostic and ambiguity-handling options."""
    if strict is not None:
        world.strict = bool(strict)
    if warn_on_ambiguity is not None:
        world.warn_on_ambiguity = bool(warn_on_ambiguity)


def diagnostics(world: EcsWorld) -> dict[str, Any]:
    """Merge Python boundary counters with the canonical Rust ECS snapshot."""
    enabled = sum(1 for system in world._systems if system.enabled)
    data: dict[str, Any] = dict(world._diagnostics)
    rust_snapshot = dict(world._rust.diagnostics())
    messages = list(rust_snapshot.pop("messages"))
    for name, value in rust_snapshot.items():
        data[f"ecs_{name}"] = value
        data[f"ecs_rust_{name}"] = value
    data["ecs_events_read"] = data["ecs_event_records_read"]
    data.update(
        {
            "ecs_systems_registered": len(world._systems),
            "ecs_systems_enabled": enabled,
            "ecs_rust_core": "available",
            "ecs_rust_compiled_plans": world._rust.compiled_plan_count(),
            "ecs_spatial_index_cache_len": int(world._rust.spatial_index_cache_len()),
            "ecs_rust_structural_revision": int(world._rust.structural_revision()),
            "ecs_rust_field_revision": int(world._rust.field_revision()),
            "ecs_strict": world.strict,
            "ecs_warn_on_ambiguity": world.warn_on_ambiguity,
            "messages": messages,
        }
    )
    data.setdefault("ecs_python_event_mirror_entries", 0)
    data.setdefault("ecs_python_event_payload_materializations", 0)
    data.setdefault("ecs_dynamic_change_plan_recompiles", 0)
    data.setdefault("ecs_steady_physical_plan_reuses", 0)
    for counter in (
        "prepared_plan_preparations",
        "prepared_plan_cache_hits",
        "prepared_plan_cache_misses",
        "prepared_plan_canonical_reuses",
        "prepared_plan_preparation_nanos",
        "prepared_plan_bytes_current",
        "prepared_plan_bytes_peak",
        "prepared_plan_schema_invalidations",
        "prepared_plans_unique",
        "executor_fixed_slot_runs",
        "executor_generic_slow_paths",
        "scheduler_wave_builds",
        "scheduler_waves",
        "scheduler_systems",
        "scheduler_world_clones",
        "scheduler_snapshot_bytes",
        "event_records_dropped",
        "event_queue_bytes",
        "resource_row_bytes",
        "spatial_index_owners",
        "spatial_index_cache_entries",
    ):
        data.setdefault(f"ecs_{counter}", 0)
        data.setdefault(f"ecs_rust_{counter}", data[f"ecs_{counter}"])
    data.setdefault("ecs_canvas_python_replays", 0)
    data.setdefault("ecs_canvas_python_materialized_commands", 0)
    return data


def reset_diagnostics(world: EcsWorld) -> None:
    """Reset Rust-owned diagnostics, then clear Python-only boundary counters."""
    world._rust.reset_diagnostics()
    world._diagnostics.clear()


def record_ambiguity(world: EcsWorld, message: str) -> None:
    """Record or raise an ambiguous ECS write/order diagnostic."""
    if world.strict:
        world._diagnostics["ecs_strict_mode_errors"] += 1
        raise SystemPlanError(message)
    world._diagnostics["ecs_ambiguity_warnings"] += 1
    world._rust.record_diagnostic_message(message)
    if world.warn_on_ambiguity:
        warnings.warn(message, RuntimeWarning, stacklevel=3)
    else:
        world._diagnostics["ecs_ambiguity_warnings_suppressed"] += 1


def note_field_update(world: EcsWorld, entity: Entity, component_type: type[Any]) -> None:
    """Record a component field update and invalidate dependent caches."""
    world._diagnostics["ecs_rows_updated"] += 1
    invalidate_spatial_indexes(world)


def note_resource_update(world: EcsWorld) -> None:
    """Record a resource update and clear expression caches that may read it."""
    world._diagnostics["ecs_resource_updates"] += 1
    world._expression_eval_cache.clear()


def invalidate_spatial_indexes(world: EcsWorld, *, clear_only: bool = False) -> None:
    """Invalidate Python-side spatial and expression caches."""
    if world._defer_spatial_invalidation and not clear_only:
        world._spatial_invalidated_deferred = True
        world._diagnostics["ecs_spatial_deferred_invalidations"] += 1
        return
    if not clear_only:
        world._spatial_epoch += 1
    world._spatial_index_cache.clear()
    world._spatial_relation_cache.clear()
    world._spatial_aggregate_cache.clear()
    world._expression_eval_cache.clear()


def configure_system_set(
    world: EcsWorld,
    name: str,
    *,
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Deprecated compatibility wrapper for group configuration."""
    configure_system_group(world, name, enabled=enabled, run_if=run_if)


def configure_system_group(
    world: EcsWorld,
    name: str,
    *,
    before: tuple[str, ...] = (),
    after: tuple[str, ...] = (),
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Create or replace scheduling options for a named ECS system group."""

    group_name = validate_group_name(name)
    config = world._system_sets.get(group_name, _SystemSetConfig())
    world._system_sets[group_name] = _SystemSetConfig(
        enabled=config.enabled if enabled is None else enabled,
        run_if=config.run_if if run_if is None else run_if,
        before=tuple(validate_group_name(ref) for ref in before) or config.before,
        after=tuple(validate_group_name(ref) for ref in after) or config.after,
    )
    sorted_system_groups(world._systems, world._system_sets, world._group_orders)
    world._diagnostics["ecs_schedule_rebuilds"] += 1


def configure_group_order(world: EcsWorld, groups: tuple[str, ...]) -> None:
    """Append a left-to-right group ordering constraint after validation."""

    if not groups:
        raise SystemPlanError("gs.order(...) requires at least one ECS system group name.")
    normalized = tuple(validate_group_name(group_name) for group_name in groups)
    if len(set(normalized)) != len(normalized):
        raise SystemPlanError("gs.order(...) group names must be unique.")
    world._group_orders.append(normalized)
    try:
        sorted_system_groups(world._systems, world._system_sets, world._group_orders)
    except Exception:
        world._group_orders.pop()
        raise
    for group_name in normalized:
        world._system_sets.setdefault(group_name, _SystemSetConfig())
    world._diagnostics["ecs_schedule_rebuilds"] += 1


def system_enabled(world: EcsWorld, scheduled: _ScheduledSystem) -> bool:
    """Return whether a scheduled system is enabled after group-level overrides."""
    for group_name in scheduled_system_group_names(scheduled):
        config = world._system_sets.get(group_name)
        if config is not None and config.enabled is False:
            return False
    return scheduled.enabled


def system_run_condition(world: EcsWorld, scheduled: _ScheduledSystem) -> bool:
    """Evaluate group-level and system-level run conditions."""
    for group_name in scheduled_system_group_names(scheduled):
        config = world._system_sets.get(group_name)
        if config is not None and config.run_if is not None and not bool(config.run_if()):
            return False
    return scheduled.run_if is None or bool(scheduled.run_if())


def begin_change_frame(world: EcsWorld) -> None:
    """Start a new ECS change-detection frame."""
    world._ecs_frame += 1
    world._rust.set_frame(world._ecs_frame)
    world._diagnostics["ecs_change_detection_refreshes"] += 1


def set_system_enabled(world: EcsWorld, handle: SystemHandle | str, enabled: bool) -> None:
    """Enable or disable a registered ECS system by handle or name."""
    for scheduled in world._systems:
        if _handle_matches(scheduled.handle, handle):
            scheduled.enabled = enabled
            return
    raise SystemPlanError(f"Unknown ECS system {handle!r}.")
