"""ECS methods for ``SketchContext``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from gummysnake.ecs.logical_plan.systems import SystemDefinition
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.ecs.world_facade import EcsWorld, Entity, EntityView, SystemHandle


class EcsContextMixin:
    """Context methods forwarding to the active ECS world."""

    ecs: EcsWorld

    def add_entity(self, *components: DataclassInstance, tags: Iterable[EcsTag] = ()) -> Entity:
        """Create an entity with components and optional tags.

        Args:
            components: Component dataclass instances to attach to the entity.
            tags: Optional tag values used for filtering queries.

        Returns:
            A stable handle for the created entity.
        """

        return self.ecs.add_entity(*components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        """Remove an entity from the ECS world.

        Args:
            entity: Entity handle returned by ``add_entity()`` or a query result.
        """

        self.ecs.despawn_entity(entity)

    def add_component(self, entity: Entity, component: DataclassInstance) -> None:
        """Attach a component instance to an existing entity.

        Args:
            entity: Entity to modify.
            component: Component dataclass instance to add.
        """

        self.ecs.add_component(entity, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        """Remove one component type from an entity.

        Args:
            entity: Entity to modify.
            component_type: Component class to remove.
        """

        self.ecs.remove_component(entity, component_type)

    def add_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Attach a tag to an entity.

        Args:
            entity: Entity to modify.
            tag: Tag value used by ECS queries.
        """

        self.ecs.add_tag(entity, tag)

    def remove_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Remove a tag from an entity.

        Args:
            entity: Entity to modify.
            tag: Tag value to remove.
        """

        self.ecs.remove_tag(entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
        """Return the first entity matching components and tags.

        Args:
            components: Component classes the entity must have.
            tags: Optional tag values the entity must have.

        Returns:
            A view for reading and writing the matched entity's components.
        """

        return self.ecs.get_entity(*components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> EntityView | None:
        """Return the first matching entity, or ``None`` when no entity matches.

        Args:
            components: Component classes the entity must have.
            tags: Optional tag values the entity must have.

        Returns:
            A matching entity view, or ``None``.
        """

        return self.ecs.try_get_entity(*components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> Iterator[EntityView]:
        """Iterate over entities matching components and tags.

        Args:
            components: Component classes each returned entity must have.
            tags: Optional tag values each returned entity must have.

        Returns:
            An iterator of entity views.
        """

        return self.ecs.iter_entities(*components, tags=tags)

    def iter_component_fields(
        self,
        component_type: type[Any],
        *field_names: str,
        tags: Iterable[EcsTag] = (),
    ) -> Iterator[tuple[Any, ...]]:
        """Iterate selected component fields without materializing full entities.

        Args:
            component_type: Component class containing the requested fields.
            field_names: Field names to read from each matching component.
            tags: Optional tag values each returned row must have.

        Returns:
            Tuples of field values in the same order as ``field_names``.
        """

        return self.ecs.iter_component_fields(component_type, *field_names, tags=tags)

    def set_resource(self, resource: DataclassInstance) -> None:
        """Insert or replace a singleton ECS resource.

        Args:
            resource: Resource dataclass instance to store.
        """

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
        """Remove a resource from the ECS world.

        Args:
            resource_type: Resource dataclass class to remove.
        """

        self.ecs.remove_resource(resource_type)

    def emit_event(self, event: EcsEventValue) -> None:
        """Emit an ECS event for systems and readers.

        Args:
            event: Event dataclass instance to enqueue.
        """

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
        """Clear queued ECS events.

        Args:
            event_type: Optional event class to clear. Leave as ``None`` to clear all events.
        """

        self.ecs.clear_events(event_type)

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
        """Schedule an ECS system to run before drawing.

        Args:
            system: System definition created with ``@ecs.system`` or ``@ecs.system_plan``.
            enabled: Whether the system starts enabled.
            name: Optional human-readable name for diagnostics and dependencies.
            before: Groups that should run after this system's implicit group.
            after: Groups that should run before this system's implicit group.
            run_if: Optional predicate checked before running the system.
            group: Optional explicit system group name or sequence of group names.

        Returns:
            A handle that can enable, disable, or remove the system later.
        """

        return self.ecs.add_system(
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

        self.ecs.remove_system(handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        """Enable a scheduled ECS system.

        Args:
            handle: System handle or registered system name.
        """

        self.ecs.enable_system(handle)

    def disable_system(self, handle: SystemHandle | str) -> None:
        """Disable a scheduled ECS system without removing it.

        Args:
            handle: System handle or registered system name.
        """

        self.ecs.disable_system(handle)

    def configure_ecs(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        """Configure ECS ambiguity handling.

        Args:
            strict: When true, reject ambiguous duplicate writes instead of warning.
            warn_on_ambiguity: Whether non-strict ambiguity diagnostics should log warnings.
        """

        self.ecs.configure(strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def group(
        self,
        name: str,
        *,
        before: Iterable[str] = (),
        after: Iterable[str] = (),
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        """Create or configure an ECS system group."""

        self.ecs.group(name, before=before, after=after, enabled=enabled, run_if=run_if)

    def order(self, groups: Iterable[str]) -> None:
        """Declare a left-to-right ordering for ECS system groups."""

        self.ecs.order(groups)

    def ecs_diagnostics(self) -> dict[str, Any]:
        """Return ECS counters and runtime diagnostics."""

        return self.ecs.diagnostics()

    def reset_ecs_diagnostics(self) -> None:
        """Reset ECS counters and diagnostics."""

        self.ecs.reset_diagnostics()

    def run_ecs_pre_draw(self) -> None:
        """Run scheduled ECS systems for the current pre-draw phase."""

        self.ecs.run_pre_draw_systems()


__all__ = ["EcsContextMixin"]
