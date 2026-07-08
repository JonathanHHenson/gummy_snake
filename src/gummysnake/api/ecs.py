"""Global-mode ECS API wrappers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.api.current import require_context
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.ecs.world import Entity, EntityView, SystemHandle


def add_entity(*components: DataclassInstance, tags: Iterable[EcsTag] = ()) -> Entity:
    """Create an ECS entity in the active sketch.

    Args:
        components: Dataclass component instances to attach to the new entity.
        tags: Optional tag values used to group or filter entities.

    Returns:
        A stable entity handle for the new Rust-owned entity.
    """

    return require_context().add_entity(*components, tags=tags)


def despawn_entity(entity: Entity) -> None:
    """Remove an ECS entity from the active sketch.

    Args:
        entity: Entity handle returned by ``add_entity()`` or an ``EntityView``.
    """

    require_context().despawn_entity(entity)


def add_component(entity: Entity, component: DataclassInstance) -> None:
    """Add or replace a dataclass component on an entity.

    Args:
        entity: Entity handle to update.
        component: Dataclass component instance to store.
    """

    require_context().add_component(entity, component)


def remove_component(entity: Entity, component_type: type[Any]) -> None:
    """Remove one component type from an entity.

    Args:
        entity: Entity handle to update.
        component_type: Dataclass component class to remove.
    """

    require_context().remove_component(entity, component_type)


def add_tag(entity: Entity, tag: EcsTag) -> None:
    """Add a tag to an entity.

    Args:
        entity: Entity handle to update.
        tag: Value converted to a string tag for filtering queries.
    """

    require_context().add_tag(entity, tag)


def remove_tag(entity: Entity, tag: EcsTag) -> None:
    """Remove a tag from an entity.

    Args:
        entity: Entity handle to update.
        tag: Value converted to the string tag to remove.
    """

    require_context().remove_tag(entity, tag)


def get_entity(*components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
    """Return the single entity matching component and tag filters.

    Args:
        components: Component classes that the entity must have.
        tags: Tag values that the entity must have.

    Returns:
        An ``EntityView`` for the matching entity.
    """

    return require_context().get_entity(*components, tags=tags)


def try_get_entity(*components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView | None:
    """Return zero or one entity matching component and tag filters.

    Args:
        components: Component classes that the entity must have.
        tags: Tag values that the entity must have.

    Returns:
        An ``EntityView`` when exactly one entity matches, or ``None`` when no entity matches.
    """

    return require_context().try_get_entity(*components, tags=tags)


def iter_entities(*components: type[Any], tags: Iterable[EcsTag] = ()) -> Iterator[EntityView]:
    """Iterate entities matching component and tag filters.

    Args:
        components: Component classes that each entity must have.
        tags: Tag values that each entity must have.

    Returns:
        An iterator of ``EntityView`` objects in deterministic entity order.
    """

    return require_context().iter_entities(*components, tags=tags)


def iter_component_fields(
    component_type: type[Any],
    *field_names: str,
    tags: Iterable[EcsTag] = (),
) -> Iterator[tuple[Any, ...]]:
    """Read selected component fields for matching entities with one batch call.

    Args:
        component_type: Dataclass component class to read.
        field_names: Names of fields to include in each returned tuple.
        tags: Optional tag values that each entity must have.

    Returns:
        An iterator of tuples whose values match ``field_names`` order.
    """

    return require_context().iter_component_fields(component_type, *field_names, tags=tags)


def set_resource(resource: DataclassInstance) -> None:
    """Store a dataclass resource in the active ECS world.

    Args:
        resource: Dataclass instance to store as a singleton resource.
    """

    require_context().set_resource(resource)


def get_resource[ResourceT](resource_type: type[ResourceT]) -> ResourceT:
    """Return a mutable view for an existing ECS resource.

    Args:
        resource_type: Dataclass resource class to access.

    Returns:
        A resource view typed as ``resource_type`` for convenient field access.
    """

    return require_context().get_resource(resource_type)


def remove_resource(resource_type: type[Any]) -> None:
    """Remove an ECS resource from the active world.

    Args:
        resource_type: Dataclass resource class to remove.
    """

    require_context().remove_resource(resource_type)


def emit_event(event: EcsEventValue) -> None:
    """Send an ECS event for systems that read that event type.

    Args:
        event: Dataclass event instance to enqueue for the current ECS frame.
    """

    require_context().emit_event(event)


def read_events[EventT](event_type: type[EventT]) -> tuple[EventT, ...]:
    """Read events of one type emitted in the current ECS frame.

    Args:
        event_type: Dataclass event class to read.

    Returns:
        A tuple of copied event instances in emission order.
    """

    return require_context().read_events(event_type)


def clear_events(event_type: type[Any] | None = None) -> None:
    """Clear queued ECS events.

    Args:
        event_type: Event class to clear, or ``None`` to clear all event types.
    """

    require_context().clear_events(event_type)


def add_system(
    system: SystemDefinition,
    *,
    enabled: bool = True,
    name: str | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
    run_if: Callable[[], bool] | None = None,
    set: str | Iterable[str] | None = None,
    group: str | Iterable[str] | None = None,
) -> SystemHandle:
    """Register an ``@ecs.system`` with the active sketch.

    Args:
        system: Function decorated with ``@ecs.system``.
        enabled: Whether the system should run immediately after registration.
        name: Optional unique system name. Defaults to the decorated function name.
        before: Groups that should run after this system's implicit group.
        after: Groups that should run before this system's implicit group.
        run_if: Optional callback checked before each scheduled run.
        set: Deprecated alias for ``group``.
        group: Optional explicit system group name or sequence of group names.

    Returns:
        A handle that can enable, disable, or remove the registered system.
    """

    return require_context().add_system(
        system,
        enabled=enabled,
        name=name,
        before=before,
        after=after,
        run_if=run_if,
        set=set,
        group=group,
    )


def remove_system(handle: SystemHandle | str) -> None:
    """Unregister a scheduled ECS system.

    Args:
        handle: System handle or system name returned by ``add_system()``.
    """

    require_context().remove_system(handle)


def enable_system(handle: SystemHandle | str) -> None:
    """Allow a scheduled ECS system to run again.

    Args:
        handle: System handle or system name to enable.
    """

    require_context().enable_system(handle)


def disable_system(handle: SystemHandle | str) -> None:
    """Temporarily prevent a scheduled ECS system from running.

    Args:
        handle: System handle or system name to disable.
    """

    require_context().disable_system(handle)


def configure_ecs(*, strict: bool | None = None, warn_on_ambiguity: bool | None = None) -> None:
    """Configure ECS conflict handling for the active sketch.

    Args:
        strict: When true, reject ambiguous duplicate writes instead of resolving them.
        warn_on_ambiguity: When true, log warnings for deterministic duplicate-write resolution.
    """

    require_context().configure_ecs(strict=strict, warn_on_ambiguity=warn_on_ambiguity)


def configure_system_set(
    name: str,
    *,
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Deprecated alias for ``group(name, enabled=..., run_if=...)``."""

    require_context().configure_system_set(name, enabled=enabled, run_if=run_if)


