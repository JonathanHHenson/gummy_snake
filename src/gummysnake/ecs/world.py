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
from dataclasses import dataclass, fields, is_dataclass
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin, get_type_hints

from gummysnake.ecs.actions import Action, action_write_targets
from gummysnake.ecs.expressions import (
    Expression,
    FieldExpression,
    QueryProxy,
    ResourceProxy,
    expression_queries,
)
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
    generation: int = 0
    alive: bool = False
    components: dict[type[Any], object] | None = None
    tags: set[object] | None = None


class EntityView:
    """Mutable Python view over an entity's components."""

    def __init__(self, world: EcsWorld, entity: Entity) -> None:
        self._world = world
        self.entity = entity

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        slot = self._world._slot(self.entity)
        assert slot.components is not None
        try:
            return cast(ComponentT, slot.components[component_type])
        except KeyError as exc:
            raise MissingComponentError(
                f"Entity {self.entity.index}:{self.entity.generation} does not have "
                f"component {component_type.__name__}."
            ) from exc

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
        self._resources: dict[type[Any], object] = {}
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
        component_map: dict[type[Any], object] = {}
        for component in components:
            self._validate_value(component)
            component_map[type(component)] = copy.deepcopy(component)
        index, generation = self._rust.allocate_entity()
        if index == len(self._slots):
            slot = _EntitySlot(
                generation=generation, alive=True, components=component_map, tags=set(tags)
            )
            self._slots.append(slot)
        else:
            slot = self._slots[index]
            slot.generation = generation
            slot.alive = True
            slot.components = component_map
            slot.tags = set(tags)
        entity = Entity(index, generation, self._world_id)
        for component_type in component_map:
            self._mark_component_added(entity, component_type)
        self._diagnostics["ecs_entities_alive"] += 1
        self._invalidate_spatial_indexes()
        return entity

    def despawn_entity(self, entity: Entity) -> None:
        slot = self._slot(entity)
        removed_components = list((slot.components or {}).keys())
        self._rust.despawn_entity(entity.index, entity.generation)
        for component_type in removed_components:
            self._mark_component_removed(entity, component_type)
        slot.alive = False
        slot.generation += 1
        slot.components = None
        slot.tags = None
        self._diagnostics["ecs_entities_alive"] -= 1
        self._diagnostics["ecs_entity_generation_reuses"] += 1
        self._invalidate_spatial_indexes()

    def add_component(self, entity: Entity, component: object) -> None:
        self._validate_value(component)
        slot = self._slot(entity)
        assert slot.components is not None
        component_type = type(component)
        slot.components[component_type] = copy.deepcopy(component)
        self._mark_component_added(entity, component_type)
        self._diagnostics["ecs_structural_commands_applied"] += 1
        self._invalidate_spatial_indexes()

    def set_component(
        self, entity: Entity, component: object, *, expected_type: type[Any] | None = None
    ) -> None:
        self._validate_value(component, expected_type)
        slot = self._slot(entity)
        assert slot.components is not None
        component_type = expected_type or type(component)
        slot.components[component_type] = copy.deepcopy(component)
        self._note_field_update(entity, component_type)

    def remove_component(self, entity: Entity, component_type: type[Any]) -> None:
        slot = self._slot(entity)
        assert slot.components is not None
        try:
            del slot.components[component_type]
        except KeyError as exc:
            raise MissingComponentError(component_type.__name__) from exc
        self._mark_component_removed(entity, component_type)
        self._diagnostics["ecs_structural_commands_applied"] += 1
        self._invalidate_spatial_indexes()

    def add_tag(self, entity: Entity, tag: object) -> None:
        slot = self._slot(entity)
        assert slot.tags is not None
        slot.tags.add(tag)
        self._diagnostics["ecs_structural_commands_applied"] += 1
        self._invalidate_spatial_indexes()

    def remove_tag(self, entity: Entity, tag: object) -> None:
        slot = self._slot(entity)
        assert slot.tags is not None
        slot.tags.discard(tag)
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
        tag_set = set(tags)
        for index, slot in enumerate(self._slots):
            if not slot.alive or slot.components is None or slot.tags is None:
                continue
            if (
                all(component in slot.components for component in components)
                and tag_set <= slot.tags
            ):
                yield EntityView(self, Entity(index, slot.generation, self._world_id))

    def _slot(self, entity: Entity) -> _EntitySlot:
        if entity.world_id != self._world_id:
            raise StaleEntityError("ECS entity belongs to a different world.")
        if entity.index < 0 or entity.index >= len(self._slots):
            raise StaleEntityError("ECS entity index is invalid.")
        slot = self._slots[entity.index]
        if not slot.alive or slot.generation != entity.generation:
            raise StaleEntityError("ECS entity handle is stale.")
        return slot

    # --------------------------------------------------------------- resources
    def set_resource(self, resource: object) -> None:
        self._validate_value(resource)
        self._resources[type(resource)] = copy.deepcopy(resource)

    def get_resource(self, resource_type: type[ResourceT]) -> ResourceT:
        self.validate_schema(resource_type)
        try:
            return cast(ResourceT, self._resources[resource_type])
        except KeyError as exc:
            raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.") from exc

    def remove_resource(self, resource_type: type[Any]) -> None:
        try:
            del self._resources[resource_type]
        except KeyError as exc:
            raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.") from exc

    # ---------------------------------------------------------------- events
    def emit_event(self, event: object, *, expected_type: type[Any] | None = None) -> None:
        event_type = expected_type or type(event)
        if expected_type is not None and type(event) is not expected_type:
            raise ComponentSchemaError(
                f"Expected ECS event {expected_type.__name__}, got {type(event).__name__}."
            )
        _validate_event_value(event)
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
            return
        self._events.pop(event_type, None)

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
        self._systems.append(
            _ScheduledSystem(
                handle,
                built,
                int(order),
                bool(enabled),
                before=tuple(before),
                after=tuple(after),
                run_if=run_if,
                set_name=set,
            )
        )
        self._systems = self._sorted_systems()
        self._diagnostics["ecs_systems_registered"] = len(self._systems)
        self._diagnostics["ecs_schedule_rebuilds"] += 1
        return handle

    def remove_system(self, handle: SystemHandle | str) -> None:
        before = len(self._systems)
        self._systems = [s for s in self._systems if not _handle_matches(s.handle, handle)]
        if len(self._systems) == before:
            raise SystemPlanError(f"Unknown ECS system {handle!r}.")
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
                scheduled.built.plan.action.execute(self, [{}])
            except Exception as exc:
                if isinstance(exc, SystemPlanError | SystemExecutionError):
                    raise
                raise SystemExecutionError(
                    f"ECS system {scheduled.handle.name!r} failed: {exc}"
                ) from exc

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
                    "deterministic fallback used."
                )
                if self.strict:
                    raise SystemPlanError(message)
                self.record_ambiguity(message)
                return
            seen.update(targets)

    def execute_parallel_children(
        self, children: tuple[Action, ...], contexts: list[dict[object, Any]]
    ) -> None:
        self.check_parallel_children(children)
        snapshot_slots = copy.deepcopy(self._slots)
        snapshot_resources = copy.deepcopy(self._resources)
        shared_spatial_index_cache: dict[object, object] = {}
        shared_spatial_relation_cache: dict[object, object] = {}
        shared_spatial_aggregate_cache: dict[object, object] = {}
        shared_expression_eval_cache: dict[object, object] = {}
        for child in children:
            child_world = self._parallel_child_world(snapshot_slots, snapshot_resources)
            child_world._spatial_index_cache = shared_spatial_index_cache
            child_world._spatial_relation_cache = shared_spatial_relation_cache
            child_world._spatial_aggregate_cache = shared_spatial_aggregate_cache
            child_world._expression_eval_cache = shared_expression_eval_cache
            child.execute(child_world, child_world._translate_contexts(contexts))
            self._merge_parallel_child(
                snapshot_slots,
                snapshot_resources,
                child_world,
                action_write_targets(child),
            )
            self._diagnostics.update(child_world._diagnostics)
            self._messages.extend(child_world._messages)

    def _parallel_child_world(
        self, snapshot_slots: list[_EntitySlot], snapshot_resources: dict[type[Any], object]
    ) -> EcsWorld:
        child = object.__new__(EcsWorld)
        child.context = self.context
        child._rust = self._rust
        child._world_id = self._world_id
        child._slots = copy.deepcopy(snapshot_slots)
        child._systems = []
        child._system_sets = copy.deepcopy(self._system_sets)
        child._next_system_id = self._next_system_id
        child._resources = copy.deepcopy(snapshot_resources)
        child.strict = self.strict
        child.warn_on_ambiguity = self.warn_on_ambiguity
        child._diagnostics = Counter()
        child._messages = []
        child._schemas = self._schemas
        child._spatial_epoch = self._spatial_epoch
        child._spatial_index_cache = {}
        child._spatial_relation_cache = {}
        child._spatial_aggregate_cache = {}
        child._expression_eval_cache = {}
        child._defer_spatial_invalidation = True
        child._spatial_invalidated_deferred = False
        child._ecs_frame = self._ecs_frame
        child._component_snapshot = copy.deepcopy(self._component_snapshot)
        child._added_components = set(self._added_components)
        child._changed_components = set(self._changed_components)
        child._removed_components = set(self._removed_components)
        child._events = copy.deepcopy(self._events)
        return child

    def _translate_contexts(self, contexts: list[dict[object, Any]]) -> list[dict[object, Any]]:
        translated: list[dict[object, Any]] = []
        for ctx in contexts:
            translated_ctx: dict[object, Any] = {}
            for key, value in ctx.items():
                if isinstance(value, EntityView):
                    translated_ctx[key] = EntityView(self, value.entity)
                else:
                    translated_ctx[key] = value
            translated.append(translated_ctx)
        return translated

    def _merge_parallel_child(
        self,
        snapshot_slots: list[_EntitySlot],
        snapshot_resources: dict[type[Any], object],
        child_world: EcsWorld,
        write_targets: set[tuple[object, type[Any], str]],
    ) -> None:
        component_fields: dict[type[Any], set[str]] = {}
        resource_fields: dict[type[Any], set[str]] = {}
        for source, component_type, field_name in write_targets:
            if isinstance(source, QueryProxy):
                component_fields.setdefault(component_type, set()).add(field_name)
            elif isinstance(source, ResourceProxy):
                resource_fields.setdefault(component_type, set()).add(field_name)

        for index, child_slot in enumerate(child_world._slots):
            snapshot_slot = snapshot_slots[index]
            if not child_slot.alive or child_slot.components is None:
                continue
            original_slot = self._slots[index]
            if original_slot.components is None:
                continue
            snapshot_components = snapshot_slot.components or {}
            for component_type, field_names in component_fields.items():
                child_component = child_slot.components.get(component_type)
                snapshot_component = snapshot_components.get(component_type)
                original_component = original_slot.components.get(component_type)
                if (
                    child_component is None
                    or snapshot_component is None
                    or original_component is None
                ):
                    continue
                for field_name in field_names:
                    child_value = getattr(child_component, field_name)
                    if child_value != getattr(snapshot_component, field_name):
                        setattr(original_component, field_name, copy.deepcopy(child_value))
                        self._note_field_update(
                            Entity(index, original_slot.generation, self._world_id), component_type
                        )
            if child_slot.tags != snapshot_slot.tags:
                original_slot.tags = copy.deepcopy(child_slot.tags)
                self._diagnostics["ecs_structural_commands_applied"] += 1
                self._invalidate_spatial_indexes()
        for resource_type, field_names in resource_fields.items():
            child_resource = child_world._resources.get(resource_type)
            snapshot_resource = snapshot_resources.get(resource_type)
            original_resource = self._resources.get(resource_type)
            if child_resource is None or snapshot_resource is None or original_resource is None:
                continue
            for field_name in field_names:
                child_value = getattr(child_resource, field_name)
                if child_value != getattr(snapshot_resource, field_name):
                    setattr(original_resource, field_name, copy.deepcopy(child_value))
                    self._note_resource_update()

    def materialize_udf_arg(self, arg: object) -> object:
        if isinstance(arg, QueryProxy):
            return self.match_query(cast(QuerySpec, arg.spec))
        return arg

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
                "ecs_entities_alive": sum(1 for slot in self._slots if slot.alive),
                "ecs_rust_core": "available",
                "ecs_rust_entities_alive": self._rust.alive_count(),
                "ecs_rust_component_schemas_total": self._rust.schema_count(),
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
        snapshot: dict[tuple[int, int, type[Any]], object] = {}
        for index, slot in enumerate(self._slots):
            if not slot.alive or slot.components is None:
                continue
            entity = Entity(index, slot.generation, self._world_id)
            for component_type, component in slot.components.items():
                snapshot[_component_key(entity, component_type)] = copy.deepcopy(component)
        return snapshot

    def _begin_change_frame(self) -> None:
        self._ecs_frame += 1
        self._events = {
            event_type: [(frame, event) for frame, event in events if frame >= self._ecs_frame - 1]
            for event_type, events in self._events.items()
        }
        current = self._component_values_snapshot()
        old_keys = set(self._component_snapshot)
        current_keys = set(current)
        self._added_components = current_keys - old_keys
        self._removed_components = old_keys - current_keys
        self._changed_components = set(self._added_components)
        for key in current_keys & old_keys:
            if current[key] != self._component_snapshot[key]:
                self._changed_components.add(key)
        self._diagnostics["ecs_change_detection_refreshes"] += 1

    def _finalize_change_frame(self) -> None:
        self._component_snapshot = self._component_values_snapshot()

    def _mark_component_added(self, entity: Entity, component_type: type[Any]) -> None:
        key = _component_key(entity, component_type)
        self._added_components.add(key)
        self._changed_components.add(key)
        self._removed_components.discard(key)

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


def _component_key(entity: Entity, component_type: type[Any]) -> tuple[int, int, type[Any]]:
    return (entity.index, entity.generation, component_type)


def _validate_event_value(event: object) -> None:
    if is_dataclass(event) or isinstance(event, bool | int | float | str):
        return
    raise ComponentSchemaError(
        "ECS events must be dataclass instances or scalar bool/int/float/str values."
    )


def _schema_name(component_type: type[Any]) -> str:
    return f"{component_type.__module__}.{component_type.__qualname__}"


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
