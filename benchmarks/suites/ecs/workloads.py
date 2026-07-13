"""Static bounded production-path workloads for the replacement ECS suite."""

# ECS query/resource annotations are runtime subscription specifications rather than
# static generic classes; mypy cannot model that public declaration syntax.
# mypy: disable-error-code=type-arg
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from benchmarks.governance import ExecutionClass
from benchmarks.suites.registry import SuiteExecution
from gummysnake import Sketch, ecs
from gummysnake.ecs import canvas as ca
from gummysnake.ecs.world import EcsWorld
from gummysnake.exceptions import EntityNotFoundError, StaleEntityError, SystemPlanError

from .fixtures import (
    ACTIVE,
    SELECTED,
    Bounds2,
    Counter,
    Health,
    Position2,
    Position3,
    Pulse,
    StorageRecord,
    Velocity2,
    fixture_digest,
    generated_rows,
)
from .oracles import (
    EcsOracleError,
    assert_equal,
    correctness_digest,
    entity_rows,
    require_counter_minimums,
    require_counters,
)


class EcsWorkloadError(ValueError):
    """A static ECS workload declaration is unknown, unsafe, or internally inconsistent."""


class ExecutionRouteError(EcsWorkloadError):
    """A workload requested an undeclared execution class or substituted route."""


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXECUTION_LAYERS = frozenset({"R", "P", "H", "I"})
_IMPLEMENTED_LAYER_ROUTES: Mapping[str, ExecutionClass] = {"H": ExecutionClass.HEADLESS}


@dataclass(frozen=True, slots=True)
class WorkloadPlan:
    workload_id: str
    case_kind: str
    execution_class: ExecutionClass
    execution_layer: str
    expected_correctness_digest: str
    work_units: int
    required_counters: tuple[str, ...]
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Outcome:
    diagnostics: Mapping[str, object]
    summary: Mapping[str, object]
    actual_work_units: int
    extra_diagnostics: Mapping[str, object] | None = None


_CASES: Mapping[str, frozenset[str]] = {
    "storage-entity-archetype": frozenset(
        {"schema-storage", "spawn-archetypes", "structural-churn"}
    ),
    "query-view-transport": frozenset({"query-order", "batch-transport", "cardinality"}),
    "plan-compile-cache": frozenset({"plan-build-compile", "plan-cache-release"}),
    "scheduler-executor": frozenset({"group-order", "parallel-snapshot", "simulated-multisystem"}),
    "mutation-boundaries": frozenset(
        {"change-structural", "resources-events", "python-system-udf", "udf-plan"}
    ),
    "spatial-algorithms": frozenset(
        {"spatial-hash-grid", "spatial-quadtree", "spatial-octree", "spatial-hilbert"}
    ),
    "integrated-headless-frame": frozenset({"compact-fill", "simulation-render"}),
    "diagnostics-failures-longevity": frozenset(
        {"diagnostics-reset", "failure-contracts", "bounded-longevity"}
    ),
}

_COMMON_PARAMETERS = frozenset(
    {
        "case_kind",
        "execution_layer",
        "execution_layer_capabilities",
        "expected_correctness_digest",
        "work_units",
        "required_counters",
    }
)
_CASE_PARAMETERS: Mapping[str, frozenset[str]] = {
    "schema-storage": frozenset({"passes"}),
    "spawn-archetypes": frozenset({"entity_count"}),
    "structural-churn": frozenset({"entity_count", "iterations", "churn_count"}),
    "query-order": frozenset({"entity_count"}),
    "batch-transport": frozenset({"entity_count"}),
    "cardinality": frozenset(),
    "plan-build-compile": frozenset({"system_count"}),
    "plan-cache-release": frozenset({"frames", "cycles"}),
    "group-order": frozenset({"frames"}),
    "parallel-snapshot": frozenset({"entity_count"}),
    "simulated-multisystem": frozenset({"entity_count", "frames", "system_count"}),
    "change-structural": frozenset({"entity_count"}),
    "resources-events": frozenset({"event_count"}),
    "python-system-udf": frozenset({"entity_count"}),
    "udf-plan": frozenset({"entity_count"}),
    "spatial-hash-grid": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-quadtree": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-octree": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-hilbert": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "compact-fill": frozenset({"entity_count", "frames", "width", "height"}),
    "simulation-render": frozenset({"entity_count", "frames", "width", "height"}),
    "diagnostics-reset": frozenset({"entity_count"}),
    "failure-contracts": frozenset(),
    "bounded-longevity": frozenset({"entity_count", "frames", "churn_count"}),
}


