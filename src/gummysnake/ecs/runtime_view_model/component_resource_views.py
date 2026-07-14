from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gummysnake.ecs.runtime_view_model.entity_mutation import (
    Entity,
    _copy_stored_value,
)
from gummysnake.ecs.schema_helpers import _schema_name, _validate_storage_value
from gummysnake.exceptions import MissingComponentError

if TYPE_CHECKING:
    from gummysnake.ecs.world_facade import EcsWorld


class ComponentView:
    """Rust-backed view for reading and writing one entity component."""

    __slots__ = (
        "_world",
        "_entity",
        "_component_type",
        "_schema_name",
        "_field_names",
        "_storage_types",
        "_rust",
        "_access_batch",
        "_query_key",
    )

    def __init__(
        self,
        world: EcsWorld,
        entity: Entity,
        component_type: type[Any],
        *,
        access_batch: Any | None = None,
        query_key: int | None = None,
    ) -> None:
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
        object.__setattr__(self, "_storage_types", world._schemas[component_type])
        object.__setattr__(self, "_rust", world._rust)
        object.__setattr__(self, "_access_batch", access_batch)
        object.__setattr__(self, "_query_key", query_key)

    def __getattr__(self, field_name: str) -> Any:
        """Read a component field by attribute name.

        Args:
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned value for that component field.
        """
        if field_name.startswith("__") or field_name not in self._field_names:
            raise AttributeError(field_name)
        access_batch = self._access_batch
        if access_batch is not None and getattr(access_batch, "active", False):
            from gummysnake.ecs.world_runtime.python_batch import _BATCH_MISS

            value = access_batch.get_field(
                self._query_key,
                self._entity,
                self._component_type,
                field_name,
            )
            if value is not _BATCH_MISS:
                return value
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
        _validate_storage_value(
            self._component_type,
            field_name,
            value,
            self._storage_types[field_name],
        )
        access_batch = self._access_batch
        if (
            access_batch is not None
            and getattr(access_batch, "active", False)
            and access_batch.set_field(
                self._query_key,
                self._entity,
                self._component_type,
                field_name,
                value,
            )
        ):
            return
        try:
            self._rust.set_field(
                self._entity.index,
                self._entity.generation,
                self._schema_name,
                field_name,
                _copy_stored_value(value),
            )
        except ValueError as exc:
            raise MissingComponentError(
                f"Entity {self._entity.index}:{self._entity.generation} does not have "
                f"component {self._component_type.__name__}."
            ) from exc
        self._world._note_field_update(self._entity, self._component_type)

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
