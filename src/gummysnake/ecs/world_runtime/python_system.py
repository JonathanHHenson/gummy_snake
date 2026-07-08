"""Private helpers for explicit Python ECS system execution."""

from __future__ import annotations

import inspect
import time
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from gummysnake._async import call_maybe_async
from gummysnake.ecs.runtime_views import _RuntimeEventWriter, _ScheduledSystem
from gummysnake.ecs.scheduling_helpers import scheduled_system_group_names
from gummysnake.ecs.specs import EventSpec, QuerySpec, ResourceSpec
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def run_python_system(world: EcsWorld, scheduled: _ScheduledSystem) -> None:
    """Materialize ECS arguments and invoke one explicit ``@ecs.system(python=True)`` callback."""
    definition = scheduled.built.definition
    callback = definition.function
    signature = inspect.signature(callback)
    hints = get_type_hints(callback, include_extras=True)
    args: list[object] = []
    materialized_count = 0
    start = time.perf_counter()
    try:
        for parameter in signature.parameters.values():
            annotation = hints.get(parameter.name)
            if isinstance(annotation, QuerySpec):
                rows = tuple(world.match_query(annotation))
                materialized_count += len(rows)
                args.append(rows)
            elif isinstance(annotation, ResourceSpec):
                args.append(world.get_resource(annotation.resource_type))
            elif isinstance(annotation, EventSpec):
                if annotation.mode == "reader":
                    args.append(world.read_events(annotation.event_type))
                else:
                    args.append(_RuntimeEventWriter(world, annotation.event_type))
            elif parameter.name in definition.queries:
                query = definition.queries[parameter.name]
                if not isinstance(query, QuerySpec):
                    raise SystemPlanError(
                        f"Python ECS system query metadata for {parameter.name!r} "
                        "must be ecs.Query[...]."
                    )
                rows = tuple(world.match_query(query))
                materialized_count += len(rows)
                args.append(rows)
            else:
                args.append(None)
        call_maybe_async(callback, *args)
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
