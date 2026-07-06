"""Python-facing ECS world and entity APIs.

Rust owns canonical ECS entity/component/resource storage and physical system execution. This module
keeps the public Python API, schema conversion, logical-plan construction, and explicit Python UDF
integration at the boundary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import fields, is_dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    get_type_hints,
)

from gummysnake.ecs.actions import Action
from gummysnake.ecs.expressions import (
    Expression,
    FieldExpression,
    QueryProxy,
)
from gummysnake.ecs.runtime_views import (
    Entity,
    EntityMutation,
    EntityView,
    MutEntity,
    SystemHandle,
    _ScheduledSystem,
    _SystemSetConfig,
)
from gummysnake.ecs.scheduling_helpers import sorted_scheduled_systems
from gummysnake.ecs.schema_helpers import (
    _schema_name,
    _storage_type_for,
    _validate_storage_value,
)
from gummysnake.ecs.specs import QuerySpec
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.types import StorageType
from gummysnake.ecs.world_runtime.entities import (
    add_component as add_component_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    add_entity as add_entity_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    add_tag as add_tag_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    component_snapshot as component_snapshot_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    component_type_for_schema as component_type_for_schema_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    despawn_entity as despawn_entity_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    get_component_field as get_component_field_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    get_entity as get_entity_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    has_component as has_component_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    iter_component_fields as iter_component_fields_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    iter_entities as iter_entities_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    remove_component as remove_component_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    remove_tag as remove_tag_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    set_component as set_component_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    set_component_field as set_component_field_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    slot as slot_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    sync_component_field_to_rust as sync_component_field_to_rust_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    sync_component_fields_to_rust as sync_component_fields_to_rust_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    try_get_entity as try_get_entity_runtime,
)
from gummysnake.ecs.world_runtime.entities import (
    upsert_component as upsert_component_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    check_parallel_children as check_parallel_children_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    iter_join_contexts_for as iter_join_contexts_for_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    iter_join_contexts_for_queries as iter_join_contexts_for_queries_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    match_query as match_query_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    materialize_udf_arg as materialize_udf_arg_runtime,
)
from gummysnake.ecs.world_runtime.query import (
    write_key as write_key_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    clear_events as clear_events_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    emit_event as emit_event_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    get_resource as get_resource_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    get_resource_field as get_resource_field_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    read_events as read_events_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    register_event_type as register_event_type_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    remove_resource as remove_resource_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    resource_snapshot as resource_snapshot_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    set_resource as set_resource_runtime,
)
from gummysnake.ecs.world_runtime.resources import (
    set_resource_field as set_resource_field_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    begin_change_frame as begin_change_frame_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    configure as configure_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    configure_system_set as configure_system_set_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    diagnostics as diagnostics_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    finalize_change_frame as finalize_change_frame_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    invalidate_spatial_indexes as invalidate_spatial_indexes_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    mark_component_added as mark_component_added_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    mark_component_changed as mark_component_changed_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    mark_component_removed as mark_component_removed_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    note_field_update as note_field_update_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    note_resource_update as note_resource_update_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    record_ambiguity as record_ambiguity_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    reset_diagnostics as reset_diagnostics_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    set_system_enabled as set_system_enabled_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    system_enabled as system_enabled_runtime,
)
from gummysnake.ecs.world_runtime.state import (
    system_run_condition as system_run_condition_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    add_system as add_system_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    has_change_filtered_systems as has_change_filtered_systems_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    remove_system as remove_system_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    run_pre_draw_systems as run_pre_draw_systems_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    run_sorted_systems as run_sorted_systems_runtime,
)
from gummysnake.ecs.world_runtime.systems import (
    run_system_action as run_system_action_runtime,
)
from gummysnake.exceptions import ComponentSchemaError
from gummysnake.rust.ecs import create_ecs_world

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.context import SketchContext

ComponentT = TypeVar("ComponentT")
ResourceT = TypeVar("ResourceT")


class EcsWorld:
    """Deterministic ECS world owned by one ``SketchContext``."""

    def __init__(self, context: SketchContext | None = None) -> None:
        self.context = context
        self._world_id = id(self)
        self._rust = create_ecs_world()
        self._systems: list[_ScheduledSystem] = []
        self._system_sets: dict[str, _SystemSetConfig] = {}
        self._next_system_id = 1
        self.strict = False
        self.warn_on_ambiguity = True
        self._diagnostics: Counter[str] = Counter()
        self._messages: list[str] = []
        self._schemas: dict[type[Any], dict[str, StorageType]] = {}
        self._spatial_epoch = 0
        self._spatial_index_cache: dict[object, object] = {}
        self._spatial_relation_cache: dict[object, object] = {}
        self._spatial_aggregate_cache: dict[object, object] = {}
        self._expression_eval_cache: dict[object, object] = {}
        self._defer_spatial_invalidation = False
        self._spatial_invalidated_deferred = False
        self._ecs_frame = 0
        self._added_components: set[tuple[int, int, type[Any]]] = set()
        self._changed_components: set[tuple[int, int, type[Any]]] = set()
        self._removed_components: set[tuple[int, int, type[Any]]] = set()
        self._events: dict[type[Any], list[tuple[int, object]]] = {}
        self._event_types: dict[str, type[Any]] = {}
        self._has_change_filtered_systems_cache: bool | None = None

    # ------------------------------------------------------------------ schema
    def validate_schema(self, component_type: type[Any]) -> dict[str, StorageType]:
        cached = self._schemas.get(component_type)
        if cached is not None:
            return cached
        if not is_dataclass(component_type):
            raise ComponentSchemaError(
                f"ECS components/resources must be dataclasses; got {component_type!r}."
            )
        hints = get_type_hints(component_type, include_extras=True)
        schema: dict[str, StorageType] = {}
        for field in fields(component_type):
            annotation = hints.get(field.name, field.type)
            schema[field.name] = _storage_type_for(annotation, component_type, field.name)
        try:
            self._rust.register_schema(
                _schema_name(component_type),
                [(field_name, storage_type.name) for field_name, storage_type in schema.items()],
            )
        except ValueError as exc:
            if "unknown ECS storage type" not in str(exc):
                raise
            # Older editable builds may expose the ECS ABI before vector/list markers were added.
            # Keep Python-side schema validation functional; a rebuilt Rust bridge records the
            # exact storage names.
            self._diagnostics["ecs_rust_schema_registration_fallbacks"] += 1
        self._schemas[component_type] = schema
        self._diagnostics["ecs_component_schemas_total"] = len(self._schemas)
        self._diagnostics["ecs_rust_component_schemas_total"] = self._rust.schema_count()
        return schema

    def _validate_value(self, value: object, expected_type: type[Any] | None = None) -> None:
        component_type = expected_type or type(value)
        self.validate_schema(component_type)
        if not is_dataclass(value):
            raise ComponentSchemaError(
                f"ECS component values must be dataclass instances: {value!r}."
            )
        if type(value) is not component_type:
            raise ComponentSchemaError(
                f"Expected {component_type.__name__}, got {type(value).__name__}."
            )
        for field_name, storage_type in self._schemas[component_type].items():
            raw = getattr(value, field_name)
            _validate_storage_value(component_type, field_name, raw, storage_type)

    # ---------------------------------------------------------------- entities
    def add_entity(self, *components: object, tags: Iterable[object] = ()) -> Entity:
        """Create an entity with dataclass components and optional tags.

        Args:
            components: Dataclass component instances to attach to the new entity.
            tags: Optional tag values used for query filtering.

        Returns:
            A stable handle for the new Rust-owned entity.
        """

        return add_entity_runtime(self, *components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        """Remove an entity and all of its components.

        Args:
            entity: Entity handle that belongs to this world.
        """

        despawn_entity_runtime(self, entity)

    def add_component(self, entity: Entity, component: object) -> None:
        """Add or replace a dataclass component on an entity.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
        """

        add_component_runtime(self, entity, component)

    def set_component(
        self, entity: Entity, component: object, *, expected_type: type[Any] | None = None
    ) -> None:
        """Store a component value in a specific component slot.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
            expected_type: Component class for assignment through typed view APIs.
        """

        set_component_runtime(self, entity, component, expected_type=expected_type)

    def _upsert_component(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        upsert_component_runtime(self, entity, component_type, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        """Remove one component type from an entity.

        Args:
            entity: Entity handle to update.
            component_type: Dataclass component class to remove.
        """

        remove_component_runtime(self, entity, component_type)

    def add_tag(self, entity: Entity, tag: object) -> None:
        """Add a tag to an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to a string tag for filtering queries.
        """

        add_tag_runtime(self, entity, tag)

    def remove_tag(self, entity: Entity, tag: object) -> None:
        """Remove a tag from an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to the string tag to remove.
        """

        remove_tag_runtime(self, entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[object] = ()) -> EntityView:
        """Return the single entity matching component and tag filters.

        Args:
            components: Component classes that the entity must have.
            tags: Tag values that the entity must have.

        Returns:
            An ``EntityView`` for the matching entity.
        """

        return get_entity_runtime(self, *components, tags=tags)

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> EntityView | None:
        """Return zero or one entity matching component and tag filters.

        Args:
            components: Component classes that the entity must have.
            tags: Tag values that the entity must have.

        Returns:
            An ``EntityView`` when exactly one entity matches, or ``None`` when no entity matches.
        """

        return try_get_entity_runtime(self, *components, tags=tags)

    def iter_entities(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> Iterator[EntityView]:
        """Iterate entities matching component and tag filters.

        Args:
            components: Component classes that each entity must have.
            tags: Tag values that each entity must have.

        Returns:
            An iterator of ``EntityView`` objects in deterministic entity order.
        """

        return iter_entities_runtime(self, *components, tags=tags)

    def iter_component_fields(
        self,
        component_type: type[Any],
        *field_names: str,
        tags: Iterable[object] = (),
    ) -> Iterator[tuple[Any, ...]]:
        """Read selected component fields with one Rust-backed batch call.

        Args:
            component_type: Dataclass component class to read.
            field_names: Names of fields to include in each returned tuple.
            tags: Optional tag values that each entity must have.

        Returns:
            An iterator of tuples whose values match ``field_names`` order.
        """

        return iter_component_fields_runtime(self, component_type, *field_names, tags=tags)

    def _slot(self, entity: Entity) -> None:
        slot_runtime(self, entity)

    def _has_component(self, entity: Entity, component_type: type[Any]) -> bool:
        return has_component_runtime(self, entity, component_type)

    def get_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str
    ) -> Any:
        """Read one field from an entity component.

        Args:
            entity: Entity handle whose component should be read.
            component_type: Dataclass component class that owns the field.
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned field value.
        """

        return get_component_field_runtime(self, entity, component_type, field_name)

    def set_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str, value: object
    ) -> None:
        """Write one field on an entity component.

        Args:
            entity: Entity handle whose component should be updated.
            component_type: Dataclass component class that owns the field.
            field_name: Dataclass field name to update.
            value: New value accepted by the field's ECS storage type.
        """

        set_component_field_runtime(self, entity, component_type, field_name, value)

    def component_snapshot(self, entity: Entity, component_type: type[Any]) -> object:
        """Copy a component's current fields into a new dataclass instance.

        Args:
            entity: Entity handle whose component should be copied.
            component_type: Dataclass component class to copy.

        Returns:
            A new dataclass instance of ``component_type``.
        """

        return component_snapshot_runtime(self, entity, component_type)

    # --------------------------------------------------------------- resources
    def set_resource(self, resource: object) -> None:
        """Store a dataclass singleton resource in the ECS world.

        Args:
            resource: Dataclass resource instance to store or replace.
        """

        set_resource_runtime(self, resource)

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        """Return a mutable view for an existing resource.

        Args:
            resource_type: Dataclass resource class to access.

        Returns:
            A resource view typed as ``resource_type`` for field access.
        """

        return get_resource_runtime(self, resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        """Remove a resource from the ECS world.

        Args:
            resource_type: Dataclass resource class to remove.
        """

        remove_resource_runtime(self, resource_type)

    def get_resource_field(self, resource_type: type[Any], field_name: str) -> Any:
        """Read one field from an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned resource field value.
        """

        return get_resource_field_runtime(self, resource_type, field_name)

    def set_resource_field(self, resource_type: type[Any], field_name: str, value: object) -> None:
        """Write one field on an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to update.
            value: New value accepted by the field's ECS storage type.
        """

        set_resource_field_runtime(self, resource_type, field_name, value)

    def resource_snapshot(self, resource_type: type[Any]) -> object:
        """Copy a resource's current fields into a new dataclass instance.

        Args:
            resource_type: Dataclass resource class to copy.

        Returns:
            A new dataclass instance of ``resource_type``.
        """

        return resource_snapshot_runtime(self, resource_type)

    # ---------------------------------------------------------------- events
    def emit_event(self, event: object, *, expected_type: type[Any] | None = None) -> None:
        """Queue an ECS event for readers in the current frame.

        Args:
            event: Dataclass event instance to enqueue.
            expected_type: Optional event class used when a typed writer validates payloads.
        """

        emit_event_runtime(self, event, expected_type=expected_type)

    def read_events(self, event_type: type[ComponentT]) -> tuple[ComponentT, ...]:
        """Read queued events of one dataclass type.

        Args:
            event_type: Dataclass event class to read.

        Returns:
            A tuple of copied event instances in emission order.
        """

        return read_events_runtime(self, event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        """Clear queued ECS events.

        Args:
            event_type: Event class to clear, or ``None`` to clear all event types.
        """

        clear_events_runtime(self, event_type)

    # ---------------------------------------------------------------- systems
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
        """Register an ``@ecs.system`` with this world.

        Args:
            system: Function decorated with ``@ecs.system``.
            order: Numeric ordering key used before dependency constraints.
            enabled: Whether the system should run immediately after registration.
            name: Optional unique system name. Defaults to the decorated function name.
            before: Systems that should run after this system.
            after: Systems that should run before this system.
            run_if: Optional callback checked before each scheduled run.
            set: Optional system-set name for shared configuration.

        Returns:
            A handle that can enable, disable, or remove the registered system.
        """

        return add_system_runtime(
            self,
            system,
            order=order,
            enabled=enabled,
            name=name,
            before=tuple(before),
            after=tuple(after),
            run_if=run_if,
            set_name=set,
        )

    def remove_system(self, handle: SystemHandle | str) -> None:
        """Unregister a scheduled ECS system.

        Args:
            handle: System handle or system name returned by ``add_system()``.
        """

        remove_system_runtime(self, handle)

    def enable_system(self, handle: SystemHandle | str) -> None:
        """Allow a scheduled ECS system to run again.

        Args:
            handle: System handle or system name to enable.
        """

        self._set_system_enabled(handle, True)

    def disable_system(self, handle: SystemHandle | str) -> None:
        """Temporarily prevent a scheduled ECS system from running.

        Args:
            handle: System handle or system name to disable.
        """

        self._set_system_enabled(handle, False)

    def run_pre_draw_systems(self) -> None:
        """Run enabled ECS systems once using the sketch pre-draw lifecycle order."""

        run_pre_draw_systems_runtime(self)

    def _run_sorted_systems(self) -> None:
        run_sorted_systems_runtime(self)

    def _run_system_action(self, scheduled: _ScheduledSystem, action: Action) -> None:
        run_system_action_runtime(self, scheduled, action)

    def _has_change_filtered_systems(self) -> bool:
        return has_change_filtered_systems_runtime(self)

    def match_query(self, spec: QuerySpec) -> list[EntityView]:
        return match_query_runtime(self, spec)

    def iter_join_contexts_for(
        self,
        base_ctx: dict[object, Any],
        expr: Expression,
        *,
        include_query: QueryProxy | None = None,
    ) -> Iterator[dict[object, Any]]:
        yield from iter_join_contexts_for_runtime(self, base_ctx, expr, include_query=include_query)

    def iter_join_contexts_for_queries(
        self, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
    ) -> Iterator[dict[object, Any]]:
        yield from iter_join_contexts_for_queries_runtime(self, base_ctx, queries)

    def write_key(
        self, target: FieldExpression, ctx: dict[object, Any]
    ) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
        return write_key_runtime(target, ctx)

    def check_parallel_children(self, children: tuple[Action, ...]) -> None:
        check_parallel_children_runtime(self, children)

    def materialize_udf_arg(self, arg: object) -> object:
        return materialize_udf_arg_runtime(self, arg)

    def _register_event_type(self, event_type: type[Any]) -> None:
        register_event_type_runtime(self, event_type)

    # -------------------------------------------------------------- Rust sync
    def _sync_component_fields_to_rust(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        sync_component_fields_to_rust_runtime(self, entity, component_type, component)

    def _sync_component_field_to_rust(
        self, entity: Entity, component_type: type[Any], field_name: str, value: object
    ) -> None:
        sync_component_field_to_rust_runtime(self, entity, component_type, field_name, value)

    def _component_type_for_schema(self, schema_name: str) -> type[Any]:
        return component_type_for_schema_runtime(self, schema_name)

    # -------------------------------------------------------------- diagnostics
    def configure(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        """Configure duplicate-write handling for this ECS world.

        Args:
            strict: When true, reject ambiguous duplicate writes instead of resolving them.
            warn_on_ambiguity: When true, log warnings for duplicate-write resolution.
        """

        configure_runtime(self, strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def diagnostics(self) -> dict[str, Any]:
        """Return ECS counters and diagnostic messages.

        Returns:
            A dictionary of diagnostic names to values.
        """

        return diagnostics_runtime(self)

    def reset_diagnostics(self) -> None:
        """Reset ECS diagnostic counters and messages."""

        reset_diagnostics_runtime(self)

    def record_ambiguity(self, message: str) -> None:
        """Record an ambiguity diagnostic message.

        Args:
            message: Human-readable explanation of the ambiguous write or schedule.
        """

        record_ambiguity_runtime(self, message)

    def _note_field_update(self, entity: Entity, component_type: type[Any]) -> None:
        note_field_update_runtime(self, entity, component_type)

    def _note_resource_update(self) -> None:
        note_resource_update_runtime(self)

    def _invalidate_spatial_indexes(self, *, clear_only: bool = False) -> None:
        invalidate_spatial_indexes_runtime(self, clear_only=clear_only)

    def configure_system_set(
        self,
        name: str,
        *,
        order: int | None = None,
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        """Configure default scheduling options for a named system set.

        Args:
            name: System-set name used by ``add_system(..., set=name)``.
            order: Optional order applied to systems in the set.
            enabled: Optional enabled state applied to systems in the set.
            run_if: Optional run condition applied to systems in the set.
        """

        configure_system_set_runtime(self, name, order=order, enabled=enabled, run_if=run_if)

    def _system_enabled(self, scheduled: _ScheduledSystem) -> bool:
        return system_enabled_runtime(self, scheduled)

    def _system_run_condition(self, scheduled: _ScheduledSystem) -> bool:
        return system_run_condition_runtime(self, scheduled)

    def _sorted_systems(self) -> list[_ScheduledSystem]:
        return sorted_scheduled_systems(self._systems, self._system_sets)

    def _begin_change_frame(self) -> None:
        begin_change_frame_runtime(self)

    def _finalize_change_frame(self) -> None:
        finalize_change_frame_runtime(self)

    def _mark_component_added(self, entity: Entity, component_type: type[Any]) -> None:
        mark_component_added_runtime(self, entity, component_type)

    def _mark_component_changed(self, entity: Entity, component_type: type[Any]) -> None:
        mark_component_changed_runtime(self, entity, component_type)

    def _mark_component_removed(self, entity: Entity, component_type: type[Any]) -> None:
        mark_component_removed_runtime(self, entity, component_type)

    def _set_system_enabled(self, handle: SystemHandle | str, enabled: bool) -> None:
        set_system_enabled_runtime(self, handle, enabled)


__all__ = ["EcsWorld", "Entity", "EntityMutation", "EntityView", "MutEntity", "SystemHandle"]
