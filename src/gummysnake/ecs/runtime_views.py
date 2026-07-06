"""Entity handles and Python runtime views for the ECS world."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

from gummysnake.ecs.schema_helpers import _schema_name
from gummysnake.ecs.systems import BuiltSystem
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.exceptions import MissingComponentError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld

ComponentT = TypeVar("ComponentT")
_ENTITY_MUTATION_COMPONENT_UNSET = object()


@dataclass(frozen=True)
class Entity:
    """Stable handle for an ECS entity stored in the Rust world."""

    index: int
    generation: int
    world_id: int

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        """Create an annotation marker such as ``ecs.Entity[Position]``."""
        return EntityAnnotation(item, mutable=False)

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Explain why raw entity handles cannot read components directly.

        Args:
            component_type: Component type requested with subscription syntax.

        Returns:
            This method always raises because component access needs an ``EntityView``.
        """
        del component_type
        raise TypeError(
            "ecs.Entity[...] is a Python UDF/system annotation marker. Runtime component "
            "access is available on EntityView objects materialized by explicit Python "
            "ECS boundaries."
        )

    def add_component(self, component: DataclassInstance) -> None:
        """Reject direct mutation and point callers to ``EntityView``."""
        del component
        raise TypeError("Raw Entity handles cannot mutate components directly; use EntityView.")

    def remove_component(self, component_type: type[Any]) -> None:
        """Reject direct mutation and point callers to ``EntityView``."""
        del component_type
        raise TypeError("Raw Entity handles cannot mutate components directly; use EntityView.")

    def add_tag(self, tag: EcsTag) -> None:
        """Reject direct tag mutation and point callers to ``EntityView``."""
        del tag
        raise TypeError("Raw Entity handles cannot mutate tags directly; use EntityView.")

    def remove_tag(self, tag: EcsTag) -> None:
        """Reject direct tag mutation and point callers to ``EntityView``."""
        del tag
        raise TypeError("Raw Entity handles cannot mutate tags directly; use EntityView.")

    def despawn(self) -> None:
        """Reject direct despawning and point callers to ``EntityView``."""
        raise TypeError("Raw Entity handles cannot despawn directly; use EntityView.")


@dataclass(frozen=True)
class EntityAnnotation:
    """Annotation marker created by ``ecs.Entity[Component]``.

    The marker is consumed when planning explicit Python ECS boundaries; raw entity
    handles still need an ``EntityView`` before component data can be read or changed.
    """

    component_type: object
    mutable: bool = False


@dataclass(frozen=True)
class EntityMutation:
    """Describe which component changes a Python ECS boundary may perform."""

    component_type: object = _ENTITY_MUTATION_COMPONENT_UNSET
    add: bool = False
    remove: bool = False
    update: bool = True

    def __post_init__(self) -> None:
        if self.component_type is _ENTITY_MUTATION_COMPONENT_UNSET:
            raise SystemPlanError(
                "EntityMutation must be parameterized as ecs.EntityMutation[Component](...)."
            )
        if not (self.add or self.remove or self.update):
            raise SystemPlanError(
                "EntityMutation must allow at least one of add, remove, or update."
            )

    def __class_getitem__(cls, item: object) -> _EntityMutationAlias:
        """Create a mutation descriptor factory for one component type."""
        return _EntityMutationAlias(item)


@dataclass(frozen=True)
class _EntityMutationAlias:
    component_type: object

    def __call__(
        self, *, add: bool = False, remove: bool = False, update: bool = True
    ) -> EntityMutation:
        return EntityMutation(self.component_type, add=add, remove=remove, update=update)


class MutEntity:
    """Deprecated mutable entity annotation marker."""

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        """Raise with migration guidance for old ``ecs.MutEntity[...]`` annotations."""
        raise SystemPlanError(
            "ecs.MutEntity has been replaced by ecs.Entity[...] plus EntityMutation[...] "
            "metadata on @ecs.udf(python=True) or @ecs.system(python=True)."
        )

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Raise with migration guidance for old runtime ``MutEntity`` access."""
        raise TypeError(
            "ecs.MutEntity is deprecated; use ecs.Entity[...] and EntityMutation metadata."
        )


class ComponentView:
    """Rust-backed view for reading and writing one entity component."""

    __slots__ = (
        "_world",
        "_entity",
        "_component_type",
        "_schema_name",
        "_field_names",
        "_rust",
    )

    def __init__(self, world: EcsWorld, entity: Entity, component_type: type[Any]) -> None:
        """Create a view for ``entity`` and ``component_type``.

        Args:
            world: ECS world that owns the entity.
            entity: Entity handle to read or mutate.
            component_type: Dataclass component type stored on the entity.
        """
        world.validate_schema(component_type)
        object.__setattr__(self, "_world", world)
        object.__setattr__(self, "_entity", entity)
        object.__setattr__(self, "_component_type", component_type)
        object.__setattr__(self, "_schema_name", _schema_name(component_type))
        object.__setattr__(self, "_field_names", frozenset(world._schemas[component_type]))
        object.__setattr__(self, "_rust", world._rust)

    def __getattr__(self, field_name: str) -> Any:
        """Read a component field by attribute name.

        Args:
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned value for that component field.
        """
        if field_name.startswith("__") or field_name not in self._field_names:
            raise AttributeError(field_name)
        try:
            return self._rust.get_field(
                self._entity.index,
                self._entity.generation,
                self._schema_name,
                field_name,
            )
        except ValueError as exc:
            raise MissingComponentError(
                f"Entity {self._entity.index}:{self._entity.generation} does not have "
                f"component {self._component_type.__name__}."
            ) from exc

    def __setattr__(self, field_name: str, value: object) -> None:
        """Write a component field by attribute name.

        Args:
            field_name: Dataclass field name to update.
            value: New value accepted by the component field storage type.
        """
        if field_name.startswith("_"):
            object.__setattr__(self, field_name, value)
            return
        if field_name not in self._field_names:
            raise AttributeError(field_name)
        self._world.set_component_field(self._entity, self._component_type, field_name, value)

    def snapshot(self) -> object:
        """Return a dataclass copy of this component's current fields.

        Returns:
            A new dataclass instance of the component type.
        """
        return self._world.component_snapshot(self._entity, self._component_type)

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this component view."""
        return (
            f"ComponentView({self._component_type.__name__}@"
            f"{self._entity.index}:{self._entity.generation})"
        )