def _positive_int(parameters: Mapping[str, object], name: str, maximum: int = 100_000) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise EcsWorkloadError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _positive_float(parameters: Mapping[str, object], name: str) -> float:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise EcsWorkloadError(f"{name} must be a positive finite number")
    try:
        result = float(value)
    except ValueError as error:
        raise EcsWorkloadError(f"{name} must be a positive finite number") from error
    if not 0.0 < result < 1_000_000.0:
        raise EcsWorkloadError(f"{name} must be in (0, 1000000)")
    return result


def _required_counters(parameters: Mapping[str, object]) -> tuple[str, ...]:
    raw = parameters.get("required_counters")
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(item, str) and item for item in raw)
    ):
        raise EcsWorkloadError("required_counters must be a non-empty list of names")
    if len(set(raw)) != len(raw):
        raise EcsWorkloadError("required_counters must not contain duplicates")
    return tuple(raw)


def _execution_layer_capabilities(
    parameters: Mapping[str, object],
) -> Mapping[str, tuple[bool, str]]:
    """Validate the exact R/P/H/I declaration without inferring unsupported routes."""

    raw = parameters["execution_layer_capabilities"]
    if not isinstance(raw, Mapping) or set(raw) != _EXECUTION_LAYERS:
        raise EcsWorkloadError("execution_layer_capabilities must declare exactly R, P, H, and I")
    statuses: dict[str, tuple[bool, str]] = {}
    for layer in sorted(_EXECUTION_LAYERS):
        declaration = raw[layer]
        if not isinstance(declaration, Mapping) or set(declaration) != {"available", "detail"}:
            raise EcsWorkloadError(
                f"execution_layer_capabilities.{layer} must contain only available and detail"
            )
        available = declaration["available"]
        detail = declaration["detail"]
        if not isinstance(available, bool) or not isinstance(detail, str) or not detail.strip():
            raise EcsWorkloadError(
                f"execution_layer_capabilities.{layer} requires a boolean available and detail"
            )
        statuses[layer] = (available, detail.strip())
    return statuses


def build_workload(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass | str,
) -> WorkloadPlan:
    """Validate an exact static ECS case without constructing native runtime state."""

    cases = _CASES.get(workload_id)
    if cases is None:
        raise EcsWorkloadError(f"unknown ECS workload id: {workload_id!r}")
    case_kind = parameters.get("case_kind")
    if not isinstance(case_kind, str) or case_kind not in cases:
        raise EcsWorkloadError(
            f"case_kind for {workload_id!r} must be one of {sorted(cases)}, got {case_kind!r}"
        )
    allowed = _COMMON_PARAMETERS | _CASE_PARAMETERS[case_kind]
    unexpected = sorted(set(parameters) - allowed)
    missing = sorted(allowed - set(parameters))
    if unexpected:
        raise EcsWorkloadError(f"unexecuted or unsupported parameter(s): {', '.join(unexpected)}")
    if missing:
        raise EcsWorkloadError(f"missing required parameter(s): {', '.join(missing)}")
    try:
        route = ExecutionClass(execution_class)
    except ValueError as error:
        raise ExecutionRouteError(f"unknown ECS execution class: {execution_class!r}") from error
    layer_capabilities = _execution_layer_capabilities(parameters)
    execution_layer = parameters["execution_layer"]
    if not isinstance(execution_layer, str) or execution_layer not in _EXECUTION_LAYERS:
        raise ExecutionRouteError(
            f"ECS case {case_kind!r} has an unknown execution_layer={execution_layer!r}; "
            "declare one of R, P, H, or I"
        )
    layer_available, layer_detail = layer_capabilities[execution_layer]
    if not layer_available:
        raise ExecutionRouteError(
            f"ECS execution_layer={execution_layer!r} is declared unavailable: {layer_detail} "
            "No fallback route is available; implement and qualify that layer before enabling it."
        )
    expected_route = _IMPLEMENTED_LAYER_ROUTES.get(execution_layer)
    if expected_route is None:
        raise ExecutionRouteError(
            f"ECS execution_layer={execution_layer!r} is declared available but has no "
            "implemented route. Add and qualify its route before enabling it; no fallback is used."
        )
    if route is not expected_route:
        raise ExecutionRouteError(
            f"ECS case {case_kind!r} requires execution_class={expected_route.value!r} "
            f"for execution_layer={execution_layer!r}; got {route.value!r}"
        )
    expected_digest = parameters["expected_correctness_digest"]
    if not isinstance(expected_digest, str) or not _DIGEST.fullmatch(expected_digest):
        raise EcsWorkloadError("expected_correctness_digest must be a lowercase SHA-256 digest")
    return WorkloadPlan(
        workload_id=workload_id,
        case_kind=case_kind,
        execution_class=route,
        execution_layer=execution_layer,
        expected_correctness_digest=expected_digest,
        work_units=_positive_int(parameters, "work_units", 100_000_000),
        required_counters=_required_counters(parameters),
        parameters=dict(parameters),
    )


