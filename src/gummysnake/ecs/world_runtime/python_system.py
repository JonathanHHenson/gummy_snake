"""Private helpers for explicit Python ECS system execution."""

from __future__ import annotations

import inspect
import time
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from gummysnake._async import call_maybe_async
from gummysnake.ecs.runtime_views import _RuntimeEventWriter, _ScheduledSystem
from gummysnake.ecs.scheduling_helpers import scheduled_system_group_names
from gummysnake.ecs.specs import EventSpec, QuerySpec, ResourceSpec
from gummysnake.ecs.systems import RuntimeSystemDefinition
from gummysnake.ecs.world_runtime.python_batch import PythonEcsAccessBatch
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def run_python_system(world: EcsWorld, scheduled: _ScheduledSystem) -> None:
    """Materialize ECS arguments and invoke one explicit ``@ecs.system`` callback."""
    definition = cast(RuntimeSystemDefinition, scheduled.built.definition)
    callback = definition.function
    args: list[object] = []
    materialized_count = 0
    start = time.perf_counter()
    batch = PythonEcsAccessBatch(world)
    previous_batch = world._active_python_access_batch
    world._active_python_access_batch = batch
    try:
        try:
            for kind, payload in _python_arg_plan(scheduled):
                if kind == "query":
                    query = cast(QuerySpec, payload)
                    rows = batch.materialize_query(query)
                    if rows is None:
                        rows = tuple(world.match_query(query))
                    materialized_count += len(rows)
                    args.append(rows)
                elif kind == "resource":
                    resource = cast(ResourceSpec, payload)
                    args.append(world.get_resource(resource.resource_type))
                elif kind == "event_reader":
                    event = cast(EventSpec, payload)
                    args.append(world.read_events(event.event_type))
                elif kind == "event_writer":
                    event = cast(EventSpec, payload)
                    args.append(_RuntimeEventWriter(world, event.event_type))
                else:
                    args.append(None)
            call_maybe_async(callback, *args)
        finally:
            batch.flush()
            batch.close()
            world._active_python_access_batch = previous_batch
    except Exception as exc:
        if "draw" in scheduled_system_group_names(scheduled):
            raise
        if isinstance(exc, SystemPlanError | SystemExecutionError):
            raise
        raise SystemExecutionError(
            f"Python ECS system {scheduled.handle.name!r} failed while materializing/executing "
            f"with mutations={dict(definition.mutations)!r}: {exc}"
        ) from exc
    finally:
        cast(Any, world._diagnostics)["ecs_python_system_runtime_ms"] += (
            time.perf_counter() - start
        ) * 1000.0
    world._diagnostics["ecs_python_system_calls"] += 1
    world._diagnostics["ecs_python_system_barriers"] += 1
    world._diagnostics["ecs_python_system_entities_materialized"] += materialized_count


def _python_arg_plan(scheduled: _ScheduledSystem) -> tuple[tuple[str, object], ...]:
    cached = scheduled.python_arg_plan
    if cached is not None:
        return cached
    definition = cast(RuntimeSystemDefinition, scheduled.built.definition)
    callback = definition.function
    signature = inspect.signature(callback)
    hints = get_type_hints(callback, include_extras=True)
    plan: list[tuple[str, object]] = []
    for parameter in signature.parameters.values():
        annotation = hints.get(parameter.name)
        if isinstance(annotation, QuerySpec):
            plan.append(("query", annotation))
        elif isinstance(annotation, ResourceSpec):
            plan.append(("resource", annotation))
        elif isinstance(annotation, EventSpec):
            plan.append(
                ("event_reader" if annotation.mode == "reader" else "event_writer", annotation)
            )
        elif parameter.name in definition.queries:
            query = definition.queries[parameter.name]
            if not isinstance(query, QuerySpec):
                raise SystemPlanError(
                    f"Python ECS system query metadata for {parameter.name!r} "
                    "must be ecs.Query[...]."
                )
            plan.append(("query", query))
        else:
            plan.append(("none", None))
    scheduled.python_arg_plan = tuple(plan)
    return scheduled.python_arg_plan
