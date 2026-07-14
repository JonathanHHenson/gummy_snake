from __future__ import annotations

from gummysnake.ecs.specs import ChangeTerm
from tests.helpers.ecs_fixtures import (
    BRIDGE_PLAN_VERSION,
    HERO,
    BackendCapabilityError,
    EcsWorld,
    Position,
    SimpleNamespace,
    SystemPlanError,
    Velocity,
    ecs,
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


def test_rust_ecs_bridge_rejects_removed_python_entity_filter() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64")])
    payload = {
        "version": BRIDGE_PLAN_VERSION,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [("with_component", "Position")],
                "allowed_entities": [],
            }
        ],
        "expressions": [],
        "actions": [{"kind": "noop"}],
        "root_action": 0,
    }

    with pytest.raises(ValueError, match="allowed_entities.*removed"):
        world.compile_bridge_plan(payload)


def test_python_change_terms_compile_as_stable_rust_query_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    world = EcsWorld()
    world.add_entity(Position(0, 0), Velocity(0, 0))
    assert not hasattr(world, "_added_components")
    assert not hasattr(world, "_changed_components")
    assert not hasattr(world, "_removed_components")

    @ecs.system_plan
    def update(
        entity: ecs.Query[
            Position, ecs.Added[Position], ecs.Changed[Position], ecs.Removed[Velocity]
        ],
    ) -> None:
        entity[Position].x.increase_by(1)

    def fail_if_materialized(_: object) -> None:
        pytest.fail("change query terms must be evaluated by the Rust journal")

    monkeypatch.setattr(world, "match_query", fail_if_materialized)
    world.add_system(update)

    payload = world._systems[0].physical_payload
    assert payload is not None
    assert payload["dynamic"] is False
    position_schema = f"{Position.__module__}.{Position.__qualname__}"
    velocity_schema = f"{Velocity.__module__}.{Velocity.__qualname__}"
    assert payload["queries"] == [
        {
            "name": "entity",
            "terms": [
                ("with_component", position_schema),
                ("added", position_schema),
                ("changed", position_schema),
                ("removed", velocity_schema),
            ],
        }
    ]

    @ecs.system_plan
    def unsupported(entity: ecs.Query[Position, ChangeTerm("unknown", Position)]) -> None:
        entity[Position].x.increase_by(1)

    with pytest.raises(SystemPlanError, match="cannot be expressed by the Rust bridge"):
        world.add_system(unsupported)


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


def test_rust_ecs_bridge_executes_removed_component_query_term() -> None:
    world = rust_ecs.create_ecs_world()
    world.register_schema("Position", [("x", "Float64"), ("y", "Float64")])
    world.register_schema("Velocity", [("dx", "Float64"), ("dy", "Float64")])
    index, generation = world.allocate_entity()
    world.add_component_default(index, generation, "Position")
    world.add_component_default(index, generation, "Velocity")
    world.remove_component(index, generation, "Velocity")
    payload = {
        "version": BRIDGE_PLAN_VERSION,
        "schema_fingerprint": world.schema_fingerprint(),
        "queries": [
            {
                "name": "entity",
                "terms": [
                    ("with_component", "Position"),
                    ("removed", "Velocity"),
                ],
            }
        ],
        "expressions": [
            {"kind": "field", "query": "entity", "component": "Position", "field": "y"},
            {"kind": "literal_f64", "value": 9.0},
        ],
        "actions": [{"kind": "set_field", "target": 0, "value": 1}],
        "root_action": 0,
    }

    summary = world.compile_bridge_plan(payload)
    report = world.execute_compiled_plan(summary["handle"])

    assert world.get_field(index, generation, "Position", "y") == 9.0
    assert report["fields_written"] == 1


def test_rust_ecs_bridge_enforces_typed_storage_at_all_write_boundaries() -> None:
    import struct

    world = rust_ecs.create_ecs_world()
    world.register_schema(
        "Typed",
        [
            ("count", "UInt8"),
            ("ratio", "Float32"),
            ("kind", "CategoricalString"),
            ("samples", "List[Int16]"),
        ],
    )
    index, generation = world.spawn_with_defaults(["Typed"])

    world.set_field(index, generation, "Typed", "count", 255)
    with pytest.raises(ValueError, match="UInt8 range"):
        world.set_field(index, generation, "Typed", "count", 256)

    world.set_field(index, generation, "Typed", "ratio", 1.0 / 3.0)
    rounded = struct.unpack("!f", struct.pack("!f", 1.0 / 3.0))[0]
    assert world.get_field(index, generation, "Typed", "ratio") == rounded
    with pytest.raises(ValueError, match="finite"):
        world.set_field(index, generation, "Typed", "ratio", float("inf"))

    world.set_field(index, generation, "Typed", "kind", "enemy")
    world.set_field(index, generation, "Typed", "samples", [-32768, 32767])
    assert world.get_field(index, generation, "Typed", "kind") == "enemy"
    assert world.get_field(index, generation, "Typed", "samples") == [-32768, 32767]
    with pytest.raises(ValueError, match="Int16 range"):
        world.set_field(index, generation, "Typed", "samples", [32768])

    world.insert_resource(
        "Typed",
        {"count": 7, "ratio": 0.1, "kind": "resource", "samples": [1, 2]},
    )
    with pytest.raises(ValueError, match="UInt8 range"):
        world.set_resource_field("Typed", "count", -1)

    world.emit_event(
        "Typed",
        {"count": 9, "ratio": 0.2, "kind": "event", "samples": [3, 4]},
    )
    payload = world.read_events("Typed")[0]["payload"]
    assert payload["count"] == 9
    assert payload["ratio"] == struct.unpack("!f", struct.pack("!f", 0.2))[0]
    with pytest.raises(ValueError, match="UInt8 range"):
        world.emit_event(
            "Typed",
            {"count": 300, "ratio": 0.2, "kind": "event", "samples": []},
        )


def test_rust_ecs_wrapper_validates_abi_and_spatial_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWorld:
        def query_with_terms(self, terms: list[tuple[str, str]]) -> list[tuple[int, int]]:
            return []

    for method_name in rust_ecs._REQUIRED_ECS_WORLD_METHODS:
        if not hasattr(FakeWorld, method_name):
            setattr(FakeWorld, method_name, lambda self, *args, **kwargs: 0)

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

    class MissingMethodWorld:
        pass

    missing_required_method = SimpleNamespace(
        ecs_abi_version=lambda: rust_ecs.EXPECTED_ECS_ABI_VERSION,
        ecs_health_check=lambda: "ok",
        EcsWorld=MissingMethodWorld,
    )
    monkeypatch.setattr(rust_ecs, "_canvas", missing_required_method)
    with pytest.raises(BackendCapabilityError, match="query_with_terms"):
        rust_ecs.create_ecs_world()

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