def _spawn_world(entity_count: int, *, full: bool = False, three_d: bool = False) -> EcsWorld:
    world = EcsWorld()
    for row in generated_rows(entity_count):
        position: object = row.position3 if three_d else row.position2
        components: list[object] = [position]
        if full or row.index % 2 == 0:
            components.append(row.velocity)
        if full or row.index % 4 == 0:
            components.append(row.health)
        if full or row.index % 8 == 0:
            components.extend((row.bounds, row.storage))
        world.add_entity(*cast(list[Any], components), tags=row.tags)
    return world


def _outcome(world: EcsWorld, state: object, actual_work_units: int) -> _Outcome:
    diagnostics = world.diagnostics()
    return _Outcome(
        diagnostics,
        {
            "correctness_digest": correctness_digest(state),
            "entities_alive": int(diagnostics["ecs_entities_alive"]),
        },
        actual_work_units,
    )


def _schema_storage(plan: WorkloadPlan) -> _Outcome:
    passes = _positive_int(plan.parameters, "passes", 1_000)
    world = EcsWorld()
    schema_types = (Position2, Bounds2, StorageRecord, Pulse)
    snapshots: list[object] = []
    for _ in range(passes):
        snapshots.append(
            {
                component.__name__: {
                    name: storage.name for name, storage in world.validate_schema(component).items()
                }
                for component in schema_types
            }
        )
    assert_equal(snapshots[0], snapshots[-1], "idempotent schema mapping")
    require_counter_minimums(
        world.diagnostics(),
        {
            "ecs_component_schemas_total": len(schema_types),
            "ecs_rust_component_schemas_total": len(schema_types),
        },
    )
    return _outcome(
        world,
        {"fixture": fixture_digest(3), "schemas": snapshots[-1]},
        passes * len(schema_types),
    )


