"""ECS methods for ``SketchContext``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.ecs.world import EcsWorld, Entity, EntityView, SystemHandle


class EcsContextMixin:
    """Context methods forwarding to the active ECS world."""

    ecs: EcsWorld

    def add_entity(self, *components: DataclassInstance, tags: Iterable[EcsTag] = ()) -> Entity:
        return self.ecs.add_entity(*components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        self.ecs.despawn_entity(entity)

    def add_component(self, entity: Entity, component: DataclassInstance) -> None:
        self.ecs.add_component(entity, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        self.ecs.remove_component(entity, component_type)

    def add_tag(self, entity: Entity, tag: EcsTag) -> None:
        self.ecs.add_tag(entity, tag)

    def remove_tag(self, entity: Entity, tag: EcsTag) -> None:
        self.ecs.remove_tag(entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
        return self.ecs.get_entity(*components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> EntityView | None:
        return self.ecs.try_get_entity(*components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> Iterator[EntityView]:
        return self.ecs.iter_entities(*components, tags=tags)

    def iter_component_fields(
        self,
        component_type: type[Any],
        *field_names: str,
        tags: Iterable[EcsTag] = (),
    ) -> Iterator[tuple[Any, ...]]:
        return self.ecs.iter_component_fields(component_type, *field_names, tags=tags)

    def set_resource(self, resource: DataclassInstance) -> None:
        self.ecs.set_resource(resource)

    def get_resource[ResourceT](self, resource_type: type[ResourceT]) -> ResourceT:
        """Return a mutable view for an existing ECS resource.

        Args:
            resource_type: Dataclass resource class to access.

        Returns:
            A resource view typed as ``resource_type`` for convenient field access.
        """

        return self.ecs.get_resource(resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        self.ecs.remove_resource(resource_type)

    def emit_event(self, event: EcsEventValue) -> None:
        self.ecs.emit_event(event)

    def read_events[EventT](self, event_type: type[EventT]) -> tuple[EventT, ...]:
        """Read events of one type emitted in the current ECS frame.

        Args:
            event_type: Dataclass event class to read.

        Returns:
            A tuple of copied event instances in emission order.
        """

        return self.ecs.read_events(event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        self.ecs.clear_events(event_type)

    def add_system(
        self,
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
        return self.ecs.add_system(
            system,
            order=order,
            enabled=enabled,
            name=name,
            before=before,
            after=after,
            run_if=run_if,
            set=set,
        )

    def remove_system(self, handle: SystemHandle | str) -> None:
        self.ecs.remove_system(handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        self.ecs.enable_system(handle)

    def disable_system(self, handle: SystemHandle | str) -> None:
        self.ecs.disable_system(handle)

    def configure_ecs(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        self.ecs.configure(strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def configure_system_set(
        self,
        name: str,
        *,
        order: int | None = None,
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        self.ecs.configure_system_set(name, order=order, enabled=enabled, run_if=run_if)

    def ecs_diagnostics(self) -> dict[str, Any]:
        return self.ecs.diagnostics()

    def reset_ecs_diagnostics(self) -> None:
        self.ecs.reset_diagnostics()

    def run_ecs_pre_draw(self) -> None:
        self.ecs.run_pre_draw_systems()


__all__ = ["EcsContextMixin"]
