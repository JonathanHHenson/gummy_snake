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
from gummysnake.ecs.world_runtime import entities as entity_runtime
from gummysnake.ecs.world_runtime import query as query_runtime
from gummysnake.ecs.world_runtime import resources as resource_runtime
from gummysnake.ecs.world_runtime import state as state_runtime
from gummysnake.ecs.world_runtime import systems as system_runtime
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
        """Validate and cache a dataclass ECS schema.

        Args:
            component_type: Dataclass type used as a component, resource, or event payload.

        Returns:
            Mapping from dataclass field names to Rust storage types.
        """

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

        return entity_runtime.add_entity(self, *components, tags=tags)

    def despawn_entity(self, entity: Entity) -> None:
        """Remove an entity and all of its components.

        Args:
            entity: Entity handle that belongs to this world.
        """

        entity_runtime.despawn_entity(self, entity)

    def add_component(self, entity: Entity, component: object) -> None:
        """Add or replace a dataclass component on an entity.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
        """

        entity_runtime.add_component(self, entity, component)

    def set_component(
        self, entity: Entity, component: object, *, expected_type: type[Any] | None = None
    ) -> None:
        """Store a component value in a specific component slot.

        Args:
            entity: Entity handle to update.
            component: Dataclass component instance to store.
            expected_type: Component class for assignment through typed view APIs.
        """

        entity_runtime.set_component(self, entity, component, expected_type=expected_type)

    def _upsert_component(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        entity_runtime.upsert_component(self, entity, component_type, component)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        """Remove one component type from an entity.

        Args:
            entity: Entity handle to update.
            component_type: Dataclass component class to remove.
        """

        entity_runtime.remove_component(self, entity, component_type)

    def add_tag(self, entity: Entity, tag: object) -> None:
        """Add a tag to an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to a string tag for filtering queries.
        """

        entity_runtime.add_tag(self, entity, tag)

    def remove_tag(self, entity: Entity, tag: object) -> None:
        """Remove a tag from an entity.

        Args:
            entity: Entity handle to update.
            tag: Value converted to the string tag to remove.
        """

        entity_runtime.remove_tag(self, entity, tag)

    def get_entity(self, *components: type[Any], tags: Iterable[object] = ()) -> EntityView:
        """Return the single entity matching component and tag filters.

        Args:
            components: Component classes that the entity must have.
            tags: Tag values that the entity must have.

        Returns:
            An ``EntityView`` for the matching entity.
        """

        return entity_runtime.get_entity(self, *components, tags=tags)

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

        return entity_runtime.try_get_entity(self, *components, tags=tags)

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

        return entity_runtime.iter_entities(self, *components, tags=tags)

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

        return entity_runtime.iter_component_fields(self, component_type, *field_names, tags=tags)

    def _slot(self, entity: Entity) -> None:
        entity_runtime.slot(self, entity)

    def _has_component(self, entity: Entity, component_type: type[Any]) -> bool:
        return entity_runtime.has_component(self, entity, component_type)

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

        return entity_runtime.get_component_field(self, entity, component_type, field_name)

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

        entity_runtime.set_component_field(self, entity, component_type, field_name, value)

    def component_snapshot(self, entity: Entity, component_type: type[Any]) -> object:
        """Copy a component's current fields into a new dataclass instance.

        Args:
            entity: Entity handle whose component should be copied.
            component_type: Dataclass component class to copy.

        Returns:
            A new dataclass instance of ``component_type``.
        """

        return entity_runtime.component_snapshot(self, entity, component_type)

    # --------------------------------------------------------------- resources
    def set_resource(self, resource: object) -> None:
        """Store a dataclass singleton resource in the ECS world.

        Args:
            resource: Dataclass resource instance to store or replace.
        """

        resource_runtime.set_resource(self, resource)

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        """Return a mutable view for an existing resource.

        Args:
            resource_type: Dataclass resource class to access.

        Returns:
            A resource view typed as ``resource_type`` for field access.
        """

        return resource_runtime.get_resource(self, resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        """Remove a resource from the ECS world.

        Args:
            resource_type: Dataclass resource class to remove.
        """

        resource_runtime.remove_resource(self, resource_type)

    def get_resource_field(self, resource_type: type[Any], field_name: str) -> Any:
        """Read one field from an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to read.

        Returns:
            The current Rust-owned resource field value.
        """

        return resource_runtime.get_resource_field(self, resource_type, field_name)

    def set_resource_field(self, resource_type: type[Any], field_name: str, value: object) -> None:
        """Write one field on an ECS resource.

        Args:
            resource_type: Dataclass resource class that owns the field.
            field_name: Dataclass field name to update.
            value: New value accepted by the field's ECS storage type.
        """

        resource_runtime.set_resource_field(self, resource_type, field_name, value)

    def resource_snapshot(self, resource_type: type[Any]) -> object:
        """Copy a resource's current fields into a new dataclass instance.

        Args:
            resource_type: Dataclass resource class to copy.

        Returns:
            A new dataclass instance of ``resource_type``.
        """

        return resource_runtime.resource_snapshot(self, resource_type)

    # ---------------------------------------------------------------- events
    def emit_event(self, event: object, *, expected_type: type[Any] | None = None) -> None:
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

        return system_runtime.add_system(
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

        system_runtime.remove_system(self, handle)

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

        system_runtime.run_pre_draw_systems(self)

    def _run_sorted_systems(self) -> None:
        system_runtime.run_sorted_systems(self)

    def _run_system_action(self, scheduled: _ScheduledSystem, action: Action) -> None:
        system_runtime.run_system_action(self, scheduled, action)

    def _has_change_filtered_systems(self) -> bool:
        return system_runtime.has_change_filtered_systems(self)

    def match_query(self, spec: QuerySpec) -> list[EntityView]:
        return query_runtime.match_query(self, spec)

    def iter_join_contexts_for(
        self,
        base_ctx: dict[object, Any],
        expr: Expression,
        *,
        include_query: QueryProxy | None = None,
    ) -> Iterator[dict[object, Any]]:
        yield from query_runtime.iter_join_contexts_for(
            self, base_ctx, expr, include_query=include_query
        )

    def iter_join_contexts_for_queries(
        self, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
    ) -> Iterator[dict[object, Any]]:
        yield from query_runtime.iter_join_contexts_for_queries(self, base_ctx, queries)

    def write_key(
        self, target: FieldExpression, ctx: dict[object, Any]
    ) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
        return query_runtime.write_key(target, ctx)

    def check_parallel_children(self, children: tuple[Action, ...]) -> None:
        query_runtime.check_parallel_children(self, children)

    def materialize_udf_arg(self, arg: object) -> object:
        return query_runtime.materialize_udf_arg(self, arg)

    def _register_event_type(self, event_type: type[Any]) -> None:
        resource_runtime.register_event_type(self, event_type)

    # -------------------------------------------------------------- Rust sync
    def _sync_component_fields_to_rust(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        entity_runtime.sync_component_fields_to_rust(self, entity, component_type, component)

    def _sync_component_field_to_rust(
        self, entity: Entity, component_type: type[Any], field_name: str, value: object
    ) -> None:
        entity_runtime.sync_component_field_to_rust(self, entity, component_type, field_name, value)

    def _component_type_for_schema(self, schema_name: str) -> type[Any]:
        return entity_runtime.component_type_for_schema(self, schema_name)

    # -------------------------------------------------------------- diagnostics
    def configure(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        """Configure duplicate-write handling for this ECS world.

        Args:
            strict: When true, reject ambiguous duplicate writes instead of resolving them.
            warn_on_ambiguity: When true, log warnings for duplicate-write resolution.
        """

        state_runtime.configure(self, strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def diagnostics(self) -> dict[str, Any]:
        """Return ECS counters and diagnostic messages.

        Returns:
            A dictionary of diagnostic names to values.
        """

        return state_runtime.diagnostics(self)

    def reset_diagnostics(self) -> None:
        """Reset ECS diagnostic counters and messages."""

        state_runtime.reset_diagnostics(self)

    def record_ambiguity(self, message: str) -> None:
        """Record an ambiguity diagnostic message.

        Args:
            message: Human-readable explanation of the ambiguous write or schedule.
        """

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

        state_runtime.configure_system_set(self, name, order=order, enabled=enabled, run_if=run_if)

    def _system_enabled(self, scheduled: _ScheduledSystem) -> bool:
        return state_runtime.system_enabled(self, scheduled)

    def _system_run_condition(self, scheduled: _ScheduledSystem) -> bool:
        return state_runtime.system_run_condition(self, scheduled)

    def _sorted_systems(self) -> list[_ScheduledSystem]:
        return sorted_scheduled_systems(self._systems, self._system_sets)

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


__all__ = ["EcsWorld", "Entity", "EntityMutation", "EntityView", "MutEntity", "SystemHandle"]
