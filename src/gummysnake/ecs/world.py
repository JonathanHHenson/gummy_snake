"""Python-facing ECS world and entity APIs.

The MVP keeps the public API and deterministic execution semantics in Python while using
column-oriented schema restrictions planned for the Rust runtime. The module is written behind a
small ``EcsWorld`` boundary so a Rust bridge can replace storage/execution without changing sketch
code.
"""

from __future__ import annotations

import copy
import itertools
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin, get_type_hints

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    ForEachAction,
    WhenAction,
    action_write_targets,
)
from gummysnake.ecs.expressions import (
    Expression,
    FieldExpression,
    QueryProxy,
    expression_queries,
)
from gummysnake.ecs.physical import PhysicalPlanUnsupported, build_physical_payload
from gummysnake.ecs.specs import ChangeTerm, QuerySpec, TagTerm
from gummysnake.ecs.systems import BuiltSystem, SystemDefinition
from gummysnake.ecs.types import (
    Bool,
    Float64,
    Int64,
    StorageType,
    String,
)
from gummysnake.exceptions import (
    ComponentSchemaError,
    EntityNotFoundError,
    MissingComponentError,
    MissingResourceError,
    StaleEntityError,
    SystemExecutionError,
    SystemPlanError,
)
from gummysnake.rust.ecs import create_ecs_world

ComponentT = TypeVar("ComponentT")
ResourceT = TypeVar("ResourceT")


@dataclass(frozen=True)
class Entity:
    """Public generational ECS entity handle."""

    index: int
    generation: int
    world_id: int

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        return EntityAnnotation(item, mutable=False)


@dataclass(frozen=True)
class EntityAnnotation:
    component_type: object
    mutable: bool = False


class MutEntity:
    """UDF annotation marker for mutable entity views."""

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        return EntityAnnotation(item, mutable=True)

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        raise TypeError("ecs.MutEntity is an annotation marker; UDFs receive entity views.")


@dataclass
class _EntitySlot:
    """Lightweight Python handle metadata; component/tag data is Rust-owned."""

    generation: int = 0
    alive: bool = False


class ComponentView:
    """Rust-backed component field view used at Python/UDF/draw boundaries."""

    __slots__ = (
        "_world",
        "_entity",
        "_component_type",
        "_schema_name",
        "_field_names",
        "_rust",
    )

    def __init__(self, world: EcsWorld, entity: Entity, component_type: type[Any]) -> None:
        world.validate_schema(component_type)
        object.__setattr__(self, "_world", world)
        object.__setattr__(self, "_entity", entity)
        object.__setattr__(self, "_component_type", component_type)
        object.__setattr__(self, "_schema_name", _schema_name(component_type))
        object.__setattr__(self, "_field_names", frozenset(world._schemas[component_type]))
        object.__setattr__(self, "_rust", world._rust)

    def __getattr__(self, field_name: str) -> Any:
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
        if field_name.startswith("_"):
            object.__setattr__(self, field_name, value)
            return
        if field_name not in self._field_names:
            raise AttributeError(field_name)
        self._world.set_component_field(self._entity, self._component_type, field_name, value)

    def snapshot(self) -> object:
        return self._world.component_snapshot(self._entity, self._component_type)

    def __repr__(self) -> str:
        return (
            f"ComponentView({self._component_type.__name__}@"
            f"{self._entity.index}:{self._entity.generation})"
        )


class ResourceView:
    """Rust-backed resource field view returned by ``get_resource``."""

    def __init__(self, world: EcsWorld, resource_type: type[Any]) -> None:
        object.__setattr__(self, "_world", world)
        object.__setattr__(self, "_resource_type", resource_type)

    def __getattr__(self, field_name: str) -> Any:
        if field_name.startswith("__"):
            raise AttributeError(field_name)
        return self._world.get_resource_field(self._resource_type, field_name)

    def __setattr__(self, field_name: str, value: object) -> None:
        if field_name.startswith("_"):
            object.__setattr__(self, field_name, value)
            return
        self._world.set_resource_field(self._resource_type, field_name, value)

    def snapshot(self) -> object:
        return self._world.resource_snapshot(self._resource_type)

    def __repr__(self) -> str:
        return f"ResourceView({self._resource_type.__name__})"


class EntityView:
    """Mutable Python view over an entity's components."""

    def __init__(self, world: EcsWorld, entity: Entity) -> None:
        self._world = world
        self.entity = entity

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        return cast(ComponentT, ComponentView(self._world, self.entity, component_type))

    def __setitem__(self, component_type: type[Any], value: object) -> None:
        self._world.set_component(self.entity, value, expected_type=component_type)

    def add_component(self, component: object) -> None:
        self._world.add_component(self.entity, component)

    def remove_component(self, component_type: type[Any]) -> None:
        self._world.remove_component(self.entity, component_type)

    def add_tag(self, tag: object) -> None:
        self._world.add_tag(self.entity, tag)

    def remove_tag(self, tag: object) -> None:
        self._world.remove_tag(self.entity, tag)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EntityView) and self.entity == other.entity

    def __hash__(self) -> int:
        return hash(self.entity)

    def __repr__(self) -> str:
        return f"EntityView({self.entity.index}:{self.entity.generation})"


