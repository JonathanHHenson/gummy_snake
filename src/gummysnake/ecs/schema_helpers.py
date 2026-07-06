"""Shared helpers for ECS schema names, tags, and value conversion."""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
from typing import Annotated, Any, cast, get_args, get_origin

from gummysnake.ecs.types import Bool, Float64, Int64, StorageType, String
from gummysnake.exceptions import ComponentSchemaError, SystemExecutionError


def _schema_name(component_type: type[Any]) -> str:
    return f"{component_type.__module__}.{component_type.__qualname__}"


def _tag_name(tag: object) -> str:
    value = str(tag)
    if not value:
        raise ComponentSchemaError("ECS tag values cannot be empty.")
    return value


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
