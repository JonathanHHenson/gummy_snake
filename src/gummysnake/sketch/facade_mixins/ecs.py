"""ECS forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.ecs.logical_plan.systems import SystemDefinition
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.ecs.world_facade import Entity, EntityView, SystemHandle
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeEcsMixin(SketchFacadeBaseMixin):
    """Object-mode ECS convenience methods."""

    def add_entity(self, *components: DataclassInstance, tags: Iterable[EcsTag] = ()) -> Entity:
        """Create an ECS entity from an object-mode sketch.

        Args:
            components: Component dataclass instances to attach.
            tags: Optional tag values for query filtering.

        Returns:
            A stable handle for the created entity.
        """

        return self._ctx.add_entity(*components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        """Remove an ECS entity from this sketch's world.

        Args:
            entity: Entity handle to remove.
        """

        self._ctx.despawn_entity(entity)

    def add_component(self, entity: Entity, component: DataclassInstance) -> None:
        """Attach a component to an entity in this sketch's ECS world.

        Args:
            entity: Entity to modify.
            component: Component dataclass instance to add.
        """

        self._ctx.add_component(entity, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        """Remove a component type from an entity.

        Args:
            entity: Entity to modify.
            component_type: Component class to remove.
        """

        self._ctx.remove_component(entity, component_type)

    def add_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Attach a query tag to an entity.

        Args:
            entity: Entity to modify.
            tag: Tag value to add.
        """

        self._ctx.add_tag(entity, tag)

    def remove_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Remove a query tag from an entity.

        Args:
            entity: Entity to modify.
            tag: Tag value to remove.
        """

        self._ctx.remove_tag(entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
        """Return the first entity matching components and tags.

        Args:
            components: Component classes the entity must have.
            tags: Optional tags the entity must have.

        Returns:
            A view for reading and writing the matched entity.
        """

        return self._ctx.get_entity(*components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> EntityView | None:
        """Return the first matching entity, or ``None``.

        Args:
            components: Component classes the entity must have.
            tags: Optional tags the entity must have.

        Returns:
            A matching entity view, or ``None``.
        """

        return self._ctx.try_get_entity(*components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> Iterator[EntityView]:
        """Iterate entities matching components and tags.

        Args:
            components: Component classes each entity must have.
            tags: Optional tags each entity must have.

        Returns:
            An iterator of entity views.
        """

        return self._ctx.iter_entities(*components, tags=tags)

    def set_resource(self, resource: DataclassInstance) -> None:
        """Insert or replace a singleton ECS resource.

        Args:
            resource: Resource dataclass instance to store.
        """

        self._ctx.set_resource(resource)

    def get_resource[ResourceT](self, resource_type: type[ResourceT]) -> ResourceT:
        """Return a mutable view for an existing ECS resource.

        Args:
            resource_type: Dataclass resource class to access.

        Returns:
            A resource view typed as ``resource_type`` for convenient field access.
        """

        return self._ctx.get_resource(resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        """Remove a singleton ECS resource.

        Args:
            resource_type: Resource dataclass class to remove.
        """

        self._ctx.remove_resource(resource_type)

    def emit_event(self, event: EcsEventValue) -> None:
        """Emit an ECS event from object-mode sketch code.

        Args:
            event: Event dataclass instance to enqueue.
        """

        self._ctx.emit_event(event)

    def read_events[EventT](self, event_type: type[EventT]) -> tuple[EventT, ...]:
        """Read events of one type emitted in the current ECS frame.

        Args:
            event_type: Dataclass event class to read.

        Returns:
            A tuple of copied event instances in emission order.
        """

        return self._ctx.read_events(event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        """Clear queued ECS events.

        Args:
            event_type: Optional event class to clear. Leave as ``None`` to clear all events.
        """

        self._ctx.clear_events(event_type)

    def add_system(
        self,
        system: SystemDefinition,
        *,
        enabled: bool = True,
        name: str | None = None,
        before: Iterable[str] = (),
        after: Iterable[str] = (),
        run_if: Callable[[], bool] | None = None,
        group: str | Iterable[str] | None = None,
    ) -> SystemHandle:
        """Schedule an ECS system for this sketch.

        Args:
            system: System definition created with ``@ecs.system`` or ``@ecs.system_plan``.
            enabled: Whether the system starts enabled.
            name: Optional name for diagnostics and dependency references.
            before: Groups that should run after this system's implicit group.
            after: Groups that should run before this system's implicit group.
            run_if: Optional predicate checked before running the system.
            group: Optional explicit system group name or sequence of group names.

        Returns:
            A handle for later system control.
        """

        return self._ctx.add_system(
            system,
            enabled=enabled,
            name=name,
            before=before,
            after=after,
            run_if=run_if,
            group=group,
        )

    def remove_system(self, handle: SystemHandle | str) -> None:
        """Remove a scheduled ECS system.

        Args:
            handle: System handle or registered system name.
        """

        self._ctx.remove_system(handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        """Enable a scheduled ECS system.

        Args:
            handle: System handle or registered system name.
        """

        self._ctx.enable_system(handle)

    def disable_system(self, handle: SystemHandle | str) -> None:
        """Disable a scheduled ECS system without removing it.

        Args:
            handle: System handle or registered system name.
        """

        self._ctx.disable_system(handle)

    def configure_ecs(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        """Configure ECS ambiguity behavior for this sketch.

        Args:
            strict: When true, reject ambiguous duplicate writes instead of warning.
            warn_on_ambiguity: Whether non-strict ambiguity diagnostics should log warnings.
        """

        self._ctx.configure_ecs(strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def group(
        self,
        name: str,
        *,
        before: Iterable[str] = (),
        after: Iterable[str] = (),
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        """Create or configure an ECS system group for this sketch."""

        self._ctx.group(name, before=before, after=after, enabled=enabled, run_if=run_if)

    def order(self, groups: Iterable[str]) -> None:
        """Declare a left-to-right ordering for ECS system groups."""

        self._ctx.order(groups)

    def ecs_diagnostics(self) -> dict[str, Any]:
        """Return ECS counters and runtime diagnostics for this sketch."""

        return self._ctx.ecs_diagnostics()

    def reset_ecs_diagnostics(self) -> None:
        """Reset ECS counters and diagnostics for this sketch."""

        self._ctx.reset_ecs_diagnostics()


__all__ = ["SketchFacadeEcsMixin"]