def _spawn_archetypes(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = _spawn_world(count)
    positions = entity_rows(world, Position2, "x", "y")
    expected = tuple((row.position2.x, row.position2.y) for row in generated_rows(count))
    assert_equal(positions, expected, "spawned position rows")
    tagged = tuple(view.entity.index for view in world.iter_entities(Position2, tags=[ACTIVE]))
    assert_equal(tagged, tuple(range(0, count, 3)), "tagged deterministic order")
    return _outcome(world, {"positions": positions, "active": tagged}, count)


def _structural_churn(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    iterations = _positive_int(plan.parameters, "iterations", 100)
    churn = _positive_int(plan.parameters, "churn_count", count)
    if churn > count:
        raise EcsWorkloadError("churn_count cannot exceed entity_count")
    world = EcsWorld()
    handles = [world.add_entity(row.position2) for row in generated_rows(count)]
    for cycle in range(iterations):
        for offset in range(churn):
            handle = handles[offset]
            world.add_component(handle, Health(cycle + offset))
            world.add_tag(handle, SELECTED)
            world.remove_component(handle, Health)
            world.remove_tag(handle, SELECTED)
            world.despawn_entity(handle)
            handles[offset] = world.add_entity(generated_rows(count)[offset].position2)
    rows = entity_rows(world, Position2, "x", "y")
    expected_rows = tuple((row.position2.x, row.position2.y) for row in generated_rows(count))
    assert_equal(sorted(rows), sorted(expected_rows), "churn row values")
    for handle, fixture in zip(handles, generated_rows(count), strict=True):
        assert_equal(
            world.component_snapshot(handle, Position2), fixture.position2, "churn handle location"
        )
    query_order = tuple(view.entity.index for view in world.iter_entities(Position2))
    assert_equal(
        query_order,
        tuple(view.entity.index for view in world.iter_entities(Position2)),
        "stable post-churn query order",
    )
    require_counter_minimums(
        world.diagnostics(),
        {
            "ecs_structural_commands_applied": iterations * churn * 4,
            "ecs_entity_generation_reuses": iterations * churn,
        },
    )
    return _outcome(
        world,
        {
            "rows": rows,
            "query_order": query_order,
            "handles": [(h.index, h.generation) for h in handles],
        },
        count * iterations,
    )


def _query_order(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = _spawn_world(count, full=True)
    indices = tuple(
        view.entity.index for view in world.iter_entities(Position2, Health, tags=[ACTIVE])
    )
    expected_indices = tuple(range(0, count, 3))
    assert_equal(indices, expected_indices, "query entity order")
    health_total = sum(
        view[Health].value for view in world.iter_entities(Position2, Health, tags=[ACTIVE])
    )
    expected_total = sum(100 + index % 31 for index in expected_indices)
    assert_equal(health_total, expected_total, "query view values")
    return _outcome(world, {"indices": indices, "health_total": health_total}, count)


def _batch_transport(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = _spawn_world(count, full=True)
    rows = entity_rows(world, StorageRecord, "signed", "ratio", "category", "small")
    fixtures = generated_rows(count)
    expected = tuple(
        (row.storage.signed, row.storage.ratio, row.storage.category, row.storage.small)
        for row in fixtures
    )
    assert_equal(rows, expected, "batched field transport")
    return _outcome(world, {"rows": rows, "fixture": fixture_digest(count)}, count)


def _cardinality(plan: WorkloadPlan) -> _Outcome:
    outcomes: list[str] = []
    for count in (0, 1, 2):
        world = EcsWorld()
        for row in generated_rows(max(1, count))[:count]:
            world.add_entity(row.position2)
        try:
            result = world.try_get_entity(Position2)
        except EntityNotFoundError:
            outcomes.append("many-error")
        else:
            outcomes.append("none" if result is None else f"one:{result.entity.index}")
    assert_equal(outcomes, ["none", "one:0", "many-error"], "cardinality outcomes")
    final_world = EcsWorld()
    return _outcome(final_world, outcomes, 3)


def _advance_definition() -> ecs.SystemPlanDefinition:
    @ecs.system_plan
    def advance(entity: ecs.Query[Position2, Velocity2]) -> None:
        entity[Position2].x.increase_by(entity[Velocity2].dx)
        entity[Position2].y.increase_by(entity[Velocity2].dy)

    return advance


def _plan_build_compile(plan: WorkloadPlan) -> _Outcome:
    system_count = _positive_int(plan.parameters, "system_count", 1_000)
    world = _spawn_world(8, full=True)
    definitions = [_advance_definition() for _ in range(system_count)]
    explanations = [definition.explain() for definition in definitions]
    for index, definition in enumerate(definitions):
        world.add_system(definition, name=f"advance_{index}", group="simulation")
    diagnostics = world.diagnostics()
    require_counter_minimums(
        diagnostics,
        {"ecs_physical_plan_compiles": system_count, "ecs_rust_compiled_plans": system_count},
    )
    return _outcome(world, explanations, system_count * 2)


def _plan_cache_release(plan: WorkloadPlan) -> _Outcome:
    frames = _positive_int(plan.parameters, "frames", 1_000)
    cycles = _positive_int(plan.parameters, "cycles", 1_000)
    world = _spawn_world(16, full=True)
    definition = _advance_definition()
    for cycle in range(cycles):
        handle = world.add_system(definition, name=f"cached_{cycle}")
        for _ in range(frames):
            world.run_pre_draw_systems()
        world.remove_system(handle)
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_rust_compiled_plans"], 0, "released compiled plans")
    require_counter_minimums(
        diagnostics,
        {"ecs_physical_plan_compiles": cycles, "ecs_physical_system_runs": cycles * frames},
    )
    return _outcome(world, diagnostics, cycles * frames)


def _group_order(plan: WorkloadPlan) -> _Outcome:
    frames = _positive_int(plan.parameters, "frames", 1_000)
    world = EcsWorld()
    world.add_entity(Position2(0.0, 0.0))

    @ecs.system_plan
    def input_system(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.increase_by(1.0)

    @ecs.system_plan
    def simulation_system(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.set_to(entity[Position2].x * 2.0)

    @ecs.system_plan
    def output_system(entity: ecs.Query[Position2]) -> None:
        entity[Position2].y.set_to(entity[Position2].x)

    world.order(["input", "simulation", "output"])
    world.add_system(output_system, group="output")
    world.add_system(simulation_system, group="simulation")
    world.add_system(input_system, group="input")
    expected = 0.0
    for _ in range(frames):
        world.run_pre_draw_systems()
        expected = (expected + 1.0) * 2.0
    row = entity_rows(world, Position2, "x", "y")[0]
    assert_equal(row, (expected, expected), "ordered schedule result")
    return _outcome(world, row, frames * 3)


def _parallel_snapshot(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = EcsWorld()
    for row in generated_rows(count):
        world.add_entity(row.position2)

    @ecs.system_plan(parallel=True)
    def snapshot(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.set_to(5.0)
        entity[Position2].y.set_to(entity[Position2].x)

    world.add_system(snapshot)
    world.run_pre_draw_systems()
    rows = entity_rows(world, Position2, "x", "y")
    expected = tuple((5.0, row.position2.x) for row in generated_rows(count))
    assert_equal(rows, expected, "parallel snapshot semantics")
    return _outcome(world, rows, count * 2)


def _simulated_multisystem(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    frames = _positive_int(plan.parameters, "frames", 10_000)
    systems = _positive_int(plan.parameters, "system_count", 128)
    world = EcsWorld()
    for row in generated_rows(count):
        world.add_entity(row.position2)

    @ecs.system_plan(parallel=True)
    def increment(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.increase_by(1.0)

    for index in range(systems):
        world.add_system(increment, name=f"increment_{index}", group="simulation")
    for _ in range(frames):
        world.run_pre_draw_systems()
    rows = entity_rows(world, Position2, "x")
    expected = tuple((row.position2.x + frames * systems,) for row in generated_rows(count))
    assert_equal(rows, expected, "simulated multi-system result")
    return _outcome(world, rows, count * frames * systems)


def _change_structural(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = EcsWorld()
    handles = []
    for row in generated_rows(count):
        handles.append(world.add_entity(row.position2, Health(0)))
    world.run_pre_draw_systems()
    selected = tuple(index for index in range(count) if index % 4 == 0)
    for index in selected:
        world.set_component(handles[index], Position2(float(index), 1.0))
        world.add_tag(handles[index], SELECTED)

    @ecs.system_plan
    def changed(entity: ecs.Query[Health, ecs.Changed[Position2]]) -> None:
        entity[Health].value.increase_by(1)

    @ecs.system_plan
    def structural(
        entity: ecs.Query[ecs.Tag[SELECTED], Health],  # type: ignore[valid-type]
    ) -> None:
        cast(Any, entity).entity.remove_component(Health)

    world.order(["change", "structural"])
    world.add_system(changed, group="change")
    world.add_system(structural, group="structural")
    world.run_pre_draw_systems()
    remaining = tuple(view.entity.index for view in world.iter_entities(Health))
    expected = tuple(index for index in range(count) if index not in selected)
    assert_equal(remaining, expected, "deferred structural visibility")
    return _outcome(world, {"selected": selected, "remaining": remaining}, count)


def _resources_events(plan: WorkloadPlan) -> _Outcome:
    event_count = _positive_int(plan.parameters, "event_count")
    world = EcsWorld()
    world.set_resource(Counter(0))
    for sequence in range(event_count):
        world.emit_event(Pulse(sequence % 5 + 1, sequence))

    @ecs.system_plan
    def consume(reader: ecs.EventReader[Pulse], counter: ecs.ResMut[Counter]) -> None:
        with ecs.for_each(reader) as event:
            counter[Counter].total.increase_by(event.amount)

    world.add_system(consume)
    world.run_pre_draw_systems()
    events = world.read_events(Pulse)
    expected_total = sum(sequence % 5 + 1 for sequence in range(event_count))
    assert_equal(world.get_resource(Counter).total, expected_total, "event reduction")
    assert_equal(
        tuple(event.sequence for event in events), tuple(range(event_count)), "event order"
    )
    world.clear_events(Pulse)
    assert_equal(world.read_events(Pulse), (), "event cleanup")
    return _outcome(
        world, {"total": expected_total, "sequences": tuple(range(event_count))}, event_count
    )


def _python_system_udf(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = EcsWorld()
    for row in generated_rows(count):
        world.add_entity(row.position2)

    @ecs.system(group="python_system")
    def python_update(entities: ecs.Query[Position2]) -> None:
        for entity in entities:
            entity[Position2].x += 3.0

    @ecs.udf(
        mutations={
            "entities": {ecs.EntityMutation[Position2](update=True)}  # type: ignore[misc]
        }
    )
    def udf_update(entities: Iterable[ecs.Entity[Position2]]) -> None:
        for entity in entities:
            cast(Any, entity)[Position2].x += 2.0

    @ecs.system_plan(group="python_udf")
    def invoke_udf(entities: ecs.Query[Position2]) -> None:
        udf_update(entities)

    world.order(["python_system", "python_udf"])
    world.add_system(python_update)
    world.add_system(invoke_udf)
    world.run_pre_draw_systems()
    rows = entity_rows(world, Position2, "x")
    expected = tuple((row.position2.x + 5.0,) for row in generated_rows(count))
    assert_equal(rows, expected, "explicit Python system and UDF mutation")
    require_counter_minimums(
        world.diagnostics(),
        {
            "ecs_python_system_calls": 1,
            "ecs_python_system_entities_materialized": count,
            "ecs_udf_calls": 1,
        },
    )
    return _outcome(world, rows, count * 2)


def _udf_plan(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = EcsWorld()
    for row in generated_rows(count):
        world.add_entity(row.position2)

    @ecs.udf_plan
    def offset(value: ecs.Expression[float]) -> ecs.Expression[float]:
        return value + 2.0

    @ecs.system_plan
    def apply(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.set_to(offset(entity[Position2].x))

    world.add_system(apply)
    world.run_pre_draw_systems()
    rows = entity_rows(world, Position2, "x")
    expected = tuple((row.position2.x + 2.0,) for row in generated_rows(count))
    assert_equal(rows, expected, "udf-plan expansion")
    assert_equal(world.diagnostics().get("ecs_udf_calls", 0), 0, "udf-plan runtime Python calls")
    return _outcome(world, rows, count)


def _spatial_algorithm(kind: str, update: str, dimensions: int) -> object:
    bounds2 = ecs.spatial.Bounds2D(0.0, 0.0, 64.0, 64.0)
    bounds3 = ecs.spatial.Bounds3D(0.0, 0.0, 0.0, 64.0, 64.0, 64.0)
    if kind == "spatial-hash-grid":
        return ecs.spatial.HashGrid(
            cell_size=8.0, dimensions=cast(Any, dimensions), update=cast(Any, update)
        )
    if kind == "spatial-quadtree":
        return ecs.spatial.Quadtree(bounds2, capacity=8, max_depth=8, update=cast(Any, update))
    if kind == "spatial-octree":
        return ecs.spatial.Octree(bounds3, capacity=8, max_depth=8, update=cast(Any, update))
    return ecs.spatial.HilbertCurve(
        bounds3 if dimensions == 3 else bounds2,
        bits=12,
        dimensions=cast(Any, dimensions),
        update=cast(Any, update),
    )


def _expected_neighbor_counts(
    points: tuple[tuple[float, ...], ...], radius: float
) -> tuple[int, ...]:
    radius_squared = radius * radius
    return tuple(
        sum(
            1
            for other_index, other in enumerate(points)
            if index != other_index
            and sum((left - right) ** 2 for left, right in zip(point, other, strict=True))
            <= radius_squared
        )
        for index, point in enumerate(points)
    )


def _spatial(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    frames = _positive_int(plan.parameters, "frames", 1_000)
    radius = _positive_float(plan.parameters, "radius")
    update = plan.parameters.get("update_policy")
    if update not in {"auto", "rebuild_each_use", "rebuild_each_frame", "incremental"}:
        raise EcsWorkloadError("update_policy is not a supported ECS spatial policy")
    dimensions = 3 if plan.case_kind == "spatial-octree" else 2
    algorithm = _spatial_algorithm(plan.case_kind, cast(str, update), dimensions)
    world = EcsWorld()
    for row in generated_rows(count):
        position = row.position3 if dimensions == 3 else row.position2
        world.add_entity(position, Health(0))

    if dimensions == 3:

        @ecs.system_plan
        def move(entity: ecs.Query[Position3]) -> None:
            entity[Position3].x.increase_by(0.25)

        @ecs.system_plan
        def neighbors(entity: ecs.Query[Position3, Health]) -> None:
            point = ecs.spatial.point3(
                entity[Position3].x, entity[Position3].y, entity[Position3].z
            )
            nearby = ecs.spatial.neighbors(
                entity,
                position=point,
                radius=radius,
                algorithm=cast(Any, algorithm),
                include_self=False,
                allow_fallback=False,
            )
            entity[Health].value.set_to(nearby.count())
    else:

        @ecs.system_plan
        def move(entity: ecs.Query[Position2]) -> None:
            entity[Position2].x.increase_by(0.25)

        @ecs.system_plan
        def neighbors(entity: ecs.Query[Position2, Health]) -> None:
            point = ecs.spatial.point2(entity[Position2].x, entity[Position2].y)
            nearby = ecs.spatial.neighbors(
                entity,
                position=point,
                radius=radius,
                algorithm=cast(Any, algorithm),
                include_self=False,
                allow_fallback=False,
            )
            entity[Health].value.set_to(nearby.count())

    world.order(["movement", "spatial"])
    world.add_system(move, group="movement")
    world.add_system(neighbors, group="spatial")
    for _ in range(frames):
        world.run_pre_draw_systems()
    points: tuple[tuple[float, ...], ...]
    if dimensions == 3:
        points = tuple(
            (float(x), float(y), float(z))
            for x, y, z in entity_rows(world, Position3, "x", "y", "z")
        )
    else:
        points = tuple((float(x), float(y)) for x, y in entity_rows(world, Position2, "x", "y"))
    counts = tuple(value for (value,) in entity_rows(world, Health, "value"))
    assert_equal(counts, _expected_neighbor_counts(points, radius), "spatial brute-force parity")
    algorithm_counter = {
        "spatial-hash-grid": "ecs_spatial_algorithm_hash_grid",
        "spatial-quadtree": "ecs_spatial_algorithm_quadtree",
        "spatial-octree": "ecs_spatial_algorithm_octree",
        "spatial-hilbert": "ecs_spatial_algorithm_hilbert_curve",
    }[plan.case_kind]
    require_counter_minimums(
        world.diagnostics(),
        {
            algorithm_counter: 1,
            "ecs_spatial_candidate_rows": 1,
            "ecs_spatial_exact_rows": 1,
            "ecs_physical_system_runs": frames * 2,
        },
    )
    return _outcome(world, {"points": points, "counts": counts, "update": update}, count * frames)


def _integrated(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    frames = _positive_int(plan.parameters, "frames", 1_000)
    width = _positive_int(plan.parameters, "width", 4_096)
    height = _positive_int(plan.parameters, "height", 4_096)
    fixtures = generated_rows(count)
    simulation = plan.case_kind == "simulation-render"

    @ecs.system_plan(group="simulation")
    def move(entity: ecs.Query[Position2, Velocity2]) -> None:
        entity[Position2].x.increase_by(entity[Velocity2].dx)

    @ecs.system_plan(name="render_entities", group="draw")
    def render_entities(entity: ecs.Query[Position2]) -> None:
        ca.no_stroke()
        ca.fill(40, 190, 120)
        if simulation:
            ca.rect(entity[Position2].x, entity[Position2].y, 2.0, 2.0)
        else:
            ca.circle(entity[Position2].x, entity[Position2].y, 2.0)

    class IntegratedSketch(Sketch):
        def setup(self) -> None:
            self.create_canvas(width, height)
            self.order(["simulation", "draw"])
            for row in fixtures:
                if simulation:
                    self.add_entity(row.position2, row.velocity)
                else:
                    self.add_entity(row.position2)
            if simulation:
                self.add_system(move)
            self.add_system(render_entities)

        def draw(self) -> None:
            self.background(6, 8, 12)

    context = IntegratedSketch().run(headless=True, max_frames=frames)
    assert_equal(context.frame_count, frames, "integrated frame count")
    pixels = context.load_pixel_bytes()
    assert_equal(len(pixels), width * height * 4, "integrated pixel byte count")
    diagnostics = context.ecs_diagnostics()
    minimum_runs = frames * (2 if simulation else 1)
    require_counter_minimums(
        diagnostics,
        {
            "ecs_physical_system_runs": minimum_runs,
            "ecs_canvas_commands": frames * 2,
            "ecs_canvas_direct_fill_primitives": count * frames,
        },
    )
    positions = entity_rows(context.ecs, Position2, "x", "y")
    expected = tuple(
        (
            row.position2.x + (frames * row.velocity.dx if simulation else 0.0),
            row.position2.y,
        )
        for row in fixtures
    )
    assert_equal(positions, expected, "integrated world state")
    state = {
        "positions": positions,
        "pixel_sha256": sha256(pixels).hexdigest(),
        "frames": frames,
    }
    return _Outcome(
        diagnostics,
        {
            "correctness_digest": correctness_digest(state),
            "frame_digest": "sha256:" + sha256(pixels).hexdigest(),
            "frames": frames,
            "pixel_bytes": len(pixels),
        },
        count * frames,
        {"renderer": context.renderer_performance_counters()},
    )


def _diagnostics_reset(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = _spawn_world(count, full=True)
    world.add_system(_advance_definition())
    world.run_pre_draw_systems()
    before = world.diagnostics()
    require_counter_minimums(
        before, {"ecs_physical_system_runs": 1, "ecs_physical_fields_written": count}
    )
    world.reset_diagnostics()
    reset = world.diagnostics()
    assert_equal(reset.get("ecs_physical_system_runs", 0), 0, "diagnostic reset")
    world.run_pre_draw_systems()
    after = world.diagnostics()
    assert_equal(after["ecs_physical_system_runs"], 1, "post-reset system runs")
    return _outcome(world, {"before": before, "after": after}, 2)


def _failure_contracts(plan: WorkloadPlan) -> _Outcome:
    failures: list[tuple[str, str]] = []
    world = EcsWorld()
    stale = world.add_entity(Position2(0.0, 0.0))
    world.despawn_entity(stale)
    try:
        world.add_tag(stale, "invalid")
    except StaleEntityError as error:
        failures.append((type(error).__name__, str(error)))

    strict_world = EcsWorld()
    strict_world.configure(strict=True)
    strict_world.add_entity(Position2(0.0, 0.0))

    @ecs.system_plan(parallel=True)
    def conflict(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.set_to(1.0)
        entity[Position2].x.set_to(2.0)

    strict_world.add_system(conflict)
    try:
        strict_world.run_pre_draw_systems()
    except SystemPlanError as error:
        failures.append((type(error).__name__, str(error)))
    try:
        ecs.spatial.HashGrid(cell_size=0.0)
    except ValueError as error:
        failures.append((type(error).__name__, str(error)))
    assert_equal(
        [name for name, _ in failures],
        ["StaleEntityError", "SystemPlanError", "ValueError"],
        "failure types",
    )
    require_counter_minimums(strict_world.diagnostics(), {"ecs_strict_mode_errors": 1})
    return _outcome(strict_world, failures, 3)


def _bounded_longevity(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    frames = _positive_int(plan.parameters, "frames", 100_000)
    churn = _positive_int(plan.parameters, "churn_count", count)
    if churn > count:
        raise EcsWorkloadError("churn_count cannot exceed entity_count")
    world = _spawn_world(count, full=True)
    world.add_system(_advance_definition())
    handles = [view.entity for view in world.iter_entities(Position2)]
    for frame in range(frames):
        for index in range(churn):
            if frame % 2:
                world.remove_tag(handles[index], SELECTED)
            else:
                world.add_tag(handles[index], SELECTED)
        world.emit_event(Pulse(1, frame))
        world.run_pre_draw_systems()
        world.clear_events(Pulse)
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_entities_alive"], count, "longevity live entities")
    assert_equal(diagnostics["ecs_rust_compiled_plans"], 1, "longevity compiled plan bound")
    assert_equal(world.read_events(Pulse), (), "longevity event cleanup")
    positions = entity_rows(world, Position2, "x", "y")
    return _outcome(world, {"positions": positions, "frames": frames}, count * frames)


_HANDLERS: Mapping[str, Callable[[WorkloadPlan], _Outcome]] = {
    "schema-storage": _schema_storage,
    "spawn-archetypes": _spawn_archetypes,
    "structural-churn": _structural_churn,
    "query-order": _query_order,
    "batch-transport": _batch_transport,
    "cardinality": _cardinality,
    "plan-build-compile": _plan_build_compile,
    "plan-cache-release": _plan_cache_release,
    "group-order": _group_order,
    "parallel-snapshot": _parallel_snapshot,
    "simulated-multisystem": _simulated_multisystem,
    "change-structural": _change_structural,
    "resources-events": _resources_events,
    "python-system-udf": _python_system_udf,
    "udf-plan": _udf_plan,
    "spatial-hash-grid": _spatial,
    "spatial-quadtree": _spatial,
    "spatial-octree": _spatial,
    "spatial-hilbert": _spatial,
    "compact-fill": _integrated,
    "simulation-render": _integrated,
    "diagnostics-reset": _diagnostics_reset,
    "failure-contracts": _failure_contracts,
    "bounded-longevity": _bounded_longevity,
}


def dispatch(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass,
) -> SuiteExecution:
    """Execute one exact bounded ECS case through its declared production route."""

    plan = build_workload(workload_id, parameters, execution_class)
    outcome = _HANDLERS[plan.case_kind](plan)
    if outcome.actual_work_units != plan.work_units:
        raise EcsOracleError(
            f"declared work_units={plan.work_units} but workload completed "
            f"{outcome.actual_work_units} units"
        )
    require_counters(outcome.diagnostics, plan.required_counters)
    summary = {
        **dict(outcome.summary),
        "work_units": outcome.actual_work_units,
        "case_kind": plan.case_kind,
        "execution_route": plan.execution_class.value,
    }
    actual_digest = summary.get("correctness_digest")
    if not isinstance(actual_digest, str):
        raise EcsOracleError("every ECS workload must return a correctness digest")
    if actual_digest != plan.expected_correctness_digest:
        raise EcsOracleError(
            f"ECS case {plan.case_kind!r} correctness digest mismatch: "
            f"expected {plan.expected_correctness_digest}, got {actual_digest}"
        )
    summary["execution_layer"] = plan.execution_layer
    diagnostics: dict[str, object] = {"ecs": dict(outcome.diagnostics)}
    if outcome.extra_diagnostics is not None:
        diagnostics.update(outcome.extra_diagnostics)
    return SuiteExecution(diagnostics=diagnostics, summary=summary)
