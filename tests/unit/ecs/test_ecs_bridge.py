from __future__ import annotations

from tests.helpers.ecs_fixtures import (
    BRIDGE_PLAN_VERSION,
    HERO,
    BackendCapabilityError,
    SimpleNamespace,
    pytest,
    rust_ecs,
)


def test_rust_ecs_bridge_compiles_plan_payload() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64"), ("y", "Float64")])
    world.register_schema("Clock", [("dt", "Float64")])
    payload = {
        "version": BRIDGE_PLAN_VERSION,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [("with_component", "Position"), ("with_tag", HERO)],
            }
        ],
        "expressions": [
            {"kind": "field", "query": "entity", "component": "Position", "field": "x"},
            {"kind": "resource_field", "resource": "Clock", "field": "dt"},
            {"kind": "binary", "op": "+", "left": 0, "right": 1},
        ],
        "actions": [{"kind": "set_field", "target": 0, "value": 2}],
        "root_action": 0,
    }

    summary = world.compile_bridge_plan(payload)

    assert isinstance(summary["handle"], int)
    assert summary["handle"] > 0
    assert world.compiled_plan_count() == 1
    assert summary["query_count"] == 1
    assert summary["expression_count"] == 3
    assert summary["action_count"] == 1
    assert summary["access"]["reads"] == ["component:Position", "resource:Clock"]
    assert summary["access"]["writes"] == ["component:Position"]


def test_rust_ecs_bridge_executes_plan_payload() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64"), ("y", "Float64")])
    world.register_schema("Velocity", [("dx", "Float64"), ("dy", "Float64")])
    index, generation = world.allocate_entity()
    world.add_component_default(index, generation, "Position")
    world.add_component_default(index, generation, "Velocity")
    world.set_field(index, generation, "Position", "x", 2.0)
    world.set_field(index, generation, "Velocity", "dx", 3.0)
    payload = {
        "version": BRIDGE_PLAN_VERSION,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [
                    ("with_component", "Position"),
                    ("with_component", "Velocity"),
                ],
            }
        ],
        "expressions": [
            {"kind": "field", "query": "entity", "component": "Position", "field": "x"},
            {"kind": "field", "query": "entity", "component": "Velocity", "field": "dx"},
            {"kind": "binary", "op": "add", "left": 0, "right": 1},
        ],
        "actions": [{"kind": "set_field", "target": 0, "value": 2}],
        "root_action": 0,
    }

    summary = world.compile_bridge_plan(payload)
    report = world.execute_compiled_plan(summary["handle"])

    assert world.get_field(index, generation, "Position", "x") == 5.0
    assert report["fields_written"] == 1
    assert report["component_writes"] == [
        {
            "index": index,
            "generation": generation,
            "component": "Position",
            "field": "x",
            "value": 5.0,
        }
    ]


def test_rust_ecs_wrapper_validates_abi_and_spatial_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWorld:
        pass

    class FakeRegistry:
        pass

    runtime = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        ecs_health_check=lambda: "ok",
        EcsWorld=FakeWorld,
        EcsSpatialIndexRegistry=FakeRegistry,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", runtime)
    assert isinstance(rust_ecs.create_ecs_world(), FakeWorld)
    assert isinstance(rust_ecs.create_spatial_index_registry(), FakeRegistry)

    bad_runtime = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION + 1,
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", bad_runtime)
    with pytest.raises(BackendCapabilityError, match="ABI"):
        rust_ecs.require_ecs_runtime()

    missing_spatial = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        ecs_health_check=lambda: "ok",
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", missing_spatial)
    with pytest.raises(BackendCapabilityError, match="EcsSpatialIndexRegistry"):
        rust_ecs.create_spatial_index_registry()


@pytest.mark.parametrize("marker", ["4", 4.0, True])
def test_rust_ecs_wrapper_rejects_malformed_abi_and_health_before_construction(
    monkeypatch: pytest.MonkeyPatch, marker: object
) -> None:
    constructed: list[str] = []

    class FakeWorld:
        def __init__(self) -> None:
            constructed.append("world")

    runtime = SimpleNamespace(
        ecs_abi_version=lambda: marker,
        ecs_health_check=lambda: "ok",
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", runtime)

    with pytest.raises(BackendCapabilityError, match="ABI") as error:
        rust_ecs.create_ecs_world()

    assert constructed == []
    assert "maturin develop --release" in str(error.value)


@pytest.mark.parametrize("health", [None, "", "unavailable", 1])
def test_rust_ecs_wrapper_rejects_malformed_health_before_construction(
    monkeypatch: pytest.MonkeyPatch, health: object
) -> None:
    constructed: list[str] = []

    class FakeWorld:
        def __init__(self) -> None:
            constructed.append("world")

    runtime = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        ecs_health_check=lambda: health,
        EcsWorld=FakeWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", runtime)

    with pytest.raises(BackendCapabilityError, match="unhealthy runtime state"):
        rust_ecs.create_ecs_world()

    assert constructed == []
