"""Regression coverage for the ECS world facade's internal ownership boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from gummysnake.ecs.runtime_view_model import (
    Entity,
)
from gummysnake.ecs.world_facade import EcsWorld, initialization
from gummysnake.ecs.world_facade import EcsWorld as FacadeEcsWorld


class _FakeRustWorld:
    def __init__(self) -> None:
        self.registered_schemas: list[tuple[str, list[tuple[str, str]]]] = []

    def register_schema(self, name: str, fields: list[tuple[str, str]]) -> None:
        self.registered_schemas.append((name, fields))

    def schema_count(self) -> int:
        return len(self.registered_schemas)

    def alive_count(self) -> int:
        return 0

    def compiled_plan_count(self) -> int:
        return 0

    def spatial_index_cache_len(self) -> int:
        return 0

    def structural_revision(self) -> int:
        return 0

    def field_revision(self) -> int:
        return 0

    def diagnostics(self) -> dict[str, int | list[str]]:
        return {
            "entities_alive": 0,
            "component_schemas_total": len(self.registered_schemas),
            "event_records_read": 0,
            "messages": [],
        }


@dataclass
class _Position:
    x: float
    y: float


def test_world_facade_uses_canonical_runtime_view_objects() -> None:
    """The world facade exposes the canonical runtime-view objects."""

    assert EcsWorld is FacadeEcsWorld
    assert Entity.__module__ == "gummysnake.ecs.runtime_view_model.entity_mutation"


def test_world_initialization_validates_rust_bridge_before_schema_registration(monkeypatch) -> None:
    """World construction obtains one bridge before facade schema metadata is registered."""

    bridge = _FakeRustWorld()
    monkeypatch.setattr(initialization, "create_ecs_world", lambda: bridge)

    world = EcsWorld()
    schema = world.validate_schema(_Position)

    assert world._rust is bridge
    assert schema == world._schemas[_Position]
    assert bridge.registered_schemas == [
        (f"{_Position.__module__}.{_Position.__qualname__}", [("x", "Float64"), ("y", "Float64")])
    ]
    assert world.diagnostics()["ecs_rust_component_schemas_total"] == 1