@dataclass(frozen=True)
class SystemHandle:
    """Handle returned by ``gs.add_system``."""

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
    physical_schema_fingerprint: int | None = None
    physical_error_reason: str | None = None


class EcsWorld:
    """Deterministic ECS world owned by one ``SketchContext``."""

    def __init__(self, context: Any | None = None) -> None:
        self.context = context
        self._world_id = id(self)
        self._rust = create_ecs_world()
        self._slots: list[_EntitySlot] = []
        self._systems: list[_ScheduledSystem] = []
        self._system_sets: dict[str, _SystemSetConfig] = {}
        self._next_system_id = 1
        self._resources: set[type[Any]] = set()
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
        self._component_snapshot: dict[tuple[int, int, type[Any]], object] = {}
        self._added_components: set[tuple[int, int, type[Any]]] = set()
        self._changed_components: set[tuple[int, int, type[Any]]] = set()
        self._removed_components: set[tuple[int, int, type[Any]]] = set()
        self._events: dict[type[Any], list[tuple[int, object]]] = {}
        self._event_types: dict[str, type[Any]] = {}
        self._mirror_writes_to_rust = True

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
        if index == len(self._slots):
            self._slots.append(_EntitySlot(generation=generation, alive=True))
        else:
            slot = self._slots[index]
            slot.generation = generation
            slot.alive = True
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
        slot = self._slot(entity)
        removed_components = [
            self._component_type_for_schema(schema_name)
            for schema_name in self._rust.entity_components(entity.index, entity.generation)
        ]
        self._rust.despawn_entity(entity.index, entity.generation)
        for component_type in removed_components:
            self._mark_component_removed(entity, component_type)
        slot.alive = False
        self._diagnostics["ecs_entities_alive"] = self._rust.alive_count()
        self._diagnostics["ecs_entity_generation_reuses"] += 1
        self._invalidate_spatial_indexes()

    def add_component(self, entity: Entity, component: object) -> None:
        self._validate_value(component)
        self._slot(entity)
        component_type = type(component)
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

    def set_component(
        self, entity: Entity, component: object, *, expected_type: type[Any] | None = None
    ) -> None:
        self._validate_value(component, expected_type)
        self._slot(entity)
        component_type = expected_type or type(component)
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

    def _slot(self, entity: Entity) -> _EntitySlot:
        if entity.world_id != self._world_id:
            raise StaleEntityError("ECS entity belongs to a different world.")
        if entity.index < 0:
            raise StaleEntityError("ECS entity index is invalid.")
        try:
            self._rust.validate_entity(entity.index, entity.generation)
        except ValueError as exc:
            raise StaleEntityError("ECS entity handle is stale.") from exc
        if entity.index >= len(self._slots):
            self._slots.extend(_EntitySlot() for _ in range(entity.index - len(self._slots) + 1))
        slot = self._slots[entity.index]
        slot.generation = entity.generation
        slot.alive = True
        return slot

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
        self._validate_value(resource)
        self._resources.add(type(resource))
        self._sync_resource_to_rust(type(resource), resource)
        self._note_resource_update()

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        self.validate_schema(resource_type)
        if not self._rust.has_resource(_schema_name(resource_type)):
            raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.")
        return cast(ResourceT, ResourceView(self, resource_type))

    def remove_resource(self, resource_type: type[Any]) -> None:
        self.validate_schema(resource_type)
        if not self._rust.has_resource(_schema_name(resource_type)):
            raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.")
        self._resources.discard(resource_type)
        self._rust.remove_resource(_schema_name(resource_type))
        self._note_resource_update()

    def get_resource_field(self, resource_type: type[Any], field_name: str) -> Any:
        self.validate_schema(resource_type)
        if field_name not in self._schemas[resource_type]:
            raise AttributeError(field_name)
        try:
            return self._rust.resource_field(_schema_name(resource_type), field_name)
        except ValueError as exc:
            raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.") from exc

    def set_resource_field(self, resource_type: type[Any], field_name: str, value: object) -> None:
        self.validate_schema(resource_type)
        if field_name not in self._schemas[resource_type]:
            raise AttributeError(field_name)
        _validate_storage_value(
            resource_type, field_name, value, self._schemas[resource_type][field_name]
        )
        self._rust.set_resource_field(_schema_name(resource_type), field_name, copy.deepcopy(value))
        self._resources.add(resource_type)
        self._note_resource_update()

    def resource_snapshot(self, resource_type: type[Any]) -> object:
        self.validate_schema(resource_type)
        resource_constructor = cast(type[Any], resource_type)
        values = {
            field.name: self.get_resource_field(resource_type, field.name)
            for field in fields(resource_constructor)
        }
        return resource_constructor(**values)

    # ---------------------------------------------------------------- events
    def emit_event(self, event: object, *, expected_type: type[Any] | None = None) -> None:
        event_type = expected_type or type(event)
        if expected_type is not None and type(event) is not expected_type:
            raise ComponentSchemaError(
                f"Expected ECS event {expected_type.__name__}, got {type(event).__name__}."
            )
        _validate_event_value(event)
        self._register_event_type(event_type)
        payload = _event_payload_to_bridge(event)
        self._rust.emit_event(_schema_name(event_type), payload)
        self._events.setdefault(event_type, []).append((self._ecs_frame, copy.deepcopy(event)))
        self._diagnostics["ecs_events_emitted"] += 1

    def read_events(self, event_type: type[ComponentT]) -> tuple[ComponentT, ...]:
        events = tuple(
            cast(ComponentT, copy.deepcopy(event)) for _, event in self._events.get(event_type, ())
        )
        self._diagnostics["ecs_events_read"] += len(events)
        return events

    def clear_events(self, event_type: type[Any] | None = None) -> None:
        if event_type is None:
            self._events.clear()
            self._rust.clear_events(None)
            return
        self._events.pop(event_type, None)
        self._rust.clear_events(_schema_name(event_type))

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
        self._prepare_scheduled_physical_plan(scheduled)
        self._systems.append(scheduled)
        self._systems = self._sorted_systems()
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
        self._diagnostics["ecs_systems_registered"] = len(self._systems)

    def enable_system(self, handle: SystemHandle | str) -> None:
        self._set_system_enabled(handle, True)

    def disable_system(self, handle: SystemHandle | str) -> None:
        self._set_system_enabled(handle, False)

    def run_pre_draw_systems(self) -> None:
        self._diagnostics["ecs_pre_draw_runs"] += 1
        self._begin_change_frame()
        self._sync_python_changes_to_rust()
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
        if _is_direct_udf_action(action):
            action.execute(self, [{}])
            self._sync_python_changes_to_rust()
            return
        if _is_sequence_action(action):
            for child in cast(Any, action).children:
                self._run_system_action(scheduled, child)
            return
        if _contains_direct_udf_action(action):
            raise SystemPlanError(
                "Python UDF actions can only appear as standalone actions or inside "
                "do_in_order() sequences; non-UDF ECS work still executes in Rust."
            )
        self._run_physical_system(scheduled, action)

    def _prepare_scheduled_physical_plan(self, scheduled: _ScheduledSystem) -> None:
        action = scheduled.built.plan.action
        if _is_direct_udf_action(action) or _contains_direct_udf_action(action):
            return
        payload = self._build_and_compile_payload(scheduled, scheduled.built)
        scheduled.physical_payload = payload
        scheduled.physical_payload_dynamic = bool(payload.get("dynamic", False))

    def _build_and_compile_payload(
        self, scheduled: _ScheduledSystem, built: BuiltSystem
    ) -> dict[str, Any]:
        schema_fingerprint: int | None = None
        try:
            payload = build_physical_payload(self, built)
            schema_fingerprint = self._rust.schema_fingerprint()
            if scheduled.physical_plan_handle is not None:
                self._rust.release_compiled_plan(scheduled.physical_plan_handle)
                scheduled.physical_plan_handle = None
            summary = self._rust.compile_bridge_plan(payload)
            scheduled.physical_plan_handle = int(summary["handle"])
            scheduled.physical_schema_fingerprint = schema_fingerprint
            scheduled.physical_error_reason = None
            self._diagnostics["ecs_physical_plan_compiles"] += 1
            return payload
        except PhysicalPlanUnsupported as exc:
            message = (
                f"ECS system {scheduled.handle.name!r} cannot execute in Rust ECS: {exc}. "
                "Python fallback execution has been removed; only explicit @ecs.udf actions "
                "may execute in Python."
            )
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
            scheduled.physical_schema_fingerprint = schema_fingerprint
            scheduled.physical_error_reason = str(exc)
            self._diagnostics["ecs_physical_plan_errors"] += 1
            raise SystemPlanError(message) from exc
        except (AttributeError, ValueError) as exc:
            scheduled.physical_payload = None
            scheduled.physical_plan_handle = None
            scheduled.physical_schema_fingerprint = schema_fingerprint
            scheduled.physical_error_reason = str(exc)
            self._diagnostics["ecs_physical_plan_compile_errors"] += 1
            raise SystemPlanError(
                f"ECS system {scheduled.handle.name!r} could not compile for Rust ECS: {exc}"
            ) from exc

    def _run_physical_system(
        self, scheduled: _ScheduledSystem, action: Action | None = None
    ) -> None:
        use_scheduled_cache = action is None or action is scheduled.built.plan.action
        temporary_handle: int | None = None
        execution_payload: dict[str, Any] | None = None
        try:
            if use_scheduled_cache:
                schema_fingerprint = self._rust.schema_fingerprint()
                needs_recompile = (
                    scheduled.physical_plan_handle is None
                    or scheduled.physical_schema_fingerprint != schema_fingerprint
                    or scheduled.physical_payload_dynamic
                )
                if needs_recompile:
                    payload = self._build_and_compile_payload(scheduled, scheduled.built)
                    scheduled.physical_payload = payload
                    scheduled.physical_payload_dynamic = bool(payload.get("dynamic", False))
                execution_payload = scheduled.physical_payload
                if scheduled.physical_plan_handle is None:
                    raise SystemPlanError(
                        f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                    )
                handle = scheduled.physical_plan_handle
            else:
                assert action is not None
                built = replace(scheduled.built, plan=action.plan())
                payload = self._build_and_compile_payload(scheduled, built)
                execution_payload = payload
                temporary_handle = scheduled.physical_plan_handle
                if temporary_handle is None:
                    raise SystemPlanError(
                        f"ECS system {scheduled.handle.name!r} did not produce a Rust plan handle."
                    )
                scheduled.physical_payload = None
                scheduled.physical_plan_handle = None
                scheduled.physical_payload_dynamic = False
                handle = temporary_handle

            self._refresh_rust_input_states(execution_payload)
            report = self._rust.execute_compiled_plan(handle, self._has_change_filtered_systems())
        except (AttributeError, ValueError) as exc:
            if use_scheduled_cache:
                scheduled.physical_payload = None
                scheduled.physical_plan_handle = None
                scheduled.physical_error_reason = str(exc)
            self._diagnostics["ecs_physical_execution_errors"] += 1
            raise SystemExecutionError(
                f"ECS system {scheduled.handle.name!r} could not execute in Rust ECS: {exc}"
            ) from exc
        finally:
            if temporary_handle is not None:
                self._rust.release_compiled_plan(temporary_handle)
        self._apply_physical_report(report)
        self._diagnostics["ecs_physical_system_runs"] += 1
        self._diagnostics["ecs_physical_rows_scanned"] += int(report.get("rows_scanned", 0))
        self._diagnostics["ecs_physical_fields_written"] += int(report.get("fields_written", 0))
        self._diagnostics["ecs_physical_resource_fields_written"] += int(
            report.get("resource_fields_written", 0)
        )
        self._diagnostics["ecs_events_emitted"] += int(report.get("events_emitted", 0))
        for counter in (
            "spatial_indexes_built",
            "spatial_candidate_rows",
            "spatial_exact_rows",
            "spatial_false_positive_rows",
            "spatial_deduplicated_pairs",
            "spatial_algorithm_hash_grid",
            "spatial_algorithm_quadtree",
            "spatial_algorithm_octree",
            "spatial_algorithm_hilbert_curve",
        ):
            self._diagnostics[f"ecs_{counter}"] += int(report.get(counter, 0))
        duplicate_writes = int(report.get("duplicate_writes", 0))
        if duplicate_writes:
            self._diagnostics["ecs_physical_duplicate_writes"] += duplicate_writes
            self.record_ambiguity(
                "ECS do_in_parallel()/Rust physical execution wrote the same field more "
                "than once; deterministic last-write-wins is used. Consider group_by(...).any()."
            )

    def _has_change_filtered_systems(self) -> bool:
        for scheduled in self._systems:
            for query in scheduled.built.queries:
                spec = query.spec
                if isinstance(spec, QuerySpec) and any(
                    isinstance(term, ChangeTerm) for term in spec.terms
                ):
                    return True
        return False

    def _refresh_rust_input_states(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            return
        for expr in payload.get("expressions", ()):  # tiny input binding pass; not ECS execution
            if not isinstance(expr, dict) or expr.get("kind") != "input_state":
                continue
            name = str(expr.get("name", ""))
            code = expr.get("code")
            int_code = int(code) if code is not None else None
            if name == "dt":
                self._rust.set_input_state("dt", _current_delta_time(self))
            elif name == "key_down" and int_code is not None:
                self._rust.set_input_state("key_down", _current_key_down(self, int_code), int_code)

    def contexts_for_system(self, built: BuiltSystem) -> list[dict[object, Any]]:
        query_rows: list[list[EntityView]] = []
        for query in built.queries:
            query_rows.append(self.match_query(cast(QuerySpec, query.spec)))
        if not query_rows:
            return [{}]
        contexts: list[dict[object, Any]] = []
        for combo in itertools.product(*query_rows):
            ctx: dict[object, Any] = {}
            for query, entity in zip(built.queries, combo, strict=True):
                ctx[query] = entity
            contexts.append(ctx)
        self._diagnostics["ecs_rows_scanned"] += len(contexts)
        return contexts

    def match_query(self, spec: QuerySpec) -> list[EntityView]:
        components: list[type[Any]] = []
        tags: list[object] = []
        change_terms: list[ChangeTerm] = []
        for term in spec.terms:
            if isinstance(term, TagTerm):
                tags.append(term.value)
            elif isinstance(term, ChangeTerm):
                self.validate_schema(term.component_type)
                change_terms.append(term)
                if term.kind != "removed" and term.component_type not in components:
                    components.append(term.component_type)
            elif isinstance(term, type):
                self.validate_schema(term)
                components.append(term)
            else:
                raise SystemPlanError(f"Unsupported ECS query term {term!r}.")
        matches = list(self.iter_entities(*components, tags=tags))
        if change_terms:
            matches = [
                entity for entity in matches if self._matches_change_terms(entity, change_terms)
            ]
            self._diagnostics["ecs_change_filtered_rows"] += len(matches)
        return matches

    def expand_context_for_condition(
        self, ctx: dict[object, Any], condition: Expression
    ) -> list[dict[object, Any]]:
        return list(self.iter_join_contexts_for(ctx, condition))

    def iter_join_contexts_for(
        self,
        base_ctx: dict[object, Any],
        expr: Expression,
        *,
        include_query: QueryProxy | None = None,
    ) -> Iterator[dict[object, Any]]:
        queries = expression_queries(expr)
        if include_query is not None:
            queries.add(include_query)
        missing = sorted(
            (query for query in queries if query not in base_ctx), key=lambda q: q.name
        )
        if not missing:
            yield dict(base_ctx)
            return
        matches = [self.match_query(cast(QuerySpec, query.spec)) for query in missing]
        for combo in itertools.product(*matches):
            joined = dict(base_ctx)
            for query, entity in zip(missing, combo, strict=True):
                joined[query] = entity
            yield joined

    def iter_join_contexts_for_queries(
        self, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
    ) -> Iterator[dict[object, Any]]:
        missing = sorted(
            (query for query in set(queries) if query not in base_ctx), key=lambda q: q.name
        )
        if not missing:
            yield dict(base_ctx)
            return
        matches = [self.match_query(cast(QuerySpec, query.spec)) for query in missing]
        for combo in itertools.product(*matches):
            joined = dict(base_ctx)
            for query, entity in zip(missing, combo, strict=True):
                joined[query] = entity
            yield joined

    def write_key(
        self, target: FieldExpression, ctx: dict[object, Any]
    ) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
        if isinstance(target.source, QueryProxy):
            entity = ctx[target.source]
            return (entity.entity.index, target.component_type, target.field_name)
        return ("resource", target.component_type, target.field_name)

    def check_parallel_children(self, children: tuple[Action, ...]) -> None:
        seen: set[tuple[object, type[Any], str]] = set()
        for child in children:
            targets = action_write_targets(child)
            conflict = seen & targets
            if conflict:
                message = (
                    "ECS do_in_parallel() children write overlapping targets; "
                    "deterministic last-write-wins is used."
                )
                if self.strict:
                    raise SystemPlanError(message)
                self.record_ambiguity(message)
                return
            seen.update(targets)

    def execute_parallel_children(
        self, children: tuple[Action, ...], contexts: list[dict[object, Any]]
    ) -> None:
        del children, contexts
        raise SystemExecutionError(
            "Python ECS parallel execution has been removed; use the Rust physical executor."
        )

    def materialize_udf_arg(self, arg: object) -> object:
        if isinstance(arg, QueryProxy):
            return self.match_query(cast(QuerySpec, arg.spec))
        return arg

    def _register_event_type(self, event_type: type[Any]) -> None:
        self._event_types[_schema_name(event_type)] = event_type
        if is_dataclass(event_type):
            self.validate_schema(event_type)

    # -------------------------------------------------------------- Rust sync
    def _sync_python_changes_to_rust(self) -> None:
        # Rust owns canonical ECS storage. Python component/resource views write through
        # immediately, so there is no mirrored Python storage to flush before systems run.
        return

    def _sync_component_fields_to_rust(
        self, entity: Entity, component_type: type[Any], component: object
    ) -> None:
        if not self._mirror_writes_to_rust:
            return
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
        if not self._mirror_writes_to_rust:
            return
        self._rust.set_field(
            entity.index,
            entity.generation,
            _schema_name(component_type),
            field_name,
            copy.deepcopy(value),
        )

    def _sync_resources_to_rust(self) -> None:
        return

    def _sync_resource_to_rust(self, resource_type: type[Any], resource: object) -> None:
        if not self._mirror_writes_to_rust:
            return
        self._rust.insert_resource(_schema_name(resource_type), _dataclass_field_dict(resource))

    def _sync_resource_field_to_rust(
        self, resource_type: type[Any], field_name: str, value: object
    ) -> None:
        if not self._mirror_writes_to_rust:
            return
        self._rust.set_resource_field(_schema_name(resource_type), field_name, copy.deepcopy(value))

    def _apply_physical_report(self, report: dict[str, Any]) -> None:
        previous_defer_spatial = self._defer_spatial_invalidation
        previous_spatial_invalidated = self._spatial_invalidated_deferred
        self._defer_spatial_invalidation = True
        self._spatial_invalidated_deferred = False
        try:
            for write in report.get("component_writes", ()):
                component_type = self._component_type_for_schema(str(write["component"]))
                entity = Entity(int(write["index"]), int(write["generation"]), self._world_id)
                self._mark_component_changed(entity, component_type)
            for event in report.get("events", ()):
                event_type = self._component_type_for_schema(str(event["event_type"]))
                payload = _event_payload_from_bridge(event_type, event["payload"])
                self._events.setdefault(event_type, []).append(
                    (self._ecs_frame, copy.deepcopy(payload))
                )
            for write in report.get("resource_writes", ()):
                self._component_type_for_schema(str(write["resource"]))
                self._note_resource_update()
        finally:
            invalidated = self._spatial_invalidated_deferred
            self._defer_spatial_invalidation = previous_defer_spatial
            self._spatial_invalidated_deferred = previous_spatial_invalidated or invalidated
            if invalidated and not previous_defer_spatial:
                self._spatial_invalidated_deferred = previous_spatial_invalidated
                self._invalidate_spatial_indexes()

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
        if strict is not None:
            self.strict = bool(strict)
        if warn_on_ambiguity is not None:
            self.warn_on_ambiguity = bool(warn_on_ambiguity)

    def diagnostics(self) -> dict[str, Any]:
        enabled = sum(1 for system in self._systems if system.enabled)
        data: dict[str, Any] = dict(self._diagnostics)
        data.update(
            {
                "ecs_systems_registered": len(self._systems),
                "ecs_systems_enabled": enabled,
                "ecs_entities_alive": self._rust.alive_count(),
                "ecs_rust_core": "available",
                "ecs_rust_entities_alive": self._rust.alive_count(),
                "ecs_rust_component_schemas_total": self._rust.schema_count(),
                "ecs_rust_compiled_plans": self._rust.compiled_plan_count(),
                "ecs_strict": self.strict,
                "ecs_warn_on_ambiguity": self.warn_on_ambiguity,
                "messages": list(self._messages),
            }
        )
        return data

    def reset_diagnostics(self) -> None:
        self._diagnostics.clear()
        self._messages.clear()

    def record_ambiguity(self, message: str) -> None:
        if self.strict:
            self._diagnostics["ecs_strict_mode_errors"] += 1
            raise SystemPlanError(message)
        self._diagnostics["ecs_ambiguity_warnings"] += 1
        self._messages.append(message)
        if self.warn_on_ambiguity:
            warnings.warn(message, RuntimeWarning, stacklevel=3)
        else:
            self._diagnostics["ecs_ambiguity_warnings_suppressed"] += 1

    def _note_row_update(self) -> None:
        self._diagnostics["ecs_rows_updated"] += 1
        self._invalidate_spatial_indexes()

    def _note_field_update(self, entity: Entity, component_type: type[Any]) -> None:
        self._diagnostics["ecs_rows_updated"] += 1
        self._changed_components.add(_component_key(entity, component_type))
        self._invalidate_spatial_indexes()

    def _note_resource_update(self) -> None:
        self._diagnostics["ecs_resource_updates"] += 1
        self._expression_eval_cache.clear()

    def _invalidate_spatial_indexes(self, *, clear_only: bool = False) -> None:
        if self._defer_spatial_invalidation and not clear_only:
            self._spatial_invalidated_deferred = True
            self._diagnostics["ecs_spatial_deferred_invalidations"] += 1
            return
        if not clear_only:
            self._spatial_epoch += 1
        self._spatial_index_cache.clear()
        self._spatial_relation_cache.clear()
        self._spatial_aggregate_cache.clear()
        self._expression_eval_cache.clear()

    def configure_system_set(
        self,
        name: str,
        *,
        order: int | None = None,
        enabled: bool | None = None,
        run_if: Callable[[], bool] | None = None,
    ) -> None:
        self._system_sets[name] = _SystemSetConfig(order=order, enabled=enabled, run_if=run_if)
        self._diagnostics["ecs_schedule_rebuilds"] += 1

    def _system_enabled(self, scheduled: _ScheduledSystem) -> bool:
        config = self._system_sets.get(scheduled.set_name or "")
        if config is not None and config.enabled is False:
            return False
        return scheduled.enabled

    def _system_run_condition(self, scheduled: _ScheduledSystem) -> bool:
        config = self._system_sets.get(scheduled.set_name or "")
        if config is not None and config.run_if is not None and not bool(config.run_if()):
            return False
        return scheduled.run_if is None or bool(scheduled.run_if())

    def _effective_order(self, scheduled: _ScheduledSystem) -> int:
        config = self._system_sets.get(scheduled.set_name or "")
        return scheduled.order if config is None or config.order is None else config.order

    def _sorted_systems(self) -> list[_ScheduledSystem]:
        systems = list(self._systems)
        by_name = {system.handle.name: system for system in systems}
        by_id = {system.handle.id: system for system in systems}
        edges: dict[int, set[int]] = {system.handle.id: set() for system in systems}
        incoming: dict[int, set[int]] = {system.handle.id: set() for system in systems}

        def resolve(ref: SystemHandle | str) -> _ScheduledSystem:
            if isinstance(ref, SystemHandle):
                try:
                    return by_id[ref.id]
                except KeyError as exc:
                    raise SystemPlanError(f"Unknown ECS system dependency {ref!r}.") from exc
            try:
                return by_name[ref]
            except KeyError as exc:
                raise SystemPlanError(f"Unknown ECS system dependency {ref!r}.") from exc

        for system in systems:
            for before_ref in system.before:
                target = resolve(before_ref)
                edges[system.handle.id].add(target.handle.id)
                incoming[target.handle.id].add(system.handle.id)
            for after_ref in system.after:
                source = resolve(after_ref)
                edges[source.handle.id].add(system.handle.id)
                incoming[system.handle.id].add(source.handle.id)

        stable = {
            system.handle.id: (self._effective_order(system), system.handle.id)
            for system in systems
        }

        def stable_key(system_id: int) -> tuple[int, int]:
            return stable[system_id]

        ready = sorted(
            (system_id for system_id, deps in incoming.items() if not deps),
            key=stable_key,
        )
        ordered_ids: list[int] = []
        while ready:
            system_id = ready.pop(0)
            ordered_ids.append(system_id)
            for target_id in sorted(edges[system_id], key=stable_key):
                incoming[target_id].remove(system_id)
                if not incoming[target_id]:
                    ready.append(target_id)
                    ready.sort(key=stable_key)
        if len(ordered_ids) != len(systems):
            cycle_ids = [system_id for system_id, deps in incoming.items() if deps]
            cycle_names = [by_id[system_id].handle.name for system_id in cycle_ids]
            raise SystemPlanError(
                "ECS system dependency cycle detected: " + " -> ".join(sorted(cycle_names))
            )
        return [by_id[system_id] for system_id in ordered_ids]

    def _component_values_snapshot(self) -> dict[tuple[int, int, type[Any]], object]:
        # Component values are Rust-owned. This compatibility helper intentionally
        # returns no value mirror; change detection is tracked by structural/write events.
        return {}

    def _begin_change_frame(self) -> None:
        self._ecs_frame += 1
        self._rust.set_frame(self._ecs_frame)
        self._events = {
            event_type: [(frame, event) for frame, event in events if frame >= self._ecs_frame - 1]
            for event_type, events in self._events.items()
        }
        self._diagnostics["ecs_change_detection_refreshes"] += 1

    def _finalize_change_frame(self) -> None:
        self._component_snapshot = {}
        self._added_components.clear()
        self._changed_components.clear()
        self._removed_components.clear()

    def _mark_component_added(self, entity: Entity, component_type: type[Any]) -> None:
        key = _component_key(entity, component_type)
        self._added_components.add(key)
        self._changed_components.add(key)
        self._removed_components.discard(key)

    def _mark_component_changed(self, entity: Entity, component_type: type[Any]) -> None:
        key = _component_key(entity, component_type)
        if key not in self._added_components:
            self._changed_components.add(key)
        self._invalidate_spatial_indexes()

    def _mark_component_removed(self, entity: Entity, component_type: type[Any]) -> None:
        key = _component_key(entity, component_type)
        self._removed_components.add(key)
        self._added_components.discard(key)
        self._changed_components.discard(key)

    def _matches_change_terms(self, entity: EntityView, terms: Iterable[ChangeTerm]) -> bool:
        for term in terms:
            key = _component_key(entity.entity, term.component_type)
            if term.kind == "added" and key not in self._added_components:
                return False
            if term.kind == "changed" and key not in self._changed_components:
                return False
            if term.kind == "removed" and key not in self._removed_components:
                return False
        return True

    def _set_system_enabled(self, handle: SystemHandle | str, enabled: bool) -> None:
        for scheduled in self._systems:
            if _handle_matches(scheduled.handle, handle):
                scheduled.enabled = enabled
                return
        raise SystemPlanError(f"Unknown ECS system {handle!r}.")


def _handle_matches(handle: SystemHandle, value: SystemHandle | str) -> bool:
    return handle == value if isinstance(value, SystemHandle) else handle.name == value


def _is_direct_udf_action(action: Action) -> bool:
    return isinstance(action, DefaultAction) and action.kind == "udf"


def _is_sequence_action(action: Action) -> bool:
    return isinstance(action, DefaultAction) and action.kind == "sequence"


def _contains_direct_udf_action(action: Action) -> bool:
    if _is_direct_udf_action(action):
        return True
    if isinstance(action, DefaultAction):
        return any(_contains_direct_udf_action(child) for child in action.children)
    if isinstance(action, ForEachAction):
        return _contains_direct_udf_action(action.body)
    if isinstance(action, WhenAction):
        if any(_contains_direct_udf_action(branch) for _, branch in action.branches):
            return True
        return action.otherwise_action is not None and _contains_direct_udf_action(
            action.otherwise_action
        )
    return False


def _component_key(entity: Entity, component_type: type[Any]) -> tuple[int, int, type[Any]]:
    return (entity.index, entity.generation, component_type)


def _validate_event_value(event: object) -> None:
    if is_dataclass(event) or isinstance(event, bool | int | float | str):
        return
    raise ComponentSchemaError(
        "ECS events must be dataclass instances or scalar bool/int/float/str values."
    )


def _event_payload_to_bridge(event: object) -> object:
    if is_dataclass(event):
        return _dataclass_field_dict(event)
    return copy.deepcopy(event)


def _event_payload_from_bridge(event_type: type[Any], payload: object) -> object:
    if is_dataclass(event_type):
        if not isinstance(payload, dict):
            raise SystemExecutionError(
                f"Rust ECS returned non-struct payload for event {event_type.__name__}."
            )
        return event_type(**copy.deepcopy(payload))
    return copy.deepcopy(payload)


def _schema_name(component_type: type[Any]) -> str:
    return f"{component_type.__module__}.{component_type.__qualname__}"


def _tag_name(tag: object) -> str:
    value = str(tag)
    if not value:
        raise ComponentSchemaError("ECS tag values cannot be empty.")
    return value


def _current_delta_time(world: EcsWorld) -> float:
    context = getattr(world, "context", None)
    if context is None:
        return 0.0
    return float(getattr(context, "delta_time", 0.0))


def _current_key_down(world: EcsWorld, key: int) -> bool:
    context = getattr(world, "context", None)
    if context is None:
        return False
    key_is_down = getattr(context, "key_is_down", None)
    if not callable(key_is_down):
        return False
    return bool(key_is_down(key))


def _dataclass_field_dict(value: object) -> dict[str, object]:
    dataclass_value = cast(Any, value)
    return {
        field.name: copy.deepcopy(getattr(dataclass_value, field.name))
        for field in fields(dataclass_value)
    }


def _storage_type_for(
    annotation: object, component_type: type[Any], field_name: str
) -> StorageType:
    origin = get_origin(annotation)
    args = get_args(annotation)
    marker = None
    if origin is Annotated:
        annotation = args[0]
        marker = next((arg for arg in args[1:] if isinstance(arg, StorageType)), None)
        if marker is None:
            raise ComponentSchemaError(
                f"Unsupported ECS Annotated metadata for {component_type.__name__}.{field_name}."
            )
    if marker is not None:
        return marker
    if annotation is bool:
        return Bool
    if annotation is int:
        return Int64
    if annotation is float:
        return Float64
    if annotation is str:
        return String
    raise ComponentSchemaError(
        f"Unsupported ECS field annotation for {component_type.__name__}.{field_name}: "
        f"{annotation!r}. ECS supports bool, int, float, str, and Annotated storage markers."
    )


def _validate_storage_value(
    component_type: type[Any], field_name: str, value: object, storage_type: StorageType
) -> None:
    if storage_type.fixed_length is not None:
        if not isinstance(value, tuple | list) or len(value) != storage_type.fixed_length:
            raise ComponentSchemaError(
                f"{component_type.__name__}.{field_name} expects {storage_type.name} with "
                f"{storage_type.fixed_length} numeric values, got {value!r}."
            )
        for item in value:
            if not isinstance(item, int | float):
                raise ComponentSchemaError(
                    f"{component_type.__name__}.{field_name} expects numeric vector values, "
                    f"got {value!r}."
                )
        return
    if storage_type.element_type is not None and storage_type.python_type is list:
        if not isinstance(value, list):
            raise ComponentSchemaError(
                f"{component_type.__name__}.{field_name} expects {storage_type.name}, "
                f"got {value!r}."
            )
        for item in value:
            _validate_storage_value(component_type, field_name, item, storage_type.element_type)
        return
    if storage_type.python_type is float:
        if not isinstance(value, int | float):
            raise ComponentSchemaError(
                f"{component_type.__name__}.{field_name} expects {storage_type.name}, "
                f"got {value!r}."
            )
        return
    if storage_type.python_type is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ComponentSchemaError(
                f"{component_type.__name__}.{field_name} expects {storage_type.name}, "
                f"got {value!r}."
            )
        if storage_type.min_value is not None and value < storage_type.min_value:
            raise ValueError(
                f"{component_type.__name__}.{field_name} underflows {storage_type.name}."
            )
        if storage_type.max_value is not None and value > storage_type.max_value:
            raise ValueError(
                f"{component_type.__name__}.{field_name} overflows {storage_type.name}."
            )
        return
    if not isinstance(value, storage_type.python_type):
        raise ComponentSchemaError(
            f"{component_type.__name__}.{field_name} expects {storage_type.name}, got {value!r}."
        )


__all__ = ["EcsWorld", "Entity", "EntityView", "MutEntity", "SystemHandle"]