class ResourceView:
    """Rust-backed view for reading and writing an ECS resource."""

    def __init__(self, world: EcsWorld, resource_type: type[Any]) -> None:
        """Create a view for one resource type.

        Args:
            world: ECS world that owns the resource.
            resource_type: Dataclass resource type to read or mutate.
        """
        object.__setattr__(self, "_world", world)
        object.__setattr__(self, "_resource_type", resource_type)

    def __getattr__(self, field_name: str) -> Any:
        """Read a resource field by attribute name.

        Args:
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned resource field value.
        """
        if field_name.startswith("__"):
            raise AttributeError(field_name)
        return self._world.get_resource_field(self._resource_type, field_name)

    def __setattr__(self, field_name: str, value: object) -> None:
        """Write a resource field by attribute name.

        Args:
            field_name: Dataclass field name to update.
            value: New value accepted by the resource field storage type.
        """
        if field_name.startswith("_"):
            object.__setattr__(self, field_name, value)
            return
        self._world.set_resource_field(self._resource_type, field_name, value)

    def snapshot(self) -> object:
        """Return a dataclass copy of this resource's current fields.

        Returns:
            A new dataclass instance of the resource type.
        """
        return self._world.resource_snapshot(self._resource_type)

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this resource view."""
        return f"ResourceView({self._resource_type.__name__})"


class EntityView:
    """Mutable Python view over one entity's components and tags."""

    def __init__(self, world: EcsWorld, entity: Entity) -> None:
        """Create a view for ``entity`` in ``world``.

        Args:
            world: ECS world that owns the entity.
            entity: Entity handle to read or mutate.
        """
        self._world = world
        self.entity = entity

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Return a component view using ``entity[Component]`` syntax.

        Args:
            component_type: Dataclass component type to access.

        Returns:
            A ``ComponentView`` typed as the requested component for user code.
        """
        return cast(ComponentT, ComponentView(self._world, self.entity, component_type))

    def __setitem__(self, component_type: type[Any], value: DataclassInstance) -> None:
        """Replace a component using ``entity[Component] = value`` syntax.

        Args:
            component_type: Component slot to replace.
            value: Dataclass instance to store in that slot.
        """
        self._world.set_component(self.entity, value, expected_type=component_type)

    def add_component(self, component: DataclassInstance) -> None:
        """Add or replace one component on the entity.

        Args:
            component: Dataclass component instance to store.
        """
        self._world.add_component(self.entity, component)

    def remove_component(self, component_type: type[Any]) -> None:
        """Remove one component type from the entity.

        Args:
            component_type: Dataclass component type to remove.
        """
        self._world.remove_component(self.entity, component_type)

    def add_tag(self, tag: EcsTag) -> None:
        """Add a tag value to the entity.

        Args:
            tag: Value converted to a non-empty string tag.
        """
        self._world.add_tag(self.entity, tag)

    def remove_tag(self, tag: EcsTag) -> None:
        """Remove a tag value from the entity.

        Args:
            tag: Value converted to the string tag to remove.
        """
        self._world.remove_tag(self.entity, tag)

    def __eq__(self, other: object) -> bool:
        """Compare entity views by the entity handle they wrap.

        Args:
            other: Object to compare with this view.

        Returns:
            ``True`` when both views wrap the same entity handle.
        """
        return isinstance(other, EntityView) and self.entity == other.entity

    def __hash__(self) -> int:
        """Return a hash based on the wrapped entity handle."""
        return hash(self.entity)

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this entity view."""
        return f"EntityView({self.entity.index}:{self.entity.generation})"


@dataclass(frozen=True)
class SystemHandle:
    """Identifier returned when a system is added to an ECS world."""

    id: int
    name: str


@dataclass
class _SystemSetConfig:
    order: int | None = None
    enabled: bool | None = None
    run_if: Callable[[], bool] | None = None


@dataclass
class _ScheduledSystem:
    handle: SystemHandle
    built: BuiltSystem
    order: int
    enabled: bool = True
    before: tuple[SystemHandle | str, ...] = ()
    after: tuple[SystemHandle | str, ...] = ()
    run_if: Callable[[], bool] | None = None
    set_name: str | None = None
    physical_payload: dict[str, Any] | None = None
    physical_plan_handle: int | None = None
    physical_payload_dynamic: bool = False
    physical_has_input_state: bool = False
    physical_schema_fingerprint: int | None = None


class _RuntimeEventWriter:
    def __init__(self, world: EcsWorld, event_type: type[Any]) -> None:
        self._world = world
        self._event_type = event_type

    def emit(self, event: EcsEventValue) -> None:
        self._world.emit_event(event, expected_type=self._event_type)


__all__ = [
    "Entity",
    "EntityAnnotation",
    "EntityMutation",
    "EntityView",
    "MutEntity",
    "SystemHandle",
]
