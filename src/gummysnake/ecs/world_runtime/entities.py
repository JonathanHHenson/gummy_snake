"""Private helpers for ECS entity and component operations."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Iterator
from dataclasses import fields
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.runtime_views import Entity, EntityView
from gummysnake.ecs.schema_helpers import _schema_name, _tag_name, _validate_storage_value
from gummysnake.ecs.value_types import DataclassInstance, EcsStoredValue, EcsTag
from gummysnake.exceptions import (
    EntityNotFoundError,
    MissingComponentError,
    StaleEntityError,
    SystemExecutionError,
)

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def add_entity(
    world: EcsWorld, *components: DataclassInstance, tags: Iterable[EcsTag] = ()
) -> Entity:
    """Validate components and create one Rust-owned entity."""
    component_values: dict[type[Any], DataclassInstance] = {}
    for component in components:
        world._validate_value(component)
        component_values[type(component)] = component
    index, generation = world._rust.allocate_entity()
    entity = Entity(index, generation, world._world_id)
    for component_type, component in component_values.items():
        world._rust.add_component_default(index, generation, _schema_name(component_type))
        sync_component_fields_to_rust(world, entity, component_type, component)
        world._mark_component_added(entity, component_type)
    for tag in tags:
        world._rust.add_tag(index, generation, _tag_name(tag))
    world._diagnostics["ecs_entities_alive"] = world._rust.alive_count()
    world._invalidate_spatial_indexes()
    return entity


def despawn_entity(world: EcsWorld, entity: Entity) -> None:
    """Remove one entity and mark its components as removed for this frame."""
    slot(world, entity)
    removed_components = [
        component_type_for_schema(world, schema_name)
        for schema_name in world._rust.entity_components(entity.index, entity.generation)
    ]
    world._rust.despawn_entity(entity.index, entity.generation)
    for component_type in removed_components:
        world._mark_component_removed(entity, component_type)
    world._diagnostics["ecs_entities_alive"] = world._rust.alive_count()
    world._diagnostics["ecs_entity_generation_reuses"] += 1
    world._invalidate_spatial_indexes()


def add_component(world: EcsWorld, entity: Entity, component: DataclassInstance) -> None:
    """Validate and add or replace one component on an entity."""
    world._validate_value(component)
    slot(world, entity)
    upsert_component(world, entity, type(component), component)


def set_component(
    world: EcsWorld,
    entity: Entity,
    component: DataclassInstance,
    *,
    expected_type: type[Any] | None = None,
) -> None:
    """Validate and store a component in a specific component slot."""
    world._validate_value(component, expected_type)
    slot(world, entity)
    upsert_component(world, entity, expected_type or type(component), component)


def upsert_component(
    world: EcsWorld, entity: Entity, component_type: type[Any], component: DataclassInstance
) -> None:
    """Insert a missing component or update an existing component's fields."""
    existed = has_component(world, entity, component_type)
    if not existed:
        world._rust.add_component_default(
            entity.index, entity.generation, _schema_name(component_type)
        )
    sync_component_fields_to_rust(world, entity, component_type, component)
    if existed:
        world._note_field_update(entity, component_type)
    else:
        world._mark_component_added(entity, component_type)
        world._diagnostics["ecs_structural_commands_applied"] += 1
        world._invalidate_spatial_indexes()


def remove_component(world: EcsWorld, entity: Entity, component_type: type[Any]) -> None:
    """Remove one component type from an entity."""
    slot(world, entity)
    if not has_component(world, entity, component_type):
        raise MissingComponentError(component_type.__name__)
    world._rust.remove_component(entity.index, entity.generation, _schema_name(component_type))
    world._mark_component_removed(entity, component_type)
    world._diagnostics["ecs_structural_commands_applied"] += 1
    world._invalidate_spatial_indexes()


def add_tag(world: EcsWorld, entity: Entity, tag: EcsTag) -> None:
    """Add a tag if the entity does not already have it."""
    slot(world, entity)
    tag_name = _tag_name(tag)
    if tag_name not in world._rust.entity_tags(entity.index, entity.generation):
        world._rust.add_tag(entity.index, entity.generation, tag_name)
        world._diagnostics["ecs_structural_commands_applied"] += 1
        world._invalidate_spatial_indexes()


def remove_tag(world: EcsWorld, entity: Entity, tag: EcsTag) -> None:
    """Remove a tag if the entity currently has it."""
    slot(world, entity)
    tag_name = _tag_name(tag)
    if tag_name in world._rust.entity_tags(entity.index, entity.generation):
        world._rust.remove_tag(entity.index, entity.generation, tag_name)
        world._diagnostics["ecs_structural_commands_applied"] += 1
        world._invalidate_spatial_indexes()


def get_entity(world: EcsWorld, *components: type[Any], tags: Iterable[EcsTag] = ()) -> EntityView:
    """Return exactly one entity matching component and tag filters."""
    matches = list(iter_entities(world, *components, tags=tags))
    if len(matches) != 1:
        raise EntityNotFoundError(f"Expected exactly one ECS entity, found {len(matches)}.")
    return matches[0]


