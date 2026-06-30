"""Global-mode ECS API wrappers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.api.current import require_context
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.world import Entity, EntityView, SystemHandle


def add_entity(*components: object, tags: Iterable[object] = ()) -> Entity:
    return require_context().add_entity(*components, tags=tags)


def despawn_entity(entity: Entity) -> None:
    require_context().despawn_entity(entity)


def add_component(entity: Entity, component: object) -> None:
    require_context().add_component(entity, component)


def remove_component(entity: Entity, component_type: type[Any]) -> None:
    require_context().remove_component(entity, component_type)


def add_tag(entity: Entity, tag: object) -> None:
    require_context().add_tag(entity, tag)


def remove_tag(entity: Entity, tag: object) -> None:
    require_context().remove_tag(entity, tag)


def get_entity(*components: type[Any], tags: Iterable[object] = ()) -> EntityView:
    return require_context().get_entity(*components, tags=tags)


def try_get_entity(*components: type[Any], tags: Iterable[object] = ()) -> EntityView | None:
    return require_context().try_get_entity(*components, tags=tags)


def iter_entities(*components: type[Any], tags: Iterable[object] = ()) -> Iterator[EntityView]:
    return require_context().iter_entities(*components, tags=tags)


def iter_component_fields(
    component_type: type[Any],
    *field_names: str,
    tags: Iterable[object] = (),
) -> Iterator[tuple[Any, ...]]:
    return require_context().iter_component_fields(component_type, *field_names, tags=tags)


def set_resource(resource: object) -> None:
    require_context().set_resource(resource)


def get_resource(resource_type: type[Any]) -> object:
    return require_context().get_resource(resource_type)


def remove_resource(resource_type: type[Any]) -> None:
    require_context().remove_resource(resource_type)


def emit_event(event: object) -> None:
    require_context().emit_event(event)


def read_events(event_type: type[Any]) -> tuple[Any, ...]:
    return require_context().read_events(event_type)


def clear_events(event_type: type[Any] | None = None) -> None:
    require_context().clear_events(event_type)


def add_system(
    system: SystemDefinition,
    *,
    order: int = 0,
    enabled: bool = True,
    name: str | None = None,
    before: Iterable[SystemHandle | str] = (),
    after: Iterable[SystemHandle | str] = (),
    run_if: Callable[[], bool] | None = None,
    set: str | None = None,
) -> SystemHandle:
    return require_context().add_system(
        system,
        order=order,
        enabled=enabled,
        name=name,
        before=before,
        after=after,
        run_if=run_if,
        set=set,
    )


def remove_system(handle: SystemHandle | str) -> None:
    require_context().remove_system(handle)


def enable_system(handle: SystemHandle | str) -> None:
    require_context().enable_system(handle)


def disable_system(handle: SystemHandle | str) -> None:
    require_context().disable_system(handle)


def configure_ecs(*, strict: bool | None = None, warn_on_ambiguity: bool | None = None) -> None:
    require_context().configure_ecs(strict=strict, warn_on_ambiguity=warn_on_ambiguity)


def configure_system_set(
    name: str,
    *,
    order: int | None = None,
    enabled: bool | None = None,
    run_if: Callable[[], bool] | None = None,
) -> None:
    require_context().configure_system_set(name, order=order, enabled=enabled, run_if=run_if)


def ecs_diagnostics() -> dict[str, Any]:
    return require_context().ecs_diagnostics()


def reset_ecs_diagnostics() -> None:
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
    "emit_event",
    "iter_component_fields",
    "iter_entities",
    "remove_component",
    "read_events",
    "remove_resource",
    "remove_system",
    "remove_tag",
    "reset_ecs_diagnostics",
    "set_resource",
    "try_get_entity",
]