def group(
    name: str,
    *,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    """Create or configure an ECS system group in the active sketch."""

    require_context().group(name, before=before, after=after, enabled=enabled, run_if=run_if)


def order(groups: Iterable[str]) -> None:
    """Declare a left-to-right ordering for active-sketch ECS system groups."""

    require_context().order(groups)


def ecs_diagnostics() -> dict[str, Any]:
    """Return ECS counters and diagnostic messages for the active sketch.

    Returns:
        A dictionary of diagnostic names to values.
    """

    return require_context().ecs_diagnostics()


def reset_ecs_diagnostics() -> None:
    """Reset ECS diagnostic counters for the active sketch."""

    require_context().reset_ecs_diagnostics()


__all__ = [
    "add_component",
    "add_entity",
    "add_system",
    "add_tag",
    "configure_ecs",
    "clear_events",
    "configure_system_set",
    "despawn_entity",
    "disable_system",
    "ecs_diagnostics",
    "enable_system",
    "get_entity",
    "get_resource",
    "group",
    "emit_event",
    "iter_component_fields",
    "iter_entities",
    "remove_component",
    "read_events",
    "remove_resource",
    "order",
    "remove_system",
    "remove_tag",
    "reset_ecs_diagnostics",
    "set_resource",
    "try_get_entity",
]
