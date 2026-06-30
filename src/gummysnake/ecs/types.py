"""ECS Rust storage type markers for ``typing.Annotated`` metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageType:
    """Description of an ECS storage type marker."""

    name: str
    python_type: type[object]
    min_value: int | None = None
    max_value: int | None = None
    element_type: StorageType | None = None
    fixed_length: int | None = None

    def __repr__(self) -> str:
        return self.name


Bool = StorageType("Bool", bool)
Int8 = StorageType("Int8", int, -(2**7), 2**7 - 1)
UInt8 = StorageType("UInt8", int, 0, 2**8 - 1)
Int16 = StorageType("Int16", int, -(2**15), 2**15 - 1)
UInt16 = StorageType("UInt16", int, 0, 2**16 - 1)
Int32 = StorageType("Int32", int, -(2**31), 2**31 - 1)
UInt32 = StorageType("UInt32", int, 0, 2**32 - 1)
Int64 = StorageType("Int64", int, -(2**63), 2**63 - 1)
UInt64 = StorageType("UInt64", int, 0, 2**64 - 1)
Float32 = StorageType("Float32", float)
Float64 = StorageType("Float64", float)
String = StorageType("String", str)
CategoricalString = StorageType("CategoricalString", str)
Vec2F32 = StorageType("Vec2F32", tuple, element_type=Float32, fixed_length=2)
Vec2F64 = StorageType("Vec2F64", tuple, element_type=Float64, fixed_length=2)
Vec3F32 = StorageType("Vec3F32", tuple, element_type=Float32, fixed_length=3)
Vec3F64 = StorageType("Vec3F64", tuple, element_type=Float64, fixed_length=3)


def List(element_type: StorageType = Float64) -> StorageType:
    """Create a Rust-owned list column storage marker for ``typing.Annotated``.

    The Python MVP stores these as list-like dataclass values while preserving the
    explicit storage marker for the Rust-backed column implementation.
    """

    if not isinstance(element_type, StorageType):
        raise TypeError("ecs.types.List() expects an ecs storage type marker.")
    return StorageType(f"List[{element_type.name}]", list, element_type=element_type)


__all__ = [
    "StorageType",
    "Bool",
    "Int8",
    "UInt8",
    "Int16",
    "UInt16",
    "Int32",
    "UInt32",
    "Int64",
    "UInt64",
    "Float32",
    "Float64",
    "String",
    "CategoricalString",
    "Vec2F32",
    "Vec2F64",
    "Vec3F32",
    "Vec3F64",
    "List",
]
