"""ECS forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.world import Entity, EntityView, SystemHandle
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeEcsMixin(SketchFacadeBaseMixin):
    """Object-mode ECS convenience methods."""

    def add_entity(self, *components: object, tags: Iterable[object] = ()) -> Entity:
        return self._ctx.add_entity(*components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        self._ctx.despawn_entity(entity)

    def add_component(self, entity: Entity, component: object) -> None:
        self._ctx.add_component(entity, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        self._ctx.remove_component(entity, component_type)

    def add_tag(self, entity: Entity, tag: object) -> None:
        self._ctx.add_tag(entity, tag)

    def remove_tag(self, entity: Entity, tag: object) -> None:
        self._ctx.remove_tag(entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[object] = ()) -> EntityView:
        return self._ctx.get_entity(*components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> EntityView | None:
        return self._ctx.try_get_entity(*components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> Iterator[EntityView]:
        return self._ctx.iter_entities(*components, tags=tags)

    def set_resource(self, resource: object) -> None:
        self._ctx.set_resource(resource)

    def get_resource(self, resource_type: type[Any]) -> object:
        return self._ctx.get_resource(resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        self._ctx.remove_resource(resource_type)

    def emit_event(self, event: object) -> None:
        self._ctx.emit_event(event)

    def read_events(self, event_type: type[Any]) -> tuple[Any, ...]:
        return self._ctx.read_events(event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        self._ctx.clear_events(event_type)

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
        return self._ctx.add_system(
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
        self._ctx.remove_system(handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        self._ctx.enable_system(handle)

    def disable_system(self, handle: SystemHandle | str) -> None:
        self._ctx.disable_system(handle)

    def configure_ecs(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        self._ctx.configure_ecs(strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def configure_system_set(
        self,
        name: str,
        *,
        order: int | None = None,
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        self._ctx.configure_system_set(name, order=order, enabled=enabled, run_if=run_if)

    def ecs_diagnostics(self) -> dict[str, Any]:
        return self._ctx.ecs_diagnostics()

    def reset_ecs_diagnostics(self) -> None:
        self._ctx.reset_ecs_diagnostics()


__all__ = ["SketchFacadeEcsMixin"]
