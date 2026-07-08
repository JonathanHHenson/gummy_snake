"""Private helpers for Rust-backed ECS physical system execution."""

from __future__ import annotations

import copy
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action
from gummysnake.ecs.physical import PhysicalPlanUnsupported, build_physical_payload
from gummysnake.ecs.runtime_views import Entity, _ScheduledSystem
from gummysnake.ecs.schema_helpers import _event_payload_from_bridge
from gummysnake.ecs.systems import PlanBuiltSystem
from gummysnake.ecs.world_helpers import (
    _contains_canvas_action,
    _contains_direct_canvas_barrier_action,
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
        for scheduled in scheduled_systems:
            run_physical_system(world, scheduled)
        return
    try:
        handles: list[int] = []
        warm_reports: list[dict[str, Any] | None] = []
        schema_fingerprint = world._rust.schema_fingerprint()
        for scheduled in scheduled_systems:
            built = require_plan_built(scheduled)
            needs_recompile = (
                scheduled.physical_plan_handle is None
                or scheduled.physical_schema_fingerprint != schema_fingerprint
                or scheduled.physical_payload_dynamic
            )
            if needs_recompile:
                set_physical_payload(scheduled, build_and_compile_payload(world, scheduled, built))
            if scheduled.physical_has_input_state or scheduled.physical_payload_dynamic:
                for fallback in scheduled_systems:
                    run_physical_system(world, fallback)
                return
            if scheduled.physical_plan_handle is None:
                raise SystemPlanError(
                    f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                )
            handles.append(scheduled.physical_plan_handle)
            warm_reports.append(scheduled.physical_warm_report)
        include_writes = world._has_change_filtered_systems()
        if any(
            _contains_canvas_action(scheduled.built.plan.action) for scheduled in scheduled_systems
        ):
            reports = execute_compiled_plans_to_canvas(world, handles, include_writes)
        else:
            execute_sequential = getattr(world._rust, "execute_compiled_plans_sequential", None)
            if not callable(execute_sequential):
                for scheduled in scheduled_systems:
                    run_physical_system(world, scheduled)
                return
            reports = cast(list[dict[str, Any]], execute_sequential(handles, include_writes))
    except (AttributeError, ValueError) as exc:
        for scheduled in scheduled_systems:
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
            scheduled.physical_warm_report = None
        world._diagnostics["ecs_physical_execution_errors"] += 1
        names = ", ".join(scheduled.handle.name for scheduled in scheduled_systems)
        raise SystemExecutionError(
            f"ECS systems {names!r} could not execute in Rust ECS batch: {exc}"
        ) from exc
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
                set_physical_payload(scheduled, build_and_compile_payload(world, scheduled, built))
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


def _direct_canvas_execution_args(world: EcsWorld) -> tuple[Any, Any, Any, bool] | None:
    """Return renderer/canvas/matrix args for Rust-direct ECS canvas replay if available."""

    if os.environ.get("GUMMY_ECS_CANVAS_DIRECT_REPLAY") != "1":
        return None
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
    execute_to_canvas = getattr(world._rust, "execute_compiled_plans_to_canvas", None)
    if direct_args is None or not callable(execute_to_canvas):
        return cast(
            list[dict[str, Any]], world._rust.execute_compiled_plans(handles, include_writes)
        )
    _, canvas, matrix_payload, direct_fill_allowed = direct_args
    return cast(
        list[dict[str, Any]],
        execute_to_canvas(handles, canvas, matrix_payload, direct_fill_allowed, include_writes),
    )


def execute_compiled_plan(
    world: EcsWorld, scheduled: _ScheduledSystem, handle: int
) -> dict[str, Any]:
    """Execute a compiled Rust ECS plan, using native canvas replay when possible."""

    include_writes = world._has_change_filtered_systems()
    if not _contains_canvas_action(scheduled.built.plan.action):
        return cast(dict[str, Any], world._rust.execute_compiled_plan(handle, include_writes))

    direct_args = _direct_canvas_execution_args(world)
    execute_to_canvas = getattr(world._rust, "execute_compiled_plan_to_canvas", None)
    if (
        direct_args is None
        or not callable(execute_to_canvas)
        or _contains_direct_canvas_barrier_action(scheduled.built.plan.action)
    ):
        return cast(dict[str, Any], world._rust.execute_compiled_plan(handle, include_writes))
    _, canvas, matrix_payload, direct_fill_allowed = direct_args
    return cast(
        dict[str, Any],
        execute_to_canvas(handle, canvas, matrix_payload, direct_fill_allowed, include_writes),
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
    dispatch_canvas_commands(world, report)
    dispatch_canvas_fill_batches(world, report)
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


def dispatch_canvas_commands(world: EcsWorld, report: dict[str, Any]) -> None:
    """Replay canvas draw commands emitted by Rust ECS physical execution."""

    commands = report.get("canvas_commands", ())
    if not commands:
        return
    context = world.context
    if context is None:
        raise SystemExecutionError("ECS canvas draw commands require an active SketchContext.")
    from gummysnake import constants as c
    from gummysnake.drawing.primitive_fast_path import (
        PRIMITIVE_ELLIPSE,
        PRIMITIVE_RECT,
        PRIMITIVE_TRIANGLE,
    )

    fast = context.fast()
    renderer = cast(Any, context.renderer)
    primitive_batch = renderer._primitive_batch_state
    primitive_records = primitive_batch.records
    direct_fill_active = False
    matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
    current_fill = context.state.style.fill_rgba
    direct_fill_allowed = (
        current_fill is not None
        and context.state.style.stroke_rgba is None
        and not context.state.style.erasing
        and context.state.style.blend_mode == c.BLEND
    )

    def refresh_direct_fill_state() -> None:
        nonlocal current_fill, direct_fill_allowed, matrix_payload, primitive_records
        style = context.state.style
        primitive_records = primitive_batch.records
        matrix_payload = renderer._matrix_payload(context.state.transform.matrix)
        current_fill = style.fill_rgba
        direct_fill_allowed = (
            current_fill is not None
            and style.stroke_rgba is None
            and not style.erasing
            and style.blend_mode == c.BLEND
        )

    def append_fill_primitive(kind: int, coords: tuple[float, ...]) -> bool:
        nonlocal direct_fill_active, primitive_records
        if not direct_fill_allowed or current_fill is None:
            return False
        if not direct_fill_active:
            renderer._flush_batches_before_primitive_batch()
            primitive_records = primitive_batch.records
            direct_fill_active = True
        if primitive_batch.has_records() and not primitive_batch.matches_fill(matrix_payload):
            renderer._flush_primitive_batch_only()
            primitive_records = primitive_batch.records
        primitive_records.append((kind, *coords, *current_fill))
        primitive_batch.style = None
        primitive_batch.matrix = matrix_payload
        primitive_batch.current = False
        primitive_batch.mode = "fill"
        return True

    handlers: dict[str, Callable[..., Any]] = {
        "background": context.background,
        "clear": context.clear,
        "fill": context.fill,
        "no_fill": context.no_fill,
        "stroke": context.stroke,
        "no_stroke": context.no_stroke,
        "stroke_weight": context.stroke_weight,
        "rect": fast.rect,
        "circle": fast.circle,
        "ellipse": fast.ellipse,
        "line": fast.line,
        "triangle": fast.triangle,
        "text_size": context.text_size,
        "text": fast.text,
    }
    fallback_handlers: dict[str, Callable[..., Any]] = {}
    for command in commands:
        if isinstance(command, (tuple, list)) and len(command) == 2:
            name = str(command[0])
            args = command[1]
        elif isinstance(command, dict):
            name = str(command.get("command", ""))
            args = command.get("args", ())
        else:
            raise SystemExecutionError("Malformed ECS canvas command report.")
        if not name:
            raise SystemExecutionError("Malformed ECS canvas command without a command name.")
        if name == "rect" and len(args) == 4 and context.state.style.rect_mode == c.CORNER:
            if append_fill_primitive(
                PRIMITIVE_RECT, (args[0], args[1], args[2], args[3], 0.0, 0.0)
            ):
                continue
        elif name == "circle" and len(args) == 3 and context.state.style.ellipse_mode == c.CENTER:
            diameter = args[2]
            if append_fill_primitive(
                PRIMITIVE_ELLIPSE,
                (args[0] - diameter / 2.0, args[1] - diameter / 2.0, diameter, diameter, 0.0, 0.0),
            ):
                continue
        elif (
            name == "ellipse"
            and len(args) in {3, 4}
            and context.state.style.ellipse_mode == c.CENTER
        ):
            width = args[2]
            height = width if len(args) == 3 else args[3]
            if append_fill_primitive(
                PRIMITIVE_ELLIPSE,
                (args[0] - width / 2.0, args[1] - height / 2.0, width, height, 0.0, 0.0),
            ):
                continue
        elif (
            name == "triangle"
            and len(args) == 6
            and append_fill_primitive(
                PRIMITIVE_TRIANGLE,
                (args[0], args[1], args[2], args[3], args[4], args[5]),
            )
        ):
            continue

        draw_api = handlers.get(name)
        if draw_api is None:
            draw_api = fallback_handlers.get(name)
            if draw_api is None:
                candidate = getattr(context, name, None)
                if not callable(candidate):
                    raise SystemExecutionError(f"Unsupported ECS canvas command {name!r}.")
                draw_api = cast(Callable[..., Any], candidate)
                fallback_handlers[name] = draw_api
        draw_api(*args)
        if name in {
            "fill",
            "no_fill",
            "stroke",
            "no_stroke",
            "stroke_weight",
            "erase",
            "no_erase",
            "blend_mode",
        }:
            refresh_direct_fill_state()
        else:
            direct_fill_active = False
            refresh_direct_fill_state()
    world._diagnostics["ecs_canvas_commands"] += len(commands)


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
