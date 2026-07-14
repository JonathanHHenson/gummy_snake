"""Execution-report helpers for Rust-backed ECS physical system execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.world_helpers import (
    _contains_canvas_action,
    _contains_direct_canvas_barrier_action,
)
from gummysnake.ecs.world_runtime.physical_execution.canvas_dispatch import (
    apply_physical_report,
    dispatch_canvas_commands,
)
from gummysnake.exceptions import SystemExecutionError

if TYPE_CHECKING:
    from gummysnake.ecs.runtime_views import _ScheduledSystem
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


def _direct_canvas_execution_args(world: EcsWorld) -> tuple[Any, Any, Any, bool] | None:
    """Return renderer/canvas/matrix args for Rust-direct ECS canvas replay if available."""

    context = world.context
    if context is None:
        return None
    renderer = cast(Any, context.renderer)
    canvas = getattr(renderer, "_canvas", None)
    if canvas is None:
        return None
    gpu_available = getattr(canvas, "gpu_available", None)
    if not callable(gpu_available) or not bool(gpu_available()):
        return None

    from gummysnake import constants as c

    style = context.state.style
    direct_fill_allowed = (
        style.stroke_rgba is None
        and not style.erasing
        and style.blend_mode == c.BLEND
        and style.rect_mode == c.CORNER
        and style.ellipse_mode == c.CENTER
    )
    renderer._flush_batches_before_primitive_batch()
    matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
    return renderer, canvas, matrix_payload, direct_fill_allowed


def execute_compiled_plans_to_canvas(
    world: EcsWorld, handles: list[int], include_writes: bool
) -> list[dict[str, Any]]:
    """Execute compiled Rust ECS plans with ordered native canvas replay when possible."""

    direct_args = _direct_canvas_execution_args(world)
    if direct_args is None:
        return cast(
            list[dict[str, Any]], world._rust.execute_compiled_plans(handles, include_writes)
        )
    _, canvas, matrix_payload, direct_fill_allowed = direct_args
    return cast(
        list[dict[str, Any]],
        world._rust.execute_compiled_plans_to_canvas(
            handles, canvas, matrix_payload, direct_fill_allowed, include_writes
        ),
    )


def execute_compiled_plan(
    world: EcsWorld, scheduled: _ScheduledSystem, handle: int
) -> dict[str, Any]:
    """Execute a compiled Rust ECS plan, using native canvas replay when possible."""

    include_writes = world._has_change_filtered_systems()
    if not _contains_canvas_action(scheduled.built.plan.action):
        return cast(dict[str, Any], world._rust.execute_compiled_plan(handle, include_writes))

    direct_args = _direct_canvas_execution_args(world)
    if direct_args is None or _contains_direct_canvas_barrier_action(scheduled.built.plan.action):
        return cast(dict[str, Any], world._rust.execute_compiled_plan(handle, include_writes))
    _, canvas, matrix_payload, direct_fill_allowed = direct_args
    return cast(
        dict[str, Any],
        world._rust.execute_compiled_plan_to_canvas(
            handle, canvas, matrix_payload, direct_fill_allowed, include_writes
        ),
    )


def record_spatial_warm_report(world: EcsWorld, report: dict[str, Any]) -> None:
    """Fold Rust spatial prewarm cache counters into Python diagnostics."""
    for counter in _SPATIAL_WARM_COUNTERS:
        world._diagnostics[f"ecs_{counter}"] += int(report.get(counter, 0))
    world._diagnostics["ecs_spatial_parallel_workers"] = max(
        int(world._diagnostics.get("ecs_spatial_parallel_workers", 0)),
        int(report.get("spatial_parallel_workers", 0)),
    )


def should_record_spatial_warm_report(
    warm_report: dict[str, Any], execution_report: dict[str, Any]
) -> bool:
    """Return whether prewarmed spatial work was reused by the execution report."""
    warm_cache_builds = int(warm_report.get("spatial_indexes_built", 0)) + int(
        warm_report.get("spatial_index_incremental_updates", 0)
    )
    execution_cache_builds = int(execution_report.get("spatial_indexes_built", 0)) + int(
        execution_report.get("spatial_index_incremental_updates", 0)
    )
    return (
        warm_cache_builds > 0
        and execution_cache_builds == 0
        and int(execution_report.get("spatial_index_reuses", 0)) > 0
    )


def record_physical_report(
    world: EcsWorld, report: dict[str, Any], *, warm_report: dict[str, Any] | None = None
) -> None:
    """Fold a Rust ECS execution report into Python diagnostics and frame state."""
    if warm_report is not None and should_record_spatial_warm_report(warm_report, report):
        record_spatial_warm_report(world, warm_report)
    apply_physical_report(world, report)
    canvas_commands = report.get("canvas_commands", ())
    canvas_fill_batches = report.get("canvas_fill_batches", ())
    if canvas_commands or canvas_fill_batches:
        world._diagnostics["ecs_canvas_python_replays"] += 1
        world._diagnostics["ecs_canvas_python_materialized_commands"] += len(canvas_commands) + sum(
            len(batch) for batch in canvas_fill_batches
        )
    dispatch_canvas_commands(world, report)
    dispatch_canvas_fill_batches(world, report)
    world._diagnostics["ecs_physical_system_runs"] += 1
    world._diagnostics["ecs_physical_rows_scanned"] += int(report.get("rows_scanned", 0))
    world._diagnostics["ecs_physical_fields_written"] += int(report.get("fields_written", 0))
    world._diagnostics["ecs_physical_resource_fields_written"] += int(
        report.get("resource_fields_written", 0)
    )

    world._diagnostics["ecs_canvas_direct_fill_primitives"] += int(
        report.get("canvas_direct_fill_primitives", 0)
    )
    world._diagnostics["ecs_canvas_fill_batch_primitives"] += sum(
        len(batch) for batch in report.get("canvas_fill_batches", ())
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


def dispatch_canvas_fill_batches(world: EcsWorld, report: dict[str, Any]) -> None:
    """Replay compact fill primitive batches emitted by Rust ECS physical execution."""

    batches = report.get("canvas_fill_batches", ())
    if not batches:
        return
    context = world.context
    if context is None:
        raise SystemExecutionError("ECS canvas draw commands require an active SketchContext.")
    renderer = cast(Any, context.renderer)
    primitive_batch = renderer._primitive_batch_state
    matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
    renderer._flush_batches_before_primitive_batch()
    primitive_records = primitive_batch.records
    for batch in batches:
        if not batch:
            continue
        if primitive_batch.has_records() and not primitive_batch.matches_fill(matrix_payload):
            renderer._flush_primitive_batch_only()
            primitive_records = primitive_batch.records
        primitive_records.extend(tuple(record) for record in batch)
        primitive_batch.style = None
        primitive_batch.matrix = matrix_payload
        primitive_batch.current = False
        primitive_batch.mode = "fill"
