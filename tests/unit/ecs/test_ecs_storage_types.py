from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, get_type_hints

import pytest

from gummysnake.ecs import types as ecs_t
from gummysnake.ecs.schema_helpers import _storage_type_for, _validate_storage_value


@dataclass
class TypedValues:
    count: Annotated[int, ecs_t.UInt8]
    ratio: Annotated[float, ecs_t.Float32]
    samples: Annotated[list[int], ecs_t.List(ecs_t.Int16)]
    point: Annotated[tuple[float, float], ecs_t.Vec2F32]


def test_list_marker_preserves_element_identity_and_rejects_nested_lists() -> None:
    marker = ecs_t.List(ecs_t.UInt16)

    assert marker.name == "List[UInt16]"
    assert marker.element_type is ecs_t.UInt16
    with pytest.raises(TypeError, match="Nested"):
        ecs_t.List(marker)


def test_python_checked_validation_matches_rust_storage_policy() -> None:
    fields = get_type_hints(TypedValues, include_extras=True)
    count = _storage_type_for(fields["count"], TypedValues, "count")
    ratio = _storage_type_for(fields["ratio"], TypedValues, "ratio")
    samples = _storage_type_for(fields["samples"], TypedValues, "samples")
    point = _storage_type_for(fields["point"], TypedValues, "point")

    _validate_storage_value(TypedValues, "count", 255, count)
    with pytest.raises(ValueError, match="overflows UInt8"):
        _validate_storage_value(TypedValues, "count", 256, count)
    with pytest.raises(ValueError, match="underflows UInt8"):
        _validate_storage_value(TypedValues, "count", -1, count)

    _validate_storage_value(TypedValues, "ratio", 1.0 / 3.0, ratio)
    with pytest.raises(ValueError, match="finite Float32"):
        _validate_storage_value(TypedValues, "ratio", float("nan"), ratio)
    with pytest.raises(ValueError, match="overflows Float32"):
        _validate_storage_value(TypedValues, "ratio", 1e100, ratio)

    _validate_storage_value(TypedValues, "samples", [-32768, 32767], samples)
    with pytest.raises(ValueError, match="overflows Int16"):
        _validate_storage_value(TypedValues, "samples", [32768], samples)

    _validate_storage_value(TypedValues, "point", (1.0, 2.0), point)
    with pytest.raises(ValueError, match="finite Float32"):
        _validate_storage_value(TypedValues, "point", (1.0, float("inf")), point)
