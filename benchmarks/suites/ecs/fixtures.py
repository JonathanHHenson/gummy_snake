"""Deterministic in-memory fixtures for the replacement ECS benchmark suite."""

from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass, make_dataclass
from functools import cache
from hashlib import sha256
from typing import Annotated, Any

from gummysnake.ecs import types as ecs_t

ACTIVE = "active"
SELECTED = "selected"


@dataclass(frozen=True, slots=True)
class Position2:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Position3:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class Velocity2:
    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class Health:
    value: int


@dataclass(frozen=True, slots=True)
class Bounds2:
    width: Annotated[int, ecs_t.UInt16]
    height: Annotated[int, ecs_t.UInt16]


@dataclass(frozen=True, slots=True)
class StorageRecord:
    enabled: bool
    signed: int
    ratio: float
    category: str
    small: Annotated[int, ecs_t.UInt16]
    vector: Annotated[tuple[float, float], ecs_t.Vec2F32]
    samples: Annotated[list[float], ecs_t.List(ecs_t.Float32)]


@dataclass(frozen=True, slots=True)
class AllStorageRecord:
    flag: Annotated[bool, ecs_t.Bool]
    i8: Annotated[int, ecs_t.Int8]
    u8: Annotated[int, ecs_t.UInt8]
    i16: Annotated[int, ecs_t.Int16]
    u16: Annotated[int, ecs_t.UInt16]
    i32: Annotated[int, ecs_t.Int32]
    u32: Annotated[int, ecs_t.UInt32]
    i64: Annotated[int, ecs_t.Int64]
    u64: Annotated[int, ecs_t.UInt64]
    f32: Annotated[float, ecs_t.Float32]
    f64: Annotated[float, ecs_t.Float64]
    text: Annotated[str, ecs_t.String]
    category: Annotated[str, ecs_t.CategoricalString]
    v2f32: Annotated[tuple[float, float], ecs_t.Vec2F32]
    v2f64: Annotated[tuple[float, float], ecs_t.Vec2F64]
    v3f32: Annotated[tuple[float, float, float], ecs_t.Vec3F32]
    v3f64: Annotated[tuple[float, float, float], ecs_t.Vec3F64]
    samples: Annotated[list[int], ecs_t.List(ecs_t.Int16)]


@dataclass(frozen=True, slots=True)
class Counter:
    total: int


@dataclass(frozen=True, slots=True)
class Pulse:
    amount: int
    sequence: int
    frame: int


@dataclass(frozen=True, slots=True)
class FixtureRow:
    index: int
    position2: Position2
    position3: Position3
    velocity: Velocity2
    health: Health
    bounds: Bounds2
    storage: StorageRecord
    tags: tuple[str, ...]


def generated_rows(count: int) -> tuple[FixtureRow, ...]:
    """Generate stable mixed-schema rows without random, network, or file inputs."""

    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("fixture row count must be a positive integer")
    rows: list[FixtureRow] = []
    for index in range(count):
        x = float((index * 17) % 61)
        y = float((index * 29) % 59)
        z = float((index * 37) % 53)
        rows.append(
            FixtureRow(
                index=index,
                position2=Position2(x, y),
                position3=Position3(x, y, z),
                velocity=Velocity2(float(index % 5) * 0.25 + 0.25, float(index % 7) * -0.125),
                health=Health(100 + index % 31),
                bounds=Bounds2(2 + index % 7, 3 + index % 5),
                storage=StorageRecord(
                    enabled=index % 2 == 0,
                    signed=index * 3 - 97,
                    ratio=float(index % 19) / 7.0,
                    category=("alpha", "beta", "gamma")[index % 3],
                    small=(index * 13) % 65_536,
                    vector=(x / 8.0, y / 8.0),
                    samples=[float((index + offset) % 11) for offset in range(index % 5)],
                ),
                tags=(ACTIVE,) if index % 3 == 0 else (),
            )
        )
    return tuple(rows)