def try_get_entity(
    world: EcsWorld, *components: type[Any], tags: Iterable[EcsTag] = ()
) -> EntityView | None:
    """Return zero or one entity matching component and tag filters."""
    matches = list(iter_entities(world, *components, tags=tags))
    if len(matches) > 1:
        raise EntityNotFoundError(f"Expected zero or one ECS entity, found {len(matches)}.")
    return matches[0] if matches else None


def iter_entities(
    world: EcsWorld, *components: type[Any], tags: Iterable[EcsTag] = ()
) -> Iterator[EntityView]:
    """Yield entity views matching component and tag filters."""
    required_components = [_schema_name(component) for component in components]
    for component in components:
        world.validate_schema(component)
    required_tags = [_tag_name(tag) for tag in tags]
    for index, generation in world._rust.query_filtered(required_components, required_tags, [], []):
        yield EntityView(world, Entity(index, generation, world._world_id))


def iter_component_fields(
    world: EcsWorld,
    component_type: type[Any],
    *field_names: str,
    tags: Iterable[EcsTag] = (),
) -> Iterator[tuple[Any, ...]]:
    """Read selected component fields through one Rust-backed batch call."""
    world.validate_schema(component_type)
    schema = _schema_name(component_type)
    schema_fields = world._schemas[component_type]
    for field_name in field_names:
        if field_name not in schema_fields:
            raise AttributeError(field_name)
    required_tags = [_tag_name(tag) for tag in tags]
    rows = world._rust.query_component_fields([schema], required_tags, schema, list(field_names))
    return iter(rows)


def slot(world: EcsWorld, entity: Entity) -> None:
    """Validate that an entity handle belongs to this world and is still alive."""
    if entity.world_id != world._world_id:
        raise StaleEntityError("ECS entity belongs to a different world.")
    if entity.index < 0:
        raise StaleEntityError("ECS entity index is invalid.")
    try:
        world._rust.validate_entity(entity.index, entity.generation)
    except ValueError as exc:
        raise StaleEntityError("ECS entity handle is stale.") from exc


def has_component(world: EcsWorld, entity: Entity, component_type: type[Any]) -> bool:
    """Return whether an entity currently has one component type."""
    world.validate_schema(component_type)
    return _schema_name(component_type) in world._rust.entity_components(
        entity.index, entity.generation
    )


def get_component_field(
    world: EcsWorld, entity: Entity, component_type: type[Any], field_name: str
) -> EcsStoredValue:
    """Read one field from an entity component."""
    slot(world, entity)
    world.validate_schema(component_type)
    if field_name not in world._schemas[component_type]:
        raise AttributeError(field_name)
    try:
        return cast(
            EcsStoredValue,
            world._rust.get_field(
                entity.index, entity.generation, _schema_name(component_type), field_name
            ),
        )
    except ValueError as exc:
        raise MissingComponentError(
            f"Entity {entity.index}:{entity.generation} does not have "
            f"component {component_type.__name__}."
        ) from exc


def set_component_field(
    world: EcsWorld,
    entity: Entity,
    component_type: type[Any],
    field_name: str,
    value: EcsStoredValue,
) -> None:
    """Validate and write one field on an entity component."""
    slot(world, entity)
    world.validate_schema(component_type)
    if field_name not in world._schemas[component_type]:
        raise AttributeError(field_name)
    _validate_storage_value(
        component_type, field_name, value, world._schemas[component_type][field_name]
    )
    sync_component_field_to_rust(world, entity, component_type, field_name, value)
    world._note_field_update(entity, component_type)


def component_snapshot(
    world: EcsWorld, entity: Entity, component_type: type[Any]
) -> DataclassInstance:
    """Copy a component's fields into a new dataclass instance."""
    slot(world, entity)
    world.validate_schema(component_type)
    component_constructor = cast(type[Any], component_type)
    values = {
        field.name: get_component_field(world, entity, component_type, field.name)
        for field in fields(component_constructor)
    }
    return component_constructor(**values)


def sync_component_fields_to_rust(
    world: EcsWorld, entity: Entity, component_type: type[Any], component: DataclassInstance
) -> None:
    """Copy every dataclass field from Python into Rust-owned component storage."""
    for field in fields(component_type):
        world._rust.set_field(
            entity.index,
            entity.generation,
            _schema_name(component_type),
            field.name,
            copy.deepcopy(getattr(component, field.name)),
        )


def sync_component_field_to_rust(
    world: EcsWorld,
    entity: Entity,
    component_type: type[Any],
    field_name: str,
    value: EcsStoredValue,
) -> None:
    """Copy one Python value into Rust-owned component storage."""
    world._rust.set_field(
        entity.index,
        entity.generation,
        _schema_name(component_type),
        field_name,
        copy.deepcopy(value),
    )


def component_type_for_schema(world: EcsWorld, schema_name: str) -> type[Any]:
    """Return the Python dataclass type registered for a Rust schema name."""
    event_type = world._event_types.get(schema_name)
    if event_type is not None:
        return event_type
    for component_type in world._schemas:
        if _schema_name(component_type) == schema_name:
            return component_type
    raise SystemExecutionError(f"Rust ECS returned unknown component schema {schema_name!r}.")
