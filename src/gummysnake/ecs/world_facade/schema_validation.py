"""Dataclass schema validation for the public ECS world facade.

The facade discovers and validates Python dataclass schemas here, then registers
only schema metadata with the Rust bridge. Values and columns remain owned by
Rust; this module never keeps component or resource data.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any, get_type_hints

from gummysnake.ecs.schema_helpers import _schema_name, _storage_type_for, _validate_storage_value
from gummysnake.ecs.types import StorageType
from gummysnake.ecs.value_types import DataclassInstance
from gummysnake.exceptions import ComponentSchemaError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world_facade.world import EcsWorld


def validate_schema(world: EcsWorld, component_type: type[Any]) -> dict[str, StorageType]:
    """Validate, register, and cache the Rust storage schema for one dataclass type."""

    cached = world._schemas.get(component_type)
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
        world._rust.register_schema(
            _schema_name(component_type),
            [(field_name, storage_type.name) for field_name, storage_type in schema.items()],
        )
    except ValueError as exc:
        if "unknown ECS storage type" not in str(exc):
            raise
        # Older editable builds may expose the ECS ABI before vector/list markers were added.
        # Keep Python-side schema validation functional; a rebuilt Rust bridge records the
        # exact storage names.
        world._diagnostics["ecs_rust_schema_registration_fallbacks"] += 1
    world._schemas[component_type] = schema
    world._diagnostics["ecs_component_schemas_total"] = len(world._schemas)
    world._diagnostics["ecs_rust_component_schemas_total"] = world._rust.schema_count()
    return schema


def validate_value(
    world: EcsWorld, value: DataclassInstance, expected_type: type[Any] | None = None
) -> None:
    """Validate a component, resource, or event value against its registered schema."""

    component_type = expected_type or type(value)
    validate_schema(world, component_type)
    if not is_dataclass(value):
        raise ComponentSchemaError(f"ECS component values must be dataclass instances: {value!r}.")
    if type(value) is not component_type:
        raise ComponentSchemaError(
            f"Expected {component_type.__name__}, got {type(value).__name__}."
        )
    for field_name, storage_type in world._schemas[component_type].items():
        raw = getattr(value, field_name)
        _validate_storage_value(component_type, field_name, raw, storage_type)