def spatial_points(count: int, dimensions: int, distribution: str) -> tuple[tuple[float, ...], ...]:
    """Generate exact bounded point distributions for generic spatial workloads."""

    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("spatial point count must be a positive integer")
    if dimensions not in {2, 3}:
        raise ValueError("spatial dimensions must be 2 or 3")
    if distribution not in {"uniform", "clustered", "diagonal", "same-cell"}:
        raise ValueError("unknown spatial distribution")
    points: list[tuple[float, ...]] = []
    for index in range(count):
        if distribution == "uniform":
            coordinates = (
                float((index * 17) % 61) + 0.25,
                float((index * 29) % 59) + 0.25,
                float((index * 37) % 53) + 0.25,
            )
        elif distribution == "clustered":
            cluster = index % 4
            coordinates = (
                8.0 + cluster * 12.0 + float(index % 5) * 0.2,
                7.0 + cluster * 11.0 + float((index // 5) % 5) * 0.2,
                6.0 + cluster * 10.0 + float((index // 25) % 5) * 0.2,
            )
        elif distribution == "diagonal":
            coordinate = 1.0 + float(index % 60)
            coordinates = (coordinate, coordinate, coordinate)
        else:
            coordinates = (
                4.0 + float(index % 4) * 0.05,
                4.0 + float((index // 4) % 4) * 0.05,
                4.0 + float((index // 16) % 4) * 0.05,
            )
        points.append(coordinates[:dimensions])
    return tuple(points)


def fixture_digest(count: int) -> str:
    """Hash generated fixture values in canonical row order."""

    payload = [asdict(row) for row in generated_rows(count)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def float32(value: float) -> float:
    """Return the deterministic IEEE-754 binary32 round-trip used by Rust storage."""

    return struct.unpack("<f", struct.pack("<f", value))[0]


def all_storage_record(index: int, list_length: int) -> AllStorageRecord:
    """Build one exact value spanning every scalar/vector/category storage marker."""

    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("storage record index must be a non-negative integer")
    if isinstance(list_length, bool) or not isinstance(list_length, int) or list_length < 0:
        raise ValueError("storage list length must be a non-negative integer")
    ratio = float(index + 1) / 7.0
    return AllStorageRecord(
        flag=index % 2 == 0,
        i8=-128 + index % 256,
        u8=index % 256,
        i16=-32_768 + index % 65_536,
        u16=index % 65_536,
        i32=-(2**31) + index,
        u32=index,
        i64=-(2**63) + index,
        u64=index,
        f32=ratio,
        f64=ratio + 0.125,
        text=f"text-{index % 11}",
        category=("alpha", "beta", "gamma")[index % 3],
        v2f32=(ratio, -ratio),
        v2f64=(ratio + 1.0, ratio + 2.0),
        v3f32=(ratio, ratio + 1.0, ratio + 2.0),
        v3f64=(ratio + 3.0, ratio + 4.0, ratio + 5.0),
        samples=[-16_384 + (index + offset) % 32_768 for offset in range(list_length)],
    )


def expected_all_storage_record(index: int, list_length: int) -> AllStorageRecord:
    """Return the exact public readback expected after Float32 conversion."""

    record = all_storage_record(index, list_length)
    return AllStorageRecord(
        record.flag,
        record.i8,
        record.u8,
        record.i16,
        record.u16,
        record.i32,
        record.u32,
        record.i64,
        record.u64,
        float32(record.f32),
        record.f64,
        record.text,
        record.category,
        (float32(record.v2f32[0]), float32(record.v2f32[1])),
        record.v2f64,
        (
            float32(record.v3f32[0]),
            float32(record.v3f32[1]),
            float32(record.v3f32[2]),
        ),
        record.v3f64,
        list(record.samples),
    )


@cache
def schema_fixture_types(schema_count: int, field_count: int) -> tuple[type[Any], ...]:
    """Create stable dataclass schema identities for one exact registration case."""

    if schema_count not in {1, 16, 64, 256}:
        raise ValueError("schema_count must be one of 1, 16, 64, or 256")
    if field_count not in {1, 4, 16}:
        raise ValueError("field_count must be one of 1, 4, or 16")
    return tuple(
        make_dataclass(
            f"Schema{schema_count}x{field_count}_{schema_index:03d}",
            [(f"field_{field_index:02d}", float) for field_index in range(field_count)],
            frozen=True,
            slots=True,
            namespace={"__module__": __name__},
        )
        for schema_index in range(schema_count)
    )


@cache
def spawn_component_types(component_count: int, field_count: int) -> tuple[type[Any], ...]:
    """Create deterministic component classes for public spawn-shape cases."""

    if component_count not in {1, 4, 8}:
        raise ValueError("component_count must be one of 1, 4, or 8")
    if field_count not in {1, 4, 16}:
        raise ValueError("field_count must be one of 1, 4, or 16")
    return tuple(
        make_dataclass(
            f"Spawn{component_count}x{field_count}_{component_index}",
            [(f"field_{field_index:02d}", float) for field_index in range(field_count)],
            frozen=True,
            slots=True,
            namespace={"__module__": __name__},
        )
        for component_index in range(component_count)
    )


def spawn_component_value(
    component_type: type[Any], entity_index: int, component_index: int, field_count: int
) -> object:
    """Instantiate one spawn component with values that encode row/component/field."""

    values = tuple(
        float(entity_index * 10_000 + component_index * 100 + field_index)
        for field_index in range(field_count)
    )
    return component_type(*values)


_TRANSPORT_STORAGE = {
    "scalar": (int, ecs_t.Int64),
    "vector": (tuple[float, float], ecs_t.Vec2F32),
    "list": (list[int], ecs_t.List(ecs_t.Int16)),
    "categorical": (str, ecs_t.CategoricalString),
}


@cache
def transport_component_type(storage_family: str, field_count: int) -> type[Any]:
    """Create one exact-width component for Python transport matrix cases."""

    if storage_family not in _TRANSPORT_STORAGE:
        raise ValueError("unknown transport storage family")
    if field_count not in {1, 2, 8, 16}:
        raise ValueError("field_count must be one of 1, 2, 8, or 16")
    python_type, marker = _TRANSPORT_STORAGE[storage_family]
    annotation = Annotated[python_type, marker]
    return make_dataclass(
        f"Transport{storage_family.title()}{field_count}",
        [(f"field_{index:02d}", annotation) for index in range(field_count)],
        frozen=True,
        slots=True,
        namespace={"__module__": __name__},
    )


def transport_value(storage_family: str, row: int, field: int, *, updated: bool = False) -> object:
    """Return one exact transport value for a storage family and field position."""

    offset = 10_000 if updated else 0
    identity = row * 31 + field + offset
    if storage_family == "scalar":
        return identity - 20_000
    if storage_family == "vector":
        return (float32(identity / 16.0), float32(-identity / 32.0))
    if storage_family == "list":
        return [((identity + item) % 32_768) - 16_384 for item in range(field % 4)]
    if storage_family == "categorical":
        return ("alpha", "beta", "gamma", "delta")[identity % 4]
    raise ValueError("unknown transport storage family")


FIXTURE_MANIFEST = {count: fixture_digest(count) for count in (3, 32, 48, 64, 96, 128, 192, 256)}
