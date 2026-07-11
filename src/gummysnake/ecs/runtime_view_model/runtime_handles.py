from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.runtime_view_model.component_resource_views import ComponentView
from gummysnake.ecs.runtime_view_model.entity_mutation import ComponentT, Entity
from gummysnake.ecs.systems import BuiltSystem
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag

if TYPE_CHECKING:
    from gummysnake.ecs.world import EcsWorld


class EntityView:
    """Mutable Python view over one entity's components and tags."""

    def __init__(
        self,
        world: EcsWorld,
        entity: Entity,
        *,
        access_batch: Any | None = None,
        query_key: int | None = None,
    ) -> None:
        """Create a view for ``entity`` in ``world``.

        Args:
            world: ECS world that owns the entity.
            entity: Entity handle to read or mutate.
        """
        self._world = world
        self.entity = entity
        self._access_batch = access_batch
        self._query_key = query_key

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Return a component view using ``entity[Component]`` syntax.

        Args:
            component_type: Dataclass component type to access.

        Returns:
            A ``ComponentView`` typed as the requested component for user code.
        """
        access_batch = self._access_batch
        if access_batch is not None and getattr(access_batch, "active", False):
            from gummysnake.ecs.world_runtime.python_batch import _BATCH_MISS

            proxy = access_batch.component_proxy(self._query_key, self.entity, component_type)
            if proxy is not _BATCH_MISS:
                return cast(ComponentT, proxy)
        return cast(
            ComponentT,
            ComponentView(
                self._world,
                self.entity,
                component_type,
                access_batch=access_batch,
                query_key=self._query_key,
            ),
        )

    def __setitem__(self, component_type: type[Any], value: DataclassInstance) -> None:
        """Replace a component using ``entity[Component] = value`` syntax.

        Args:
            component_type: Component slot to replace.
            value: Dataclass instance to store in that slot.
        """
        self._flush_access_batch()
        self._world.set_component(self.entity, value, expected_type=component_type)

    def add_component(self, component: DataclassInstance) -> None:
        """Add or replace one component on the entity.

        Args:
            component: Dataclass component instance to store.
        """
        self._flush_access_batch()
        self._world.add_component(self.entity, component)

    def remove_component(self, component_type: type[Any]) -> None:
        """Remove one component type from the entity.

        Args:
            component_type: Dataclass component type to remove.
        """
        self._flush_access_batch()
        self._world.remove_component(self.entity, component_type)

    def add_tag(self, tag: EcsTag) -> None:
        """Add a tag value to the entity.

        Args:
            tag: Value converted to a non-empty string tag.
        """
        self._flush_access_batch()
        self._world.add_tag(self.entity, tag)

    def remove_tag(self, tag: EcsTag) -> None:
        """Remove a tag value from the entity.

        Args:
            tag: Value converted to the string tag to remove.
        """
        self._flush_access_batch()
        self._world.remove_tag(self.entity, tag)

    def _flush_access_batch(self) -> None:
        access_batch = getattr(self, "_access_batch", None)
        if access_batch is not None and getattr(access_batch, "active", False):
            access_batch.flush()

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
    enabled: bool | None = None
    run_if: Callable[[], bool] | None = None
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()


@dataclass
class _ScheduledSystem:
    handle: SystemHandle
    built: BuiltSystem
    group_name: str
    enabled: bool = True
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    run_if: Callable[[], bool] | None = None
    group_names: tuple[str, ...] = ()
    physical_payload: dict[str, Any] | None = None
    physical_plan_handle: int | None = None
    physical_payload_dynamic: bool = False
    physical_has_input_state: bool = False
    physical_schema_fingerprint: int | None = None
    physical_warm_report: dict[str, Any] | None = None
    python_arg_plan: tuple[tuple[str, Any], ...] | None = None


class _RuntimeEventWriter:
    def __init__(self, world: EcsWorld, event_type: type[Any]) -> None:
        self._world = world
        self._event_type = event_type

    def emit(self, event: EcsEventValue) -> None:
        self._world.emit_event(event, expected_type=self._event_type)


__all__ = [
    "EntityView",
    "SystemHandle",
    "_RuntimeEventWriter",
    "_ScheduledSystem",
    "_SystemSetConfig",
]
