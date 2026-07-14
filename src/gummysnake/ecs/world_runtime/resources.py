"""Private helpers for ECS resources and events."""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.runtime_view_model import ResourceView
from gummysnake.ecs.schema_helpers import (
    _dataclass_field_dict,
    _event_payload_from_bridge,
    _event_payload_to_bridge,
    _schema_name,
    _validate_event_value,
    _validate_storage_value,
)
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsStoredValue
from gummysnake.exceptions import ComponentSchemaError, MissingResourceError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world_facade import EcsWorld


def set_resource(world: EcsWorld, resource: DataclassInstance) -> None:
    """Validate and store one dataclass resource in Rust-owned ECS storage."""
    world._validate_value(resource)
    world._rust.insert_resource(_schema_name(type(resource)), _dataclass_field_dict(resource))
    world._note_resource_update()


def get_resource[ResourceT](world: EcsWorld, resource_type: type[ResourceT]) -> ResourceT:
    """Return a mutable view for an existing ECS resource."""
    world.validate_schema(resource_type)
    if not world._rust.has_resource(_schema_name(resource_type)):
        raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.")
    return cast(ResourceT, ResourceView(world, resource_type))


def remove_resource(world: EcsWorld, resource_type: type[Any]) -> None:
    """Remove an existing ECS resource from Rust-owned storage."""
    world.validate_schema(resource_type)
    if not world._rust.has_resource(_schema_name(resource_type)):
        raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.")
    world._rust.remove_resource(_schema_name(resource_type))
    world._note_resource_update()


def get_resource_field(
    world: EcsWorld, resource_type: type[Any], field_name: str
) -> EcsStoredValue:
    """Read a single field from an existing ECS resource."""
    world.validate_schema(resource_type)
    if field_name not in world._schemas[resource_type]:
        raise AttributeError(field_name)
    try:
        return cast(
            EcsStoredValue, world._rust.resource_field(_schema_name(resource_type), field_name)
        )
    except ValueError as exc:
        raise MissingResourceError(f"Missing ECS resource {resource_type.__name__}.") from exc


def set_resource_field(
    world: EcsWorld, resource_type: type[Any], field_name: str, value: EcsStoredValue
) -> None:
    """Validate and write one field on an existing ECS resource."""
    world.validate_schema(resource_type)
    if field_name not in world._schemas[resource_type]:
        raise AttributeError(field_name)
    _validate_storage_value(
        resource_type, field_name, value, world._schemas[resource_type][field_name]
    )
    world._rust.set_resource_field(_schema_name(resource_type), field_name, copy.deepcopy(value))
    world._note_resource_update()


def resource_snapshot(world: EcsWorld, resource_type: type[Any]) -> DataclassInstance:
    """Copy an ECS resource into a new dataclass instance."""
    world.validate_schema(resource_type)
    resource_constructor = cast(type[Any], resource_type)
    values = {
        field.name: get_resource_field(world, resource_type, field.name)
        for field in fields(resource_constructor)
    }
    return resource_constructor(**values)


def emit_event(
    world: EcsWorld, event: EcsEventValue, *, expected_type: type[Any] | None = None
) -> None:
    """Validate and enqueue an event in the Rust-owned frame-local queue."""
    event_type = expected_type or type(event)
    if expected_type is not None and type(event) is not expected_type:
        raise ComponentSchemaError(
            f"Expected ECS event {expected_type.__name__}, got {type(event).__name__}."
        )
    _validate_event_value(event)
    register_event_type(world, event_type)
    payload = _event_payload_to_bridge(event)
    world._rust.emit_event(_schema_name(event_type), payload)


def read_events[ComponentT](
    world: EcsWorld, event_type: type[ComponentT]
) -> tuple[ComponentT, ...]:
    """Return deep-copied events of the requested type from the Rust event queue."""
    register_event_type(world, event_type)
    raw_events = world._rust.read_events(_schema_name(event_type))
    return tuple(
        cast(ComponentT, _event_payload_from_bridge(event_type, event["payload"]))
        for event in raw_events
    )


def clear_events(world: EcsWorld, event_type: type[Any] | None = None) -> None:
    """Clear all events or one event type from the Rust-owned queues."""
    world._rust.clear_events(None if event_type is None else _schema_name(event_type))


def register_event_type(world: EcsWorld, event_type: type[Any]) -> None:
    """Remember the Python dataclass type for events returned by the Rust bridge."""
    world._event_types[_schema_name(event_type)] = event_type
    if is_dataclass(event_type):
        world.validate_schema(event_type)
