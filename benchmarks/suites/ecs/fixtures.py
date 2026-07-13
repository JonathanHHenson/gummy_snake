"""Deterministic in-memory fixtures for the replacement ECS benchmark suite."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Annotated

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
class Counter:
    total: int


@dataclass(frozen=True, slots=True)
class Pulse:
    amount: int
    sequence: int


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


def fixture_digest(count: int) -> str:
    """Hash generated fixture values in canonical row order."""

    payload = [asdict(row) for row in generated_rows(count)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


FIXTURE_MANIFEST = {count: fixture_digest(count) for count in (3, 32, 48, 64, 96, 128, 192, 256)}
