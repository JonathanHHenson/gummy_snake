"""Small helper functions for ECS physical payload serialization."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, cast

from gummysnake.ecs.physical_payload.types import BridgeLiteral, PhysicalPlanUnsupported

if TYPE_CHECKING:  # pragma: no cover
    from _typeshed import DataclassInstance

    from gummysnake.ecs.spatial import Bounds2D, Bounds3D


def schema_name(component_type: type[object]) -> str:
    """Return the fully qualified schema name used by the Rust ECS bridge."""

    return f"{component_type.__module__}.{component_type.__qualname__}"


def key_code(key: int | str) -> int:
    """Convert an integer or one-character key name to the bridge key code."""

    if isinstance(key, int):
        return key
    if len(key) == 1:
        return ord(key)
    raise PhysicalPlanUnsupported(
        f"key_is_down() Rust input nodes require integer or one-character keys, got {key!r}"
    )


def bridge_literal_value(value: object) -> BridgeLiteral:
    """Convert a Python literal/dataclass tree into a Rust bridge literal value."""

    if is_dataclass(value) and not isinstance(value, type):
        dataclass_value = cast("DataclassInstance", value)
        return {
            field.name: bridge_literal_value(getattr(dataclass_value, field.name))
            for field in fields(dataclass_value)
        }
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [bridge_literal_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(bridge_literal_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): bridge_literal_value(item) for key, item in value.items()}
    raise PhysicalPlanUnsupported(f"literal value {value!r} is not supported by Rust ECS execution")


def spatial_bounds_values(bounds: Bounds2D | Bounds3D) -> list[float]:
    """Return serialized numeric bounds for a 2D or 3D spatial algorithm."""

    if hasattr(bounds, "min_z"):
        bounds3d = cast("Bounds3D", bounds)
        return [
            float(bounds3d.min_x),
            float(bounds3d.min_y),
            float(bounds3d.min_z),
            float(bounds3d.max_x),
            float(bounds3d.max_y),
            float(bounds3d.max_z),
        ]
    bounds2d = cast("Bounds2D", bounds)
    return [
        float(bounds2d.min_x),
        float(bounds2d.min_y),
        float(bounds2d.max_x),
        float(bounds2d.max_y),
    ]
