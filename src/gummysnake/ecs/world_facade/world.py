from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar

from gummysnake.ecs.action_model.nodes import Action, UdfArgument
from gummysnake.ecs.expressions import Expression, FieldExpression, QueryProxy
from gummysnake.ecs.runtime_views import (
    Entity,
    EntityView,
    SystemHandle,
    _ScheduledSystem,
    _SystemSetConfig,
)
from gummysnake.ecs.scheduling_helpers import sorted_scheduled_systems, validate_group_name
from gummysnake.ecs.schema_helpers import _schema_name
from gummysnake.ecs.specifications import QuerySpec
from gummysnake.ecs.system_model.definitions import SystemDefinition
from gummysnake.ecs.types import StorageType
from gummysnake.ecs.world_facade import initialization, schema_validation
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsStoredValue, EcsTag
from gummysnake.ecs.world_runtime import entities as entity_runtime
from gummysnake.ecs.world_runtime import query as query_runtime
from gummysnake.ecs.world_runtime import resources as resource_runtime
from gummysnake.ecs.world_runtime import state as state_runtime
from gummysnake.ecs.world_runtime import systems as system_runtime


if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.context import SketchContext

ComponentT = TypeVar("ComponentT")
ResourceT = TypeVar("ResourceT")


class EcsWorld:
    """Deterministic ECS world owned by one ``SketchContext``."""

    if TYPE_CHECKING:
        context: SketchContext | None
        _world_id: int
        _rust: Any
        _systems: list[_ScheduledSystem]
        _system_sets: dict[str, _SystemSetConfig]
        _group_orders: list[tuple[str, ...]]
        _next_system_id: int
        strict: bool
        warn_on_ambiguity: bool
        _diagnostics: Counter[str]
        _messages: list[str]
        _schemas: dict[type[Any], dict[str, StorageType]]
        _spatial_epoch: int
        _spatial_index_cache: dict[object, object]
        _spatial_relation_cache: dict[object, object]
        _spatial_aggregate_cache: dict[object, object]
        _expression_eval_cache: dict[object, object]
        _defer_spatial_invalidation: bool
        _spatial_invalidated_deferred: bool
        _ecs_frame: int
        _added_components: set[tuple[int, int, type[Any]]]
        _changed_components: set[tuple[int, int, type[Any]]]
        _removed_components: set[tuple[int, int, type[Any]]]
        _events: dict[type[Any], list[tuple[int, object]]]
        _event_types: dict[str, type[Any]]
        _has_change_filtered_systems_cache: bool | None
        _active_python_access_batch: Any | None

    def __init__(self, context: SketchContext | None = None) -> None:
        initialization.initialize_world(self, context)

    # -------------------------------------------------------------- diagnostics
    def configure(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        """Configure duplicate-write handling for this ECS world."""

        state_runtime.configure(self, strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def diagnostics(self) -> dict[str, Any]:
        """Return ECS counters and diagnostic messages."""

        return state_runtime.diagnostics(self)

    def reset_diagnostics(self) -> None:
        """Reset ECS diagnostic counters and messages."""

        state_runtime.reset_diagnostics(self)

    def record_ambiguity(self, message: str) -> None:
        """Record an ambiguity diagnostic message."""

        state_runtime.record_ambiguity(self, message)

    def _note_field_update(self, entity: Entity, component_type: type[Any]) -> None:
        state_runtime.note_field_update(self, entity, component_type)

    def _note_resource_update(self) -> None:
        state_runtime.note_resource_update(self)

    def _invalidate_spatial_indexes(self, *, clear_only: bool = False) -> None:
        state_runtime.invalidate_spatial_indexes(self, clear_only=clear_only)

    def configure_system_set(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        """Deprecated alias for ``group(name, enabled=..., run_if=...)``."""

        self.group(name, enabled=enabled, run_if=run_if)

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

        state_runtime.configure_system_group(
            self,
            name,
            before=tuple(before),
            after=tuple(after),
            enabled=enabled,
            run_if=run_if,
        )

    def order(self, groups: Iterable[str]) -> None:
        """Declare a left-to-right ordering for ECS system groups."""

        normalized = tuple(validate_group_name(group_name) for group_name in groups)
        state_runtime.configure_group_order(self, normalized)

    def _system_enabled(self, scheduled: _ScheduledSystem) -> bool:
        return state_runtime.system_enabled(self, scheduled)

    def _system_run_condition(self, scheduled: _ScheduledSystem) -> bool:
        return state_runtime.system_run_condition(self, scheduled)

    def _sorted_systems(self) -> list[_ScheduledSystem]:
        return sorted_scheduled_systems(self._systems, self._system_sets, self._group_orders)

    def _begin_change_frame(self) -> None:
        state_runtime.begin_change_frame(self)

    def _finalize_change_frame(self) -> None:
        state_runtime.finalize_change_frame(self)

    def _mark_component_added(self, entity: Entity, component_type: type[Any]) -> None:
        state_runtime.mark_component_added(self, entity, component_type)

    def _mark_component_changed(self, entity: Entity, component_type: type[Any]) -> None:
        state_runtime.mark_component_changed(self, entity, component_type)

    def _mark_component_removed(self, entity: Entity, component_type: type[Any]) -> None:
        state_runtime.mark_component_removed(self, entity, component_type)

    def _set_system_enabled(self, handle: SystemHandle | str, enabled: bool) -> None:
        state_runtime.set_system_enabled(self, handle, enabled)

    # ------------------------------------------------------------------ schema
    def validate_schema(self, component_type: type[Any]) -> dict[str, StorageType]:
        """Validate and cache a dataclass ECS schema.

        Args:
            component_type: Dataclass type used as a component, resource, or event payload.

        Returns:
            Mapping from dataclass field names to Rust storage types.
        """

        return schema_validation.validate_schema(self, component_type)

    def _validate_value(
        self, value: DataclassInstance, expected_type: type[Any] | None = None
    ) -> None:
        schema_validation.validate_value(self, value, expected_type)

    # ---------------------------------------------------------------- entities
    def add_entity(self, *components: DataclassInstance, tags: Iterable[EcsTag] = ()) -> Entity:
        """Create an entity with dataclass components and optional tags.

        Args:
            components: Dataclass component instances to attach to the new entity.
            tags: Optional tag values used for query filtering.

        Returns:
            A stable handle for the new Rust-owned entity.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.add_entity(self, *components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        """Remove an entity and all of its components.

        Args:
            entity: Entity handle that belongs to this world.
        """

        self._flush_active_python_access_batch()
        entity_runtime.despawn_entity(self, entity)

    def add_component(self, entity: Entity, component: DataclassInstance) -> None:
        """Add or replace a dataclass component on an entity.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
        """

        self._flush_active_python_access_batch()
        entity_runtime.add_component(self, entity, component)

    def set_component(
        self,
        entity: Entity,
        component: DataclassInstance,
        *,
        expected_type: type[Any] | None = None,
    ) -> None:
        """Store a component value in a specific component slot.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
            expected_type: Component class for assignment through typed view APIs.
        """

        self._flush_active_python_access_batch()
        entity_runtime.set_component(self, entity, component, expected_type=expected_type)

    def _upsert_component(
        self, entity: Entity, component_type: type[Any], component: DataclassInstance
    ) -> None:
        self._flush_active_python_access_batch()
        entity_runtime.upsert_component(self, entity, component_type, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        """Remove one component type from an entity.

        Args:
            entity: Entity handle to update.
            component_type: Dataclass component class to remove.
        """

        self._flush_active_python_access_batch()
        entity_runtime.remove_component(self, entity, component_type)

    def add_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Add a tag to an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to a string tag for filtering queries.
        """

        self._flush_active_python_access_batch()
        entity_runtime.add_tag(self, entity, tag)

    def remove_tag(self, entity: Entity, tag: EcsTag) -> None:
        """Remove a tag from an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to the string tag to remove.
        """

        self._flush_active_python_access_batch()
        entity_runtime.remove_tag(self, entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
        """Return the single entity matching component and tag filters.

        Args:
            components: Component classes that the entity must have.
            tags: Tag values that the entity must have.

        Returns:
            An ``EntityView`` for the matching entity.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.get_entity(self, *components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> EntityView | None:
        """Return zero or one entity matching component and tag filters.

        Args:
            components: Component classes that the entity must have.
            tags: Tag values that the entity must have.

        Returns:
            An ``EntityView`` when exactly one entity matches, or ``None`` when no entity matches.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.try_get_entity(self, *components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[EcsTag] = ()
    ) -> Iterator[EntityView]:
        """Iterate entities matching component and tag filters.

        Args:
            components: Component classes that each entity must have.
            tags: Tag values that each entity must have.

        Returns:
            An iterator of ``EntityView`` objects in deterministic entity order.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.iter_entities(self, *components, tags=tags)

    def iter_component_fields(
        self,
        component_type: type[Any],
        *field_names: str,
        tags: Iterable[EcsTag] = (),
    ) -> Iterator[tuple[Any, ...]]:
        """Read selected component fields with one Rust-backed batch call.

        Args:
            component_type: Dataclass component class to read.
            field_names: Names of fields to include in each returned tuple.
            tags: Optional tag values that each entity must have.

        Returns:
            An iterator of tuples whose values match ``field_names`` order.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.iter_component_fields(self, component_type, *field_names, tags=tags)

    def _slot(self, entity: Entity) -> None:
        entity_runtime.slot(self, entity)

    def _has_component(self, entity: Entity, component_type: type[Any]) -> bool:
        return entity_runtime.has_component(self, entity, component_type)

    def get_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str
    ) -> EcsStoredValue:
        """Read one field from an entity component.

        Args:
            entity: Entity handle whose component should be read.
            component_type: Dataclass component class that owns the field.
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned field value.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.get_component_field(self, entity, component_type, field_name)

    def set_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str, value: EcsStoredValue
    ) -> None:
        """Write one field on an entity component.

        Args:
            entity: Entity handle whose component should be updated.
            component_type: Dataclass component class that owns the field.
            field_name: Dataclass field name to update.
            value: New value accepted by the field's ECS storage type.
        """

        self._flush_active_python_access_batch()
        entity_runtime.set_component_field(self, entity, component_type, field_name, value)

    def component_snapshot(self, entity: Entity, component_type: type[Any]) -> DataclassInstance:
        """Copy a component's current fields into a new dataclass instance.

        Args:
            entity: Entity handle whose component should be copied.
            component_type: Dataclass component class to copy.

        Returns:
            A new dataclass instance of ``component_type``.
        """

        self._flush_active_python_access_batch()
        return entity_runtime.component_snapshot(self, entity, component_type)

    # --------------------------------------------------------------- resources
    def set_resource(self, resource: DataclassInstance) -> None:
        """Store a dataclass singleton resource in the ECS world.

        Args:
            resource: Dataclass resource instance to store or replace.
        """

        self._flush_active_python_access_batch()
        resource_runtime.set_resource(self, resource)

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        """Return a mutable view for an existing resource.

        Args:
            resource_type: Dataclass resource class to access.

        Returns:
            A resource view typed as ``resource_type`` for field access.
        """

        self._flush_active_python_access_batch()
        return resource_runtime.get_resource(self, resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        """Remove a resource from the ECS world.

        Args:
            resource_type: Dataclass resource class to remove.
        """

        self._flush_active_python_access_batch()
        resource_runtime.remove_resource(self, resource_type)

    def get_resource_field(self, resource_type: type[Any], field_name: str) -> EcsStoredValue:
        """Read one field from an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned resource field value.
        """

        self._flush_active_python_access_batch()
        return resource_runtime.get_resource_field(self, resource_type, field_name)

    def set_resource_field(
        self, resource_type: type[Any], field_name: str, value: EcsStoredValue
    ) -> None:
        """Write one field on an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to update.
            value: New value accepted by the field's ECS storage type.
        """

        self._flush_active_python_access_batch()
        resource_runtime.set_resource_field(self, resource_type, field_name, value)

    def resource_snapshot(self, resource_type: type[Any]) -> DataclassInstance:
        """Copy a resource's current fields into a new dataclass instance.

        Args:
            resource_type: Dataclass resource class to copy.

        Returns:
            A new dataclass instance of ``resource_type``.
        """

        self._flush_active_python_access_batch()
        return resource_runtime.resource_snapshot(self, resource_type)

    # ---------------------------------------------------------------- events
    def emit_event(self, event: EcsEventValue, *, expected_type: type[Any] | None = None) -> None:
        """Queue an ECS event for readers in the current frame.

        Args:
            event: Dataclass event instance to enqueue.
            expected_type: Optional event class used when a typed writer validates payloads.
        """

        resource_runtime.emit_event(self, event, expected_type=expected_type)

    def read_events(self, event_type: type[ComponentT]) -> tuple[ComponentT, ...]:
        """Read queued events of one dataclass type.

        Args:
            event_type: Dataclass event class to read.

        Returns:
            A tuple of copied event instances in emission order.
        """

        return resource_runtime.read_events(self, event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        """Clear queued ECS events.

        Args:
            event_type: Event class to clear, or ``None`` to clear all event types.
        """

        resource_runtime.clear_events(self, event_type)

    # ---------------------------------------------------------------- systems
    def add_system(
        self,
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
        """Register an ``@ecs.system`` or ``@ecs.system_plan`` with this world.

        Args:
            system: Function decorated with ``@ecs.system`` or ``@ecs.system_plan``.
            enabled: Whether the system should run immediately after registration.
            name: Optional unique system name. Defaults to the decorated function name.
            before: Groups that should run after this system's implicit group.
            after: Groups that should run before this system's implicit group.
            run_if: Optional callback checked before each scheduled run.
            set: Deprecated alias for ``group``.
            group: Optional system group name or sequence of group names. Defaults to
                ``system_<system_name>``.

        Returns:
            A handle that can enable, disable, or remove the registered system.
        """

        return system_runtime.add_system(
            self,
            system,
            enabled=enabled,
            name=name,
            before=tuple(before),
            after=tuple(after),
            run_if=run_if,
            group_name=group if group is not None else set,
        )

    def remove_system(self, handle: SystemHandle | str) -> None:
        """Unregister a scheduled ECS system.

        Args:
            handle: System handle or system name returned by ``add_system()``.
        """

        system_runtime.remove_system(self, handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        """Allow a scheduled ECS system to run again.

        Args:
            handle: System handle or system name to enable.
        """

        state_runtime.set_system_enabled(self, handle, True)

    def disable_system(self, handle: SystemHandle | str) -> None:
        """Temporarily prevent a scheduled ECS system from running.

        Args:
            handle: System handle or system name to disable.
        """

        state_runtime.set_system_enabled(self, handle, False)

    def run_pre_draw_systems(self) -> None:
        """Run enabled ECS systems once using the sketch pre-draw lifecycle order."""

        system_runtime.run_pre_draw_systems(self)

    def _run_sorted_systems(self) -> None:
        system_runtime.run_sorted_systems(self)

    def _run_system_action(self, scheduled: _ScheduledSystem, action: Action) -> None:
        system_runtime.run_system_action(self, scheduled, action)

    def _has_change_filtered_systems(self) -> bool:
        return system_runtime.has_change_filtered_systems(self)

    def match_query(self, spec: QuerySpec) -> list[EntityView]:
        """Return entity views that satisfy ``spec`` in deterministic order."""

        self._flush_active_python_access_batch()
        return query_runtime.match_query(self, spec)

    def iter_join_contexts_for(
        self,
        base_ctx: dict[object, Any],
        expr: Expression,
        *,
        include_query: QueryProxy | None = None,
    ) -> Iterator[dict[object, Any]]:
        """Yield query-binding contexts needed to evaluate ``expr``."""

        yield from query_runtime.iter_join_contexts_for(
            self, base_ctx, expr, include_query=include_query
        )

    def iter_join_contexts_for_queries(
        self, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
    ) -> Iterator[dict[object, Any]]:
        """Yield query-binding contexts for the requested query proxies."""

        yield from query_runtime.iter_join_contexts_for_queries(self, base_ctx, queries)

    def write_key(
        self, target: FieldExpression, ctx: dict[object, Any]
    ) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
        """Build the entity/resource, component, and field key for a write."""

        return query_runtime.write_key(target, ctx)

    def check_parallel_children(self, children: tuple[Action, ...]) -> None:
        """Validate that parallel child actions do not contain ambiguous writes."""

        query_runtime.check_parallel_children(self, children)

    def materialize_udf_arg(self, arg: UdfArgument) -> query_runtime.MaterializedUdfArgument:
        """Convert a UDF argument descriptor into the value passed to Python."""

        return query_runtime.materialize_udf_arg(self, arg)

    def _register_event_type(self, event_type: type[Any]) -> None:
        resource_runtime.register_event_type(self, event_type)

    def _flush_active_python_access_batch(self) -> None:
        batch = self._active_python_access_batch
        if batch is not None and getattr(batch, "active", False):
            batch.flush()

    # -------------------------------------------------------------- Rust sync
    def _sync_component_fields_to_rust(
        self, entity: Entity, component_type: type[Any], component: DataclassInstance
    ) -> None:
        entity_runtime.sync_component_fields_to_rust(self, entity, component_type, component)

    def _sync_component_field_to_rust(
        self, entity: Entity, component_type: type[Any], field_name: str, value: EcsStoredValue
    ) -> None:
        entity_runtime.sync_component_field_to_rust(self, entity, component_type, field_name, value)

    def _component_type_for_schema(self, schema_name: str) -> type[Any]:
        return entity_runtime.component_type_for_schema(self, schema_name)
