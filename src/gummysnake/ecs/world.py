"""Python-facing ECS world and entity APIs.

Rust owns canonical ECS entity/component/resource storage and physical system execution. This module
keeps the public Python API, schema conversion, logical-plan construction, and explicit Python UDF
integration at the boundary.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import fields, is_dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    cast,
    get_type_hints,
)

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
)
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
    _tag_name,
    _validate_storage_value,
)
from gummysnake.ecs.specs import (
    ChangeTerm,
    QuerySpec,
)
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.types import StorageType
from gummysnake.ecs.world_helpers import (
    _contains_direct_udf_action,
    _handle_matches,
    _is_direct_udf_action,
    _is_sequence_action,
)
from gummysnake.ecs.world_runtime.physical import (
    prepare_scheduled_physical_plan,
    run_physical_system,
)
from gummysnake.ecs.world_runtime.python_system import run_python_system
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
from gummysnake.exceptions import (
    ComponentSchemaError,
    EntityNotFoundError,
    MissingComponentError,
    StaleEntityError,
    SystemExecutionError,
    SystemPlanError,
)
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
        component_values: dict[type[Any], object] = {}
        for component in components:
            self._validate_value(component)
            component_values[type(component)] = component
        index, generation = self._rust.allocate_entity()
        entity = Entity(index, generation, self._world_id)
        for component_type, component in component_values.items():
            self._rust.add_component_default(index, generation, _schema_name(component_type))
            self._sync_component_fields_to_rust(entity, component_type, component)
            self._mark_component_added(entity, component_type)
        for tag in tags:
            self._rust.add_tag(index, generation, _tag_name(tag))
        self._diagnostics["ecs_entities_alive"] = self._rust.alive_count()
        self._invalidate_spatial_indexes()
        return entity

    def despawn_entity(self, entity: Entity) -> None:
        self._slot(entity)
        removed_components = [
            self._component_type_for_schema(schema_name)
            for schema_name in self._rust.entity_components(entity.index, entity.generation)
        ]
        self._rust.despawn_entity(entity.index, entity.generation)
        for component_type in removed_components:
            self._mark_component_removed(entity, component_type)
        self._diagnostics["ecs_entities_alive"] = self._rust.alive_count()
        self._diagnostics["ecs_entity_generation_reuses"] += 1
        self._invalidate_spatial_indexes()

    def add_component(self, entity: Entity, component: object) -> None:
        self._validate_value(component)
        self._slot(entity)
        self._upsert_component(entity, type(component), component)

    def set_component(
        self, entity: Entity, component: object, *, expected_type: type[Any] | None = None
    ) -> None:
        self._validate_value(component, expected_type)
        self._slot(entity)
        self._upsert_component(entity, expected_type or type(component), component)

    def _upsert_component(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        existed = self._has_component(entity, component_type)
        if not existed:
            self._rust.add_component_default(
                entity.index, entity.generation, _schema_name(component_type)
            )
        self._sync_component_fields_to_rust(entity, component_type, component)
        if existed:
            self._note_field_update(entity, component_type)
        else:
            self._mark_component_added(entity, component_type)
            self._diagnostics["ecs_structural_commands_applied"] += 1
            self._invalidate_spatial_indexes()

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        self._slot(entity)
        if not self._has_component(entity, component_type):
            raise MissingComponentError(component_type.__name__)
        self._rust.remove_component(entity.index, entity.generation, _schema_name(component_type))
        self._mark_component_removed(entity, component_type)
        self._diagnostics["ecs_structural_commands_applied"] += 1
        self._invalidate_spatial_indexes()

    def add_tag(self, entity: Entity, tag: object) -> None:
        self._slot(entity)
        tag_name = _tag_name(tag)
        if tag_name not in self._rust.entity_tags(entity.index, entity.generation):
            self._rust.add_tag(entity.index, entity.generation, tag_name)
            self._diagnostics["ecs_structural_commands_applied"] += 1
            self._invalidate_spatial_indexes()

    def remove_tag(self, entity: Entity, tag: object) -> None:
        self._slot(entity)
        tag_name = _tag_name(tag)
        if tag_name in self._rust.entity_tags(entity.index, entity.generation):
            self._rust.remove_tag(entity.index, entity.generation, tag_name)
            self._diagnostics["ecs_structural_commands_applied"] += 1
            self._invalidate_spatial_indexes()

    def get_entity(self, *components: type[Any], tags: Iterable[object] = ()) -> EntityView:
        matches = list(self.iter_entities(*components, tags=tags))
        if len(matches) != 1:
            raise EntityNotFoundError(f"Expected exactly one ECS entity, found {len(matches)}.")
        return matches[0]

    def try_get_entity(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> EntityView | None:
        matches = list(self.iter_entities(*components, tags=tags))
        if len(matches) > 1:
            raise EntityNotFoundError(f"Expected zero or one ECS entity, found {len(matches)}.")
        return matches[0] if matches else None

    def iter_entities(
        self, *components: type[Any], tags: Iterable[object] = ()
    ) -> Iterator[EntityView]:
        required_components = [_schema_name(component) for component in components]
        for component in components:
            self.validate_schema(component)
        required_tags = [_tag_name(tag) for tag in tags]
        for index, generation in self._rust.query_filtered(
            required_components, required_tags, [], []
        ):
            yield EntityView(self, Entity(index, generation, self._world_id))

    def iter_component_fields(
        self,
        component_type: type[Any],
        *field_names: str,
        tags: Iterable[object] = (),
    ) -> Iterator[tuple[Any, ...]]:
        """Iterate selected component fields using one Rust-backed batch read."""
        self.validate_schema(component_type)
        schema = _schema_name(component_type)
        schema_fields = self._schemas[component_type]
        for field_name in field_names:
            if field_name not in schema_fields:
                raise AttributeError(field_name)
        required_tags = [_tag_name(tag) for tag in tags]
        rows = self._rust.query_component_fields([schema], required_tags, schema, list(field_names))
        return iter(rows)

    def _slot(self, entity: Entity) -> None:
        if entity.world_id != self._world_id:
            raise StaleEntityError("ECS entity belongs to a different world.")
        if entity.index < 0:
            raise StaleEntityError("ECS entity index is invalid.")
        try:
            self._rust.validate_entity(entity.index, entity.generation)
        except ValueError as exc:
            raise StaleEntityError("ECS entity handle is stale.") from exc

    def _has_component(self, entity: Entity, component_type: type[Any]) -> bool:
        self.validate_schema(component_type)
        return _schema_name(component_type) in self._rust.entity_components(
            entity.index, entity.generation
        )

    def get_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str
    ) -> Any:
        self._slot(entity)
        self.validate_schema(component_type)
        if field_name not in self._schemas[component_type]:
            raise AttributeError(field_name)
        try:
            return self._rust.get_field(
                entity.index, entity.generation, _schema_name(component_type), field_name
            )
        except ValueError as exc:
            raise MissingComponentError(
                f"Entity {entity.index}:{entity.generation} does not have "
                f"component {component_type.__name__}."
            ) from exc

    def set_component_field(
        self, entity: Entity, component_type: type[Any], field_name: str, value: object
    ) -> None:
        self._slot(entity)
        self.validate_schema(component_type)
        if field_name not in self._schemas[component_type]:
            raise AttributeError(field_name)
        _validate_storage_value(
            component_type, field_name, value, self._schemas[component_type][field_name]
        )
        self._sync_component_field_to_rust(entity, component_type, field_name, value)
        self._note_field_update(entity, component_type)

    def component_snapshot(self, entity: Entity, component_type: type[Any]) -> object:
        self._slot(entity)
        self.validate_schema(component_type)
        component_constructor = cast(type[Any], component_type)
        values = {
            field.name: self.get_component_field(entity, component_type, field.name)
            for field in fields(component_constructor)
        }
        return component_constructor(**values)

    # --------------------------------------------------------------- resources
    def set_resource(self, resource: object) -> None:
        set_resource_runtime(self, resource)

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        return get_resource_runtime(self, resource_type)

    def remove_resource(self, resource_type: type[Any]) -> None:
        remove_resource_runtime(self, resource_type)

    def get_resource_field(self, resource_type: type[Any], field_name: str) -> Any:
        return get_resource_field_runtime(self, resource_type, field_name)

    def set_resource_field(self, resource_type: type[Any], field_name: str, value: object) -> None:
        set_resource_field_runtime(self, resource_type, field_name, value)

    def resource_snapshot(self, resource_type: type[Any]) -> object:
        return resource_snapshot_runtime(self, resource_type)

    # ---------------------------------------------------------------- events
    def emit_event(self, event: object, *, expected_type: type[Any] | None = None) -> None:
        emit_event_runtime(self, event, expected_type=expected_type)

    def read_events(self, event_type: type[ComponentT]) -> tuple[ComponentT, ...]:
        return read_events_runtime(self, event_type)

    def clear_events(self, event_type: type[Any] | None = None) -> None:
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
        if not isinstance(system, SystemDefinition):
            raise SystemPlanError("gs.add_system() expects a function decorated with @ecs.system.")
        built = system.build()
        system_name = name or built.name
        if any(s.handle.name == system_name for s in self._systems):
            raise SystemPlanError(f"ECS system name {system_name!r} is already registered.")
        handle = SystemHandle(self._next_system_id, system_name)
        self._next_system_id += 1
        scheduled = _ScheduledSystem(
            handle,
            built,
            int(order),
            bool(enabled),
            before=tuple(before),
            after=tuple(after),
            run_if=run_if,
            set_name=set,
        )
        prepare_scheduled_physical_plan(self, scheduled)
        self._systems.append(scheduled)
        self._systems = self._sorted_systems()
        self._has_change_filtered_systems_cache = None
        self._diagnostics["ecs_systems_registered"] = len(self._systems)
        self._diagnostics["ecs_schedule_rebuilds"] += 1
        return handle

    def remove_system(self, handle: SystemHandle | str) -> None:
        removed = [s for s in self._systems if _handle_matches(s.handle, handle)]
        if not removed:
            raise SystemPlanError(f"Unknown ECS system {handle!r}.")
        for scheduled in removed:
            if scheduled.physical_plan_handle is not None:
                self._rust.release_compiled_plan(scheduled.physical_plan_handle)
        self._systems = [s for s in self._systems if not _handle_matches(s.handle, handle)]
        self._has_change_filtered_systems_cache = None
        self._diagnostics["ecs_systems_registered"] = len(self._systems)

    def enable_system(self, handle: SystemHandle | str) -> None:
        self._set_system_enabled(handle, True)

    def disable_system(self, handle: SystemHandle | str) -> None:
        self._set_system_enabled(handle, False)

    def run_pre_draw_systems(self) -> None:
        self._diagnostics["ecs_pre_draw_runs"] += 1
        self._begin_change_frame()
        self._invalidate_spatial_indexes(clear_only=True)
        try:
            self._run_sorted_systems()
        finally:
            self._finalize_change_frame()

    def _run_sorted_systems(self) -> None:
        for scheduled in self._sorted_systems():
            if not self._system_enabled(scheduled):
                continue
            if not self._system_run_condition(scheduled):
                self._diagnostics["ecs_system_run_condition_skips"] += 1
                continue
            try:
                self._run_system_action(scheduled, scheduled.built.plan.action)
            except Exception as exc:
                if isinstance(exc, SystemPlanError | SystemExecutionError):
                    raise
                raise SystemExecutionError(
                    f"ECS system {scheduled.handle.name!r} failed: {exc}"
                ) from exc

    def _run_system_action(self, scheduled: _ScheduledSystem, action: Action) -> None:
        if scheduled.built.python:
            run_python_system(self, scheduled)
            return
        if _is_direct_udf_action(action):
            udf_action = cast(DefaultAction, action)
            if udf_action.udf is None:
                raise SystemExecutionError("Malformed ECS UDF action.")
            udf_action.udf.execute_action(self, udf_action.udf_args)
            return
        if _contains_direct_udf_action(action):
            if _is_sequence_action(action):
                for child in cast(Any, action).children:
                    self._run_system_action(scheduled, child)
                return
            raise SystemPlanError(
                "Python UDF actions can only appear as standalone actions or inside "
                "do_in_order() sequences; non-UDF ECS work still executes in Rust."
            )
        run_physical_system(self, scheduled, action)

    def _has_change_filtered_systems(self) -> bool:
        cached = self._has_change_filtered_systems_cache
        if cached is not None:
            return cached
        for scheduled in self._systems:
            for query in scheduled.built.queries:
                spec = query.spec
                if isinstance(spec, QuerySpec) and any(
                    isinstance(term, ChangeTerm) for term in spec.terms
                ):
                    self._has_change_filtered_systems_cache = True
                    return True
        self._has_change_filtered_systems_cache = False
        return False

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
        for field in fields(component_type):
            self._rust.set_field(
                entity.index,
                entity.generation,
                _schema_name(component_type),
                field.name,
                copy.deepcopy(getattr(component, field.name)),
            )

    def _sync_component_field_to_rust(
        self, entity: Entity, component_type: type[Any], field_name: str, value: object
    ) -> None:
        self._rust.set_field(
            entity.index,
            entity.generation,
            _schema_name(component_type),
            field_name,
            copy.deepcopy(value),
        )

    def _component_type_for_schema(self, schema_name: str) -> type[Any]:
        event_type = self._event_types.get(schema_name)
        if event_type is not None:
            return event_type
        for component_type in self._schemas:
            if _schema_name(component_type) == schema_name:
                return component_type
        raise SystemExecutionError(f"Rust ECS returned unknown component schema {schema_name!r}.")

    # -------------------------------------------------------------- diagnostics
    def configure(
        self, *, strict: bool | None = None, warn_on_ambiguity: bool | None = None
    ) -> None:
        configure_runtime(self, strict=strict, warn_on_ambiguity=warn_on_ambiguity)

    def diagnostics(self) -> dict[str, Any]:
        return diagnostics_runtime(self)

    def reset_diagnostics(self) -> None:
        reset_diagnostics_runtime(self)

    def record_ambiguity(self, message: str) -> None:
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
