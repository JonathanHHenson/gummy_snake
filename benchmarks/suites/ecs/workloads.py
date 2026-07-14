"""Static bounded production-path workloads for the replacement ECS suite."""

# ECS query/resource annotations are runtime subscription specifications rather than
# static generic classes; mypy cannot model that public declaration syntax.
# mypy: disable-error-code=type-arg
from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack
from dataclasses import asdict, dataclass, make_dataclass, replace
from typing import Annotated, Any, cast

from benchmarks.governance import ExecutionClass
from benchmarks.suites.registry import SuiteExecution
from gummysnake import Sketch, ecs
from gummysnake.ecs import canvas as ca
from gummysnake.ecs import types as ecs_t
from gummysnake.ecs.physical import build_physical_payload
from gummysnake.ecs.world import EcsWorld
from gummysnake.exceptions import (
    ComponentSchemaError,
    EntityNotFoundError,
    StaleEntityError,
    SystemPlanError,
)

from .fixtures import (
    ACTIVE,
    SELECTED,
    AllStorageRecord,
    Bounds2,
    Counter,
    Health,
    Position2,
    Position3,
    Pulse,
    StorageRecord,
    Velocity2,
    all_storage_record,
    expected_all_storage_record,
    fixture_digest,
    generated_rows,
    schema_fixture_types,
    spatial_points,
    spawn_component_types,
    spawn_component_value,
    transport_component_type,
    transport_value,
)
from .oracles import (
    CounterExpectation,
    EcsOracleError,
    assert_diagnostic_values,
    assert_equal,
    assert_path_counters,
    correctness_digest,
    entity_rows,
    frame_digest,
    require_counter_minimums,
    require_counters,
    world_state_digest,
)


class EcsWorkloadError(ValueError):
    """A static ECS workload declaration is unknown, unsafe, or internally inconsistent."""


class ExecutionRouteError(EcsWorkloadError):
    """A workload requested an undeclared execution class or substituted route."""


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXECUTION_LAYERS = frozenset({"R", "P", "H", "I"})
_IMPLEMENTED_LAYER_ROUTES: Mapping[str, ExecutionClass] = {
    "P": ExecutionClass.HEADLESS,
    "H": ExecutionClass.HEADLESS,
}
FIXTURE_SEED = 290_001
_RELEASE_PROVENANCE_PROFILE = "isolated-release-wheel-v1"
_ORACLE_PROFILES = frozenset({"full-world-v1", "full-world-frame-v1", "failure-trace-v1"})
_PATH_PROFILE_PATHS: Mapping[str, tuple[str, ...]] = {
    "public-bridge-storage": ("public-python-api", "pyo3-canvas-ecs-bridge", "rust-ecs"),
    "public-bridge-plan": (
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
    ),
    "public-bridge-python-boundary": (
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs",
        "explicit-python-system-udf-boundary",
    ),
    "public-bridge-spatial": (
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
        "rust-spatial-index",
    ),
    "bounded-headless-frame": (
        "bounded-headless-sketch",
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
        "rust-canvas-offscreen",
        "public-pixel-readback",
    ),
    "public-bridge-failure": (
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-fail-closed",
    ),
}

# The shared recorder currently stores one wall-time metric. The remaining entries
# are explicit suite requirements, not claims that the shared framework records them.
ECS_METRIC_REQUIREMENTS: Mapping[str, Mapping[str, str]] = {
    "wall-time": {"status": "recorded", "source": "worker elapsed_blocks_ns"},
    "cpu-time": {"status": "blocked", "source": "shared worker has no CPU clock samples"},
    "throughput": {"status": "derivable", "source": "work_units / wall-time"},
    "p50": {"status": "blocked", "source": "shared record stores median-of-process-medians"},
    "p95": {"status": "blocked", "source": "shared record stores no percentile series"},
    "p99": {"status": "blocked", "source": "shared record stores no percentile series"},
    "peak-rss": {"status": "blocked", "source": "shared worker has no RSS sampler"},
    "ending-rss": {"status": "blocked", "source": "shared worker has no RSS sampler"},
    "rss-slope": {"status": "blocked", "source": "shared worker has no RSS sampler"},
    "bytes-per-row": {"status": "blocked", "source": "runtime exposes no ECS allocation bytes"},
    "storage-scan-write-bandwidth": {
        "status": "blocked",
        "source": "runtime exposes no separate storage scan/write byte or phase counters",
    },
    "archetype-transition-cache": {
        "status": "blocked",
        "source": "runtime exposes no archetype transition hit/miss or bytes-moved counters",
    },
    "query-cache-phases": {
        "status": "blocked",
        "source": "runtime exposes no cold-match/cache-hit/refresh/sort phase counters",
    },
    "bridge-calls": {
        "status": "blocked",
        "source": "runtime exposes no complete bridge-call counter",
    },
    "bridge-objects": {
        "status": "blocked",
        "source": "runtime exposes no complete bridge-object counter",
    },
    "python-transport-shapes": {
        "status": "blocked",
        "source": "runtime exposes no rows/tuples/scalars/temporary-byte transport counters",
    },
    "compiled-cache-counters": {"status": "diagnostic", "source": "ecs diagnostics"},
    "plan-phase-timers": {
        "status": "blocked",
        "source": (
            "runtime/shared worker exposes no reflection/serialization/PyO3/compile phase timers"
        ),
    },
    "plan-memory-ownership": {
        "status": "blocked",
        "source": "runtime exposes no expression/program bytes or spatial key refcounts",
    },
    "rows-scanned-written": {"status": "diagnostic", "source": "ecs diagnostics"},
    "world-clones": {"status": "blocked", "source": "runtime exposes no world-clone counter"},
    "scheduler-waves-conflicts-workers": {
        "status": "blocked",
        "source": (
            "public diagnostics expose rebuild/run counts but not waves, edges, or worker controls"
        ),
    },
    "change-epoch-control": {
        "status": "blocked",
        "source": "the public facade exposes no explicit next-frame change-epoch control",
    },
    "event-queue-lifecycle": {"status": "diagnostic", "source": "ecs diagnostics"},
    "spatial-candidates-exact": {"status": "diagnostic", "source": "ecs diagnostics"},
    "spatial-update-cache-workers": {"status": "diagnostic", "source": "ecs diagnostics"},
    "headless-frame-route": {"status": "diagnostic", "source": "ecs and renderer diagnostics"},
    "native-interactive-qualification": {
        "status": "blocked",
        "source": "no registered qualified native-interactive ECS worker route",
    },
    "frame-render-present-phases": {
        "status": "blocked",
        "source": "shared worker has no ECS frame-phase timer series",
    },
}
_METRIC_PROFILES = frozenset(
    {"ecs-core", "ecs-bridge", "ecs-spatial", "ecs-frame", "ecs-longevity"}
)


@dataclass(frozen=True, slots=True)
class WorkloadPlan:
    workload_id: str
    case_kind: str
    execution_class: ExecutionClass
    execution_layer: str
    expected_correctness_digest: str
    work_units: int
    required_counters: tuple[str, ...]
    path_profile: str
    metric_profile: str
    oracle_profile: str
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Outcome:
    diagnostics: Mapping[str, object]
    summary: Mapping[str, object]
    actual_work_units: int
    extra_diagnostics: Mapping[str, object] | None = None


_CASES: Mapping[str, frozenset[str]] = {
    "storage-entity-archetype": frozenset(
        {
            "schema-storage",
            "schema-registration",
            "storage-semantics",
            "spawn-archetypes",
            "spawn-shape",
            "structural-churn",
            "sparse-id-pressure",
        }
    ),
    "query-view-transport": frozenset(
        {
            "query-order",
            "query-selectivity",
            "query-filter-plan",
            "query-join-shape",
            "batch-transport",
            "transport-family",
            "cardinality",
            "cardinality-scale",
        }
    ),
    "plan-compile-cache": frozenset(
        {
            "plan-build-compile",
            "plan-shape",
            "plan-system-scale",
            "plan-cache-release",
            "plan-steady-reuse",
            "plan-schema-invalidation",
            "plan-hostile",
        }
    ),
    "scheduler-executor": frozenset(
        {"group-order", "parallel-snapshot", "schedule-scale", "simulated-multisystem"}
    ),
    "mutation-boundaries": frozenset(
        {
            "change-structural",
            "event-volume",
            "python-system-udf",
            "resources-events",
            "structural-shape",
            "udf-plan",
        }
    ),
    "spatial-algorithms": frozenset(
        {
            "spatial-distribution",
            "spatial-hash-grid",
            "spatial-hilbert",
            "spatial-octree",
            "spatial-quadtree",
        }
    ),
    "integrated-headless-frame": frozenset({"compact-fill", "hidpi-fill", "simulation-render"}),
    "diagnostics-failures-longevity": frozenset(
        {"bounded-longevity", "diagnostics-reset", "diagnostics-volume", "failure-contracts"}
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
        "fixture_seed",
        "path_profile",
        "metric_profile",
        "oracle_profile",
        "release_provenance_profile",
    }
)
_CASE_PARAMETERS: Mapping[str, frozenset[str]] = {
    "schema-storage": frozenset({"passes"}),
    "schema-registration": frozenset({"schema_count", "field_count", "passes"}),
    "storage-semantics": frozenset({"entity_count", "list_length"}),
    "spawn-archetypes": frozenset({"entity_count"}),
    "spawn-shape": frozenset({"entity_count", "component_count", "field_count", "tag_count"}),
    "structural-churn": frozenset({"entity_count", "iterations", "churn_count"}),
    "sparse-id-pressure": frozenset({"historical_count", "live_count"}),
    "query-order": frozenset({"entity_count"}),
    "query-selectivity": frozenset({"entity_count", "selectivity_percent"}),
    "query-filter-plan": frozenset({"entity_count"}),
    "query-join-shape": frozenset(
        {"query_count", "origin_rows", "target_rows", "auxiliary_rows", "selectivity_percent"}
    ),
    "batch-transport": frozenset({"entity_count"}),
    "transport-family": frozenset({"entity_count", "field_count", "storage_family"}),
    "cardinality": frozenset(),
    "cardinality-scale": frozenset({"match_count"}),
    "plan-build-compile": frozenset({"system_count"}),
    "plan-shape": frozenset(
        {"action_count", "depth", "query_count", "repeated_subexpression_percent"}
    ),
    "plan-system-scale": frozenset({"system_count"}),
    "plan-cache-release": frozenset({"frames", "cycles"}),
    "plan-steady-reuse": frozenset({"frames"}),
    "plan-schema-invalidation": frozenset({"frames"}),
    "plan-hostile": frozenset(),
    "group-order": frozenset({"frames"}),
    "parallel-snapshot": frozenset({"entity_count"}),
    "schedule-scale": frozenset({"entity_count", "frames", "group_count", "system_count"}),
    "simulated-multisystem": frozenset({"entity_count", "frames", "system_count"}),
    "change-structural": frozenset({"entity_count"}),
    "structural-shape": frozenset({"entity_count", "mutation_percent", "operation"}),
    "resources-events": frozenset({"event_count"}),
    "event-volume": frozenset({"event_count", "reader_count"}),
    "python-system-udf": frozenset({"entity_count"}),
    "udf-plan": frozenset({"entity_count"}),
    "spatial-hash-grid": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-quadtree": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-octree": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-hilbert": frozenset({"entity_count", "frames", "radius", "update_policy"}),
    "spatial-distribution": frozenset(
        {
            "algorithm",
            "dimensions",
            "distribution",
            "entity_count",
            "frames",
            "movement_percent",
            "radius",
            "sharing_systems",
            "update_policy",
        }
    ),
    "compact-fill": frozenset({"entity_count", "frames", "width", "height"}),
    "hidpi-fill": frozenset({"density", "entity_count", "frames", "height", "width"}),
    "simulation-render": frozenset({"entity_count", "frames", "width", "height"}),
    "diagnostics-reset": frozenset({"entity_count"}),
    "diagnostics-volume": frozenset({"entity_count", "reset_every", "snapshots"}),
    "failure-contracts": frozenset(),
    "bounded-longevity": frozenset({"entity_count", "frames", "churn_count"}),
}
_CASE_CONTRACTS: Mapping[str, tuple[str, str, str]] = {
    "schema-storage": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "schema-registration": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "storage-semantics": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "spawn-archetypes": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "spawn-shape": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "structural-churn": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "sparse-id-pressure": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "query-order": ("public-bridge-storage", "ecs-bridge", "full-world-v1"),
    "query-selectivity": ("public-bridge-storage", "ecs-bridge", "full-world-v1"),
    "query-filter-plan": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "query-join-shape": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "batch-transport": ("public-bridge-storage", "ecs-bridge", "full-world-v1"),
    "transport-family": ("public-bridge-storage", "ecs-bridge", "full-world-v1"),
    "cardinality": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "cardinality-scale": ("public-bridge-storage", "ecs-core", "full-world-v1"),
    "plan-build-compile": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-shape": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-system-scale": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-cache-release": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-steady-reuse": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-schema-invalidation": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "plan-hostile": ("public-bridge-failure", "ecs-core", "failure-trace-v1"),
    "group-order": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "parallel-snapshot": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "schedule-scale": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "simulated-multisystem": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "change-structural": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "structural-shape": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "resources-events": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "event-volume": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "python-system-udf": (
        "public-bridge-python-boundary",
        "ecs-bridge",
        "full-world-v1",
    ),
    "udf-plan": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "spatial-hash-grid": ("public-bridge-spatial", "ecs-spatial", "full-world-v1"),
    "spatial-quadtree": ("public-bridge-spatial", "ecs-spatial", "full-world-v1"),
    "spatial-octree": ("public-bridge-spatial", "ecs-spatial", "full-world-v1"),
    "spatial-hilbert": ("public-bridge-spatial", "ecs-spatial", "full-world-v1"),
    "spatial-distribution": ("public-bridge-spatial", "ecs-spatial", "full-world-v1"),
    "compact-fill": ("bounded-headless-frame", "ecs-frame", "full-world-frame-v1"),
    "hidpi-fill": ("bounded-headless-frame", "ecs-frame", "full-world-frame-v1"),
    "simulation-render": (
        "bounded-headless-frame",
        "ecs-frame",
        "full-world-frame-v1",
    ),
    "diagnostics-reset": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "diagnostics-volume": ("public-bridge-plan", "ecs-core", "full-world-v1"),
    "failure-contracts": ("public-bridge-failure", "ecs-core", "failure-trace-v1"),
    "bounded-longevity": ("public-bridge-plan", "ecs-longevity", "full-world-v1"),
}


def _positive_int(parameters: Mapping[str, object], name: str, maximum: int = 100_000) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise EcsWorkloadError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _nonnegative_int(parameters: Mapping[str, object], name: str, maximum: int = 1_000_000) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise EcsWorkloadError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _enum_int(parameters: Mapping[str, object], name: str, allowed: set[int]) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
        raise EcsWorkloadError(f"{name} must be one of {sorted(allowed)}")
    return value


def _enum_string(parameters: Mapping[str, object], name: str, allowed: set[str]) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or value not in allowed:
        raise EcsWorkloadError(f"{name} must be one of {sorted(allowed)}")
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
    fixture_seed = parameters["fixture_seed"]
    if fixture_seed != FIXTURE_SEED:
        raise EcsWorkloadError(f"fixture_seed must be the frozen ECS seed {FIXTURE_SEED}")
    path_profile = parameters["path_profile"]
    metric_profile = parameters["metric_profile"]
    oracle_profile = parameters["oracle_profile"]
    if not all(isinstance(value, str) for value in (path_profile, metric_profile, oracle_profile)):
        raise EcsWorkloadError("path_profile, metric_profile, and oracle_profile must be strings")
    assert isinstance(path_profile, str)
    assert isinstance(metric_profile, str)
    assert isinstance(oracle_profile, str)
    expected_contract = _CASE_CONTRACTS[case_kind]
    actual_contract = (path_profile, metric_profile, oracle_profile)
    if actual_contract != expected_contract:
        raise EcsWorkloadError(
            f"ECS case {case_kind!r} requires path/metric/oracle profiles "
            f"{expected_contract!r}, got {actual_contract!r}"
        )
    if path_profile not in _PATH_PROFILE_PATHS:
        raise EcsWorkloadError(f"unknown ECS path_profile: {path_profile!r}")
    if metric_profile not in _METRIC_PROFILES:
        raise EcsWorkloadError(f"unknown ECS metric_profile: {metric_profile!r}")
    if oracle_profile not in _ORACLE_PROFILES:
        raise EcsWorkloadError(f"unknown ECS oracle_profile: {oracle_profile!r}")
    if parameters["release_provenance_profile"] != _RELEASE_PROVENANCE_PROFILE:
        raise EcsWorkloadError(
            f"ECS cases require release_provenance_profile={_RELEASE_PROVENANCE_PROFILE!r}"
        )
    return WorkloadPlan(
        workload_id=workload_id,
        case_kind=case_kind,
        execution_class=route,
        execution_layer=execution_layer,
        expected_correctness_digest=expected_digest,
        work_units=_positive_int(parameters, "work_units", 100_000_000),
        required_counters=_required_counters(parameters),
        path_profile=path_profile,
        metric_profile=metric_profile,
        oracle_profile=oracle_profile,
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


def _semantic_outcome(
    world: EcsWorld,
    semantic_payload: object,
    actual_work_units: int,
    *,
    extra_summary: Mapping[str, object] | None = None,
) -> _Outcome:
    """Return a compact exact oracle for large matrix cases without mirroring columns."""

    digest = correctness_digest(semantic_payload)
    return _Outcome(
        world.diagnostics(),
        {
            "correctness_digest": digest,
            "semantic_digest": digest,
            **({} if extra_summary is None else dict(extra_summary)),
        },
        actual_work_units,
    )


def _outcome(
    world: EcsWorld,
    semantic_trace: object,
    actual_work_units: int,
    *,
    component_types: Iterable[type[Any]] = (),
    tags: Iterable[str] = (),
    resource_types: Iterable[type[Any]] = (),
    event_types: Iterable[type[Any]] = (),
    dead_entities: Iterable[object] = (),
) -> _Outcome:
    canonical_state = world_state_digest(
        world,
        semantic_trace,
        component_types=component_types,
        tags=tags,
        resource_types=resource_types,
        event_types=event_types,
        dead_entities=dead_entities,
    )
    diagnostics = world.diagnostics()
    return _Outcome(
        diagnostics,
        {
            "correctness_digest": canonical_state.digest(),
            "world_state_digest": canonical_state.digest(),
            "entities_alive": canonical_state.alive_entities,
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


def _schema_registration(plan: WorkloadPlan) -> _Outcome:
    schema_count = _enum_int(plan.parameters, "schema_count", {1, 16, 64, 256})
    field_count = _enum_int(plan.parameters, "field_count", {1, 4, 16})
    passes = _positive_int(plan.parameters, "passes", 16)
    world = EcsWorld()
    schema_types = schema_fixture_types(schema_count, field_count)
    mappings: list[tuple[tuple[str, str], ...]] = []
    for _ in range(passes):
        mappings = [
            tuple((name, storage.name) for name, storage in world.validate_schema(schema).items())
            for schema in schema_types
        ]
    expected_mapping = tuple((f"field_{index:02d}", "Float64") for index in range(field_count))
    assert_equal(tuple(mappings), (expected_mapping,) * schema_count, "schema registration mapping")
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_component_schemas_total"], schema_count, "Python schema count")
    assert_equal(diagnostics["ecs_rust_component_schemas_total"], schema_count, "Rust schema count")
    payload = {
        "schema_count": schema_count,
        "field_count": field_count,
        "passes": passes,
        "schema_names": tuple(schema.__name__ for schema in schema_types),
        "mapping": expected_mapping,
    }
    return _semantic_outcome(world, payload, schema_count * field_count * passes)


def _storage_semantics(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 10_000)
    list_length = _nonnegative_int(plan.parameters, "list_length", 256)
    if list_length not in {0, 4, 32, 256}:
        raise EcsWorkloadError("list_length must be one of 0, 4, 32, or 256")
    world = EcsWorld()
    handles = [world.add_entity(all_storage_record(index, list_length)) for index in range(count)]
    snapshots = tuple(
        cast(AllStorageRecord, world.component_snapshot(handle, AllStorageRecord))
        for handle in handles
    )
    expected = tuple(expected_all_storage_record(index, list_length) for index in range(count))
    assert_equal(snapshots, expected, "all-storage exact readback")

    before_failure = world.diagnostics()["ecs_entities_alive"]
    invalid = replace(all_storage_record(count, list_length), u8=256)
    failures: list[tuple[str, str]] = []
    try:
        world.add_entity(Position2(999.0, 999.0), invalid)
    except (ComponentSchemaError, ValueError) as error:
        failures.append((type(error).__name__, str(error)))
    assert_equal(len(failures), 1, "invalid storage failure count")
    assert_equal(
        world.diagnostics()["ecs_entities_alive"],
        before_failure,
        "transactional invalid spawn entity count",
    )
    payload = {
        "records": tuple(asdict(snapshot) for snapshot in snapshots),
        "list_length": list_length,
        "failure": failures[0],
        "integer_ranges": {
            "i8": (-128, 127),
            "u8": (0, 255),
            "i16": (-32_768, 32_767),
            "u16": (0, 65_535),
            "i32": (-(2**31), 2**31 - 1),
            "u32": (0, 2**32 - 1),
            "i64": (-(2**63), 2**63 - 1),
            "u64": (0, 2**64 - 1),
        },
    }
    values_per_row = 17 + list_length
    return _semantic_outcome(world, payload, count * values_per_row)


def _spawn_archetypes(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    world = _spawn_world(count)
    positions = entity_rows(world, Position2, "x", "y")
    expected = tuple((row.position2.x, row.position2.y) for row in generated_rows(count))
    assert_equal(positions, expected, "spawned position rows")
    tagged = tuple(view.entity.index for view in world.iter_entities(Position2, tags=[ACTIVE]))
    assert_equal(tagged, tuple(range(0, count, 3)), "tagged deterministic order")
    return _outcome(
        world,
        {"positions": positions, "active": tagged},
        count,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _spawn_shape(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 100_000)
    component_count = _enum_int(plan.parameters, "component_count", {1, 4, 8})
    field_count = _enum_int(plan.parameters, "field_count", {1, 4, 16})
    tag_count = _enum_int(plan.parameters, "tag_count", {0, 2, 8})
    component_types = spawn_component_types(component_count, field_count)
    tags = tuple(f"spawn-tag-{index}" for index in range(tag_count))
    world = EcsWorld()
    handles = []
    shape_trace: list[tuple[int, int]] = []
    for entity_index in range(count):
        width = 1 + entity_index % component_count
        entity_tags = tags[: entity_index % (tag_count + 1)] if tags else ()
        components = tuple(
            spawn_component_value(component_types[index], entity_index, index, field_count)
            for index in range(width)
        )
        handles.append(world.add_entity(*cast(tuple[Any, ...], components), tags=entity_tags))
        shape_trace.append((width, len(entity_tags)))
    field_names = tuple(f"field_{index:02d}" for index in range(field_count))
    first_rows = tuple(world.iter_component_fields(component_types[0], *field_names))
    expected_rows = tuple(
        tuple(float(entity_index * 10_000 + field_index) for field_index in range(field_count))
        for entity_index in range(count)
    )
    assert_equal(first_rows, expected_rows, "spawn shape first-component values")
    assert_equal(tuple(handle.index for handle in handles), tuple(range(count)), "spawn entity IDs")
    tag_orders = {
        tag: tuple(view.entity.index for view in world.iter_entities(tags=[tag])) for tag in tags
    }
    expected_tag_orders = {
        tag: tuple(
            entity_index
            for entity_index in range(count)
            if entity_index % (tag_count + 1) > tag_index
        )
        for tag_index, tag in enumerate(tags)
    }
    assert_equal(tag_orders, expected_tag_orders, "spawn tag order")
    return _semantic_outcome(
        world,
        {
            "first_rows": first_rows,
            "shape_trace": tuple(shape_trace),
            "tag_orders": tag_orders,
            "last_handle": (handles[-1].index, handles[-1].generation),
        },
        count,
    )


def _structural_churn(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    iterations = _positive_int(plan.parameters, "iterations", 100)
    churn = _positive_int(plan.parameters, "churn_count", count)
    if churn > count:
        raise EcsWorkloadError("churn_count cannot exceed entity_count")
    world = EcsWorld()
    handles = [world.add_entity(row.position2) for row in generated_rows(count)]
    retired_handles: list[object] = []
    for cycle in range(iterations):
        for offset in range(churn):
            handle = handles[offset]
            world.add_component(handle, Health(cycle + offset))
            world.add_tag(handle, SELECTED)
            world.remove_component(handle, Health)
            world.remove_tag(handle, SELECTED)
            world.despawn_entity(handle)
            retired_handles.append(handle)
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
        component_types=(Position2,),
        tags=(SELECTED,),
        dead_entities=retired_handles,
    )


def _sparse_id_pressure(plan: WorkloadPlan) -> _Outcome:
    historical_count = _positive_int(plan.parameters, "historical_count", 100_000)
    live_count = _positive_int(plan.parameters, "live_count", historical_count)
    if live_count >= historical_count:
        raise EcsWorkloadError("live_count must be smaller than historical_count")
    world = EcsWorld()
    handles = [
        world.add_entity(Position2(float(index), float(-index)))
        for index in range(historical_count)
    ]
    retired = handles[: historical_count - live_count]
    for handle in retired:
        world.despawn_entity(handle)
    stale_failures = 0
    for handle in retired[: min(32, len(retired))]:
        try:
            world.add_tag(handle, "stale")
        except StaleEntityError:
            stale_failures += 1
    rows = entity_rows(world, Position2, "x", "y")
    expected = tuple(
        (float(index), float(-index))
        for index in range(historical_count - live_count, historical_count)
    )
    assert_equal(rows, expected, "sparse-ID surviving values")
    live_handles = tuple(
        (view.entity.index, view.entity.generation) for view in world.iter_entities(Position2)
    )
    assert_equal(
        live_handles,
        tuple((index, 0) for index in range(historical_count - live_count, historical_count)),
        "sparse-ID surviving handles",
    )
    return _semantic_outcome(
        world,
        {
            "historical_count": historical_count,
            "live_handles": live_handles,
            "rows": rows,
            "stale_failures": stale_failures,
        },
        historical_count,
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
    return _outcome(
        world,
        {"indices": indices, "health_total": health_total},
        count,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _query_selectivity(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 1_000_000)
    selectivity = _enum_int(plan.parameters, "selectivity_percent", {0, 1, 50, 100})
    selected_count = count * selectivity // 100
    world = EcsWorld()
    for index in range(count):
        if index < selected_count:
            world.add_entity(
                Position2(float(index), float(-index)), Health(index), tags=(SELECTED,)
            )
        else:
            world.add_entity(Position2(float(index), float(-index)))
    cold = tuple(
        view.entity.index for view in world.iter_entities(Position2, Health, tags=(SELECTED,))
    )
    warm = tuple(
        view.entity.index for view in world.iter_entities(Position2, Health, tags=(SELECTED,))
    )
    expected = tuple(range(selected_count))
    assert_equal(cold, expected, "cold query selectivity")
    assert_equal(warm, expected, "warm query selectivity")
    assert_equal(len(set(cold)), len(cold), "query duplicate rows")
    return _semantic_outcome(
        world,
        {
            "entity_count": count,
            "selectivity_percent": selectivity,
            "cold": cold,
            "warm": warm,
        },
        count,
    )


def _query_filter_plan(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 100_000)
    world = EcsWorld()
    for index in range(count):
        components: tuple[object, ...]
        if index % 2 == 0:
            components = (Position2(float(index), 0.0), Health(index))
        else:
            components = (Position2(float(index), 0.0),)
        tags = (ACTIVE,) if index % 3 == 0 else ()
        world.add_entity(*cast(tuple[Any, ...], components), tags=tags)

    @ecs.system_plan
    def filtered(
        entity: ecs.Query[Position2, ecs.Without[Health], ecs.Without[ecs.Tag[ACTIVE]]],  # type: ignore[valid-type]
    ) -> None:
        entity[Position2].y.set_to(entity[Position2].x + 1.0)

    world.add_system(filtered)
    world.run_pre_draw_systems()
    matched = tuple(
        index
        for index, (x, y) in enumerate(entity_rows(world, Position2, "x", "y"))
        if y == x + 1.0
    )
    expected = tuple(index for index in range(count) if index % 2 == 1 and index % 3 != 0)
    assert_equal(matched, expected, "required/excluded query result")
    return _semantic_outcome(
        world,
        {"matched": matched, "expected": expected},
        len(expected),
    )


def _query_join_shape(plan: WorkloadPlan) -> _Outcome:
    query_count = _enum_int(plan.parameters, "query_count", {2, 3, 4})
    origin_rows = _positive_int(plan.parameters, "origin_rows", 1_000)
    target_rows = _positive_int(plan.parameters, "target_rows", 10_000)
    auxiliary_rows = _positive_int(plan.parameters, "auxiliary_rows", 1_000)
    selectivity = _enum_int(plan.parameters, "selectivity_percent", {0, 1, 50})
    selected = target_rows * selectivity // 100
    world = EcsWorld()
    world.configure(strict=False, warn_on_ambiguity=False)
    for index in range(origin_rows):
        world.add_entity(Position2(float(index), 0.0))
    for index in range(target_rows):
        world.add_entity(Velocity2(float(index), 0.0))
    for index in range(auxiliary_rows):
        world.add_entity(Health(index))
        world.add_entity(Bounds2(index + 1, index + 1))

    query_specs = (
        ecs.Query[Position2],
        ecs.Query[Velocity2],
        ecs.Query[Health],
        ecs.Query[Bounds2],
    )[:query_count]

    def joined(*queries: Any) -> None:
        origin, velocity = queries[:2]
        predicate = velocity[Velocity2].dx < float(selected)
        if query_count >= 3:
            predicate = predicate & (queries[2][Health].value >= 0)
        if query_count >= 4:
            predicate = predicate & (queries[3][Bounds2].width > 0)
        with ecs.conditional(), ecs.when(predicate):
            origin[Position2].y.increase_by(1.0)

    joined.__name__ = f"join_{query_count}_{origin_rows}_{target_rows}_{selectivity}"
    annotations: dict[str, Any] = {
        f"query_{index}": query_spec for index, query_spec in enumerate(query_specs)
    }
    annotations["return"] = None
    joined.__annotations__ = annotations
    parameters = [
        inspect.Parameter(
            f"query_{index}",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=query_spec,
        )
        for index, query_spec in enumerate(query_specs)
    ]
    cast(Any, joined).__signature__ = inspect.Signature(parameters, return_annotation=None)
    definition = cast(ecs.SystemPlanDefinition, ecs.system_plan(joined))
    world.add_system(definition)
    world.run_pre_draw_systems()
    actual = entity_rows(world, Position2, "x", "y")
    auxiliary_contexts = auxiliary_rows ** (query_count - 2)
    matches_per_origin = selected * auxiliary_contexts
    expected = tuple((float(index), float(matches_per_origin)) for index in range(origin_rows))
    assert_equal(actual, expected, "multi-query join result")
    logical_contexts = origin_rows * target_rows * auxiliary_contexts
    return _semantic_outcome(
        world,
        {
            "query_count": query_count,
            "origin_rows": origin_rows,
            "target_rows": target_rows,
            "auxiliary_rows": auxiliary_rows,
            "selectivity_percent": selectivity,
            "logical_contexts": logical_contexts,
            "matches_per_origin": matches_per_origin,
            "rows": actual,
        },
        logical_contexts,
    )


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
    return _outcome(
        world,
        {"rows": rows, "fixture": fixture_digest(count)},
        count,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _transport_family(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 100_000)
    field_count = _enum_int(plan.parameters, "field_count", {1, 2, 8, 16})
    storage_family = _enum_string(
        plan.parameters, "storage_family", {"scalar", "vector", "list", "categorical"}
    )
    component_type = transport_component_type(storage_family, field_count)
    field_names = tuple(f"field_{index:02d}" for index in range(field_count))
    world = EcsWorld()
    for row in range(count):
        values = tuple(transport_value(storage_family, row, field) for field in range(field_count))
        world.add_entity(component_type(*values))
    views = tuple(world.iter_entities(component_type))
    handles = tuple((view.entity.index, view.entity.generation) for view in views)
    view_rows = tuple(
        tuple(getattr(view[component_type], field_name) for field_name in field_names)
        for view in views
    )
    batch_rows = tuple(world.iter_component_fields(component_type, *field_names))
    expected = tuple(
        tuple(transport_value(storage_family, row, field) for field in range(field_count))
        for row in range(count)
    )
    assert_equal(view_rows, expected, "EntityView/ComponentView transport")
    assert_equal(batch_rows, expected, "batch field transport")
    for row, view in enumerate(views):
        setattr(
            view[component_type],
            field_names[0],
            transport_value(storage_family, row, 0, updated=True),
        )
    updated = tuple(world.iter_component_fields(component_type, field_names[0]))
    expected_updated = tuple(
        (transport_value(storage_family, row, 0, updated=True),) for row in range(count)
    )
    assert_equal(updated, expected_updated, "ComponentView writeback")
    return _semantic_outcome(
        world,
        {
            "storage_family": storage_family,
            "field_count": field_count,
            "handles": handles,
            "view_rows": view_rows,
            "batch_rows": batch_rows,
            "updated": updated,
        },
        count * field_count * 3,
    )


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


def _cardinality_scale(plan: WorkloadPlan) -> _Outcome:
    count = _nonnegative_int(plan.parameters, "match_count", 1_000_000)
    world = EcsWorld()
    for index in range(count):
        world.add_entity(Position2(float(index), float(-index)))
    ordered = tuple(view.entity.index for view in world.iter_entities(Position2))
    assert_equal(ordered, tuple(range(count)), "cardinality ordered candidates")
    outcome: str
    try:
        entity = world.try_get_entity(Position2)
    except EntityNotFoundError:
        outcome = "many-error"
    else:
        outcome = "none" if entity is None else f"one:{entity.entity.index}"
    expected = "none" if count == 0 else "one:0" if count == 1 else "many-error"
    assert_equal(outcome, expected, "limit-aware cardinality outcome")
    return _semantic_outcome(
        world,
        {"match_count": count, "ordered": ordered, "outcome": outcome},
        max(1, count),
    )


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
    return _outcome(
        world,
        explanations,
        system_count * 2,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _generated_plan_definition(
    action_count: int,
    depth: int,
    query_count: int,
    repeated_subexpression_percent: int,
) -> ecs.SystemPlanDefinition:
    query_spec = ecs.Query[Position2]

    def generated(*queries: Any) -> None:
        entity = queries[0]
        shared = entity[Position2].x + 1.0
        repeated_count = action_count * repeated_subexpression_percent // 100
        with ExitStack() as stack:
            for _ in range(depth - 1):
                stack.enter_context(ecs.do())
            for index in range(action_count):
                value = shared if index < repeated_count else entity[Position2].x + float(index + 1)
                entity[Position2].x.set_to(value)

    generated.__name__ = (
        f"generated_{action_count}_{depth}_{query_count}_{repeated_subexpression_percent}"
    )
    annotations: dict[str, Any] = {f"query_{index}": query_spec for index in range(query_count)}
    annotations["return"] = None
    generated.__annotations__ = annotations
    parameters = [
        inspect.Parameter(
            f"query_{index}",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=query_spec,
        )
        for index in range(query_count)
    ]
    cast(Any, generated).__signature__ = inspect.Signature(parameters, return_annotation=None)
    return cast(ecs.SystemPlanDefinition, ecs.system_plan(generated))


def _plan_shape(plan: WorkloadPlan) -> _Outcome:
    action_count = _enum_int(plan.parameters, "action_count", {10, 100, 1_000, 10_000})
    depth = _enum_int(plan.parameters, "depth", {1, 16, 128})
    query_count = _enum_int(plan.parameters, "query_count", {1, 8, 64})
    repeated = _enum_int(plan.parameters, "repeated_subexpression_percent", {0, 50, 90})
    world = EcsWorld()
    world.add_entity(Position2(1.0, 2.0))
    definition = _generated_plan_definition(action_count, depth, query_count, repeated)
    built = definition.build()
    explanation = built.plan.explain()
    payload = build_physical_payload(world, built)
    queries = payload.get("queries")
    expressions = payload.get("expressions")
    actions = payload.get("actions")
    if (
        not isinstance(queries, list)
        or not isinstance(expressions, list)
        or not isinstance(actions, list)
    ):
        raise EcsOracleError("physical plan payload must expose query/expression/action lists")
    assert_equal(len(queries), query_count, "logical plan query count")
    if len(actions) < action_count:
        raise EcsOracleError(
            "logical plan action payload expected at least "
            f"{action_count} nodes, got {len(actions)}"
        )
    world.add_system(definition)
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_physical_plan_compiles"], 1, "plan shape compile count")
    payload_digest = correctness_digest(payload)
    explain_digest = correctness_digest(explanation)
    return _semantic_outcome(
        world,
        {
            "action_count": action_count,
            "depth": depth,
            "query_count": query_count,
            "repeated_subexpression_percent": repeated,
            "payload_actions": len(actions),
            "payload_expressions": len(expressions),
            "payload_digest": payload_digest,
            "explain_digest": explain_digest,
        },
        action_count,
        extra_summary={
            "payload_digest": payload_digest,
            "explain_digest": explain_digest,
            "payload_actions": len(actions),
            "payload_expressions": len(expressions),
        },
    )


def _plan_system_scale(plan: WorkloadPlan) -> _Outcome:
    system_count = _enum_int(plan.parameters, "system_count", {1, 100, 1_000})
    world = _spawn_world(1, full=True)
    definitions = [_advance_definition() for _ in range(system_count)]
    explanations = tuple(definition.explain() for definition in definitions)
    assert_equal(len(set(explanations)), 1, "equivalent plan explanations")
    handles = tuple(
        world.add_system(definition, name=f"equivalent_{index}")
        for index, definition in enumerate(definitions)
    )
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_physical_plan_compiles"], system_count, "system scale compiles")
    assert_equal(diagnostics["ecs_rust_compiled_plans"], system_count, "system scale handles")
    return _semantic_outcome(
        world,
        {
            "system_count": system_count,
            "explain_digest": correctness_digest(explanations[0]),
            "handles": tuple((handle.id, handle.name) for handle in handles),
            "compiled_plans": diagnostics["ecs_rust_compiled_plans"],
        },
        system_count,
    )


def _plan_cache_release(plan: WorkloadPlan) -> _Outcome:
    frames = _positive_int(plan.parameters, "frames", 1_000)
    cycles = _positive_int(plan.parameters, "cycles", 1_000)
    world = _spawn_world(16, full=True)
    definition = _advance_definition()
    for cycle in range(cycles):
        handle = world.add_system(definition, name=f"cached_{cycle}")
        assert_equal(
            world.diagnostics()["ecs_rust_compiled_plans"],
            1,
            f"owned compiled plan during cycle {cycle}",
        )
        for _ in range(frames):
            world.run_pre_draw_systems()
        world.remove_system(handle)
        assert_equal(
            world.diagnostics()["ecs_rust_compiled_plans"],
            0,
            f"released compiled plan after cycle {cycle}",
        )
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_physical_plan_compiles"], cycles, "plan lifecycle compiles")
    assert_equal(diagnostics["ecs_physical_system_runs"], cycles * frames, "plan lifecycle runs")
    assert_equal(
        diagnostics["ecs_steady_physical_plan_reuses"], cycles * frames, "plan lifecycle reuses"
    )
    assert_equal(diagnostics["ecs_query_cache_hits"], 0, "query cache hits")
    assert_equal(diagnostics["ecs_query_cache_misses"], 1, "query cache misses")
    assert_equal(diagnostics["ecs_query_cache_refreshes"], 0, "query cache refreshes")
    assert_equal(diagnostics["ecs_query_cache_invalidations"], 0, "query cache invalidations")
    assert_equal(diagnostics["ecs_rust_compiled_plans"], 0, "released compiled plans")
    return _outcome(
        world,
        diagnostics,
        cycles * frames,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _plan_steady_reuse(plan: WorkloadPlan) -> _Outcome:
    frames = _positive_int(plan.parameters, "frames", 10_000)
    world = _spawn_world(8, full=True)
    world.add_system(_advance_definition())
    before = world.diagnostics()
    for _ in range(frames):
        world.run_pre_draw_systems()
    after = world.diagnostics()
    assert_equal(before["ecs_physical_plan_compiles"], 1, "initial plan compile")
    assert_equal(after["ecs_physical_plan_compiles"], 1, "steady plan compile bound")
    assert_equal(after["ecs_rust_compiled_plans"], 1, "steady compiled handle bound")
    assert_equal(after["ecs_physical_system_runs"], frames, "steady plan runs")
    assert_equal(after["ecs_steady_physical_plan_reuses"], frames, "steady plan reuse count")
    rows = entity_rows(world, Position2, "x", "y")
    return _semantic_outcome(
        world,
        {"frames": frames, "rows": rows, "compile_count": 1, "reuse_count": frames},
        frames,
    )


def _plan_schema_invalidation(plan: WorkloadPlan) -> _Outcome:
    frames = _positive_int(plan.parameters, "frames", 16)
    if frames != 2:
        raise EcsWorkloadError("plan-schema-invalidation currently requires exactly two frames")
    world = _spawn_world(8, full=True)
    world.add_system(_advance_definition())
    world.run_pre_draw_systems()
    before_schema = world.diagnostics()
    world.validate_schema(Counter)
    world.run_pre_draw_systems()
    after_schema = world.diagnostics()
    assert_equal(before_schema["ecs_physical_plan_compiles"], 1, "pre-invalidation compiles")
    assert_equal(after_schema["ecs_physical_plan_compiles"], 2, "schema invalidation compiles")
    assert_equal(after_schema["ecs_rust_compiled_plans"], 1, "replaced plan handle count")
    rows = entity_rows(world, Position2, "x", "y")
    return _semantic_outcome(
        world,
        {
            "frames": frames,
            "rows": rows,
            "before_compiles": before_schema["ecs_physical_plan_compiles"],
            "after_compiles": after_schema["ecs_physical_plan_compiles"],
            "compiled_handles": after_schema["ecs_rust_compiled_plans"],
        },
        frames,
    )


def _plan_hostile(plan: WorkloadPlan) -> _Outcome:
    failures: list[tuple[str, str]] = []

    @ecs.system_plan
    def missing_annotation(entity) -> None:  # type: ignore[no-untyped-def]
        del entity

    try:
        missing_annotation.explain()
    except SystemPlanError as error:
        failures.append((type(error).__name__, str(error)))

    @ecs.system_plan
    def invalid_return(entity: ecs.Query[Position2]) -> None:
        del entity
        return cast(Any, 1)

    try:
        invalid_return.explain()
    except SystemPlanError as error:
        failures.append((type(error).__name__, str(error)))

    try:
        ecs_t.List(ecs_t.List(ecs_t.Int16))
    except TypeError as error:
        failures.append((type(error).__name__, str(error)))

    conflict_int = make_dataclass(
        "HostileConflict",
        [("value", Annotated[int, ecs_t.Int32])],
        namespace={"__module__": __name__},
    )
    conflict_float = make_dataclass(
        "HostileConflict",
        [("value", float)],
        namespace={"__module__": __name__},
    )
    conflict_world = EcsWorld()
    conflict_world.validate_schema(conflict_int)
    try:
        conflict_world.validate_schema(conflict_float)
    except (ComponentSchemaError, ValueError) as error:
        failures.append((type(error).__name__, str(error)))
    assert_equal(len(failures), 4, "hostile plan/schema failure count")
    assert_equal(
        conflict_world.diagnostics()["ecs_entities_alive"], 0, "hostile failure allocation"
    )
    return _semantic_outcome(conflict_world, {"failures": tuple(failures)}, 4)


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
    return _outcome(world, row, frames * 3, component_types=(Position2,))


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
    return _outcome(world, rows, count * 2, component_types=(Position2,))


def _schedule_scale(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 10_000)
    frames = _positive_int(plan.parameters, "frames", 1_000)
    systems = _enum_int(plan.parameters, "system_count", {8, 64, 512})
    groups = _enum_int(plan.parameters, "group_count", {1, 8, 16, 128})
    if groups > systems:
        raise EcsWorkloadError("group_count cannot exceed system_count")
    world = EcsWorld()
    for row in generated_rows(count):
        world.add_entity(row.position2)

    @ecs.system_plan(parallel=True)
    def increment(entity: ecs.Query[Position2]) -> None:
        entity[Position2].x.increase_by(1.0)

    group_names = tuple(f"schedule_group_{index:03d}" for index in range(groups))
    world.order(group_names)
    for index in range(systems):
        world.add_system(
            increment,
            name=f"schedule_system_{index:04d}",
            group=group_names[index % groups],
        )
    for _ in range(frames):
        world.run_pre_draw_systems()
    rows = entity_rows(world, Position2, "x")
    expected = tuple((row.position2.x + frames * systems,) for row in generated_rows(count))
    assert_equal(rows, expected, "scheduled scale world result")
    return _outcome(
        world,
        {"groups": group_names, "positions": rows},
        count * frames * systems,
        component_types=(Position2,),
    )


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
    return _outcome(world, rows, count * frames * systems, component_types=(Position2,))


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
    return _outcome(
        world,
        {"selected": selected, "remaining": remaining},
        count,
        component_types=(Position2, Health),
        tags=(SELECTED,),
    )


def _structural_shape(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 100_000)
    mutation_percent = _enum_int(plan.parameters, "mutation_percent", {1, 10, 100})
    operation = _enum_string(
        plan.parameters,
        "operation",
        {"add-component", "add-tag", "despawn", "remove-component", "remove-tag"},
    )
    selected_count = max(1, count * mutation_percent // 100)
    world = EcsWorld()
    selected_handles: list[object] = []
    for index in range(count):
        components: tuple[object, ...]
        if operation == "add-component":
            components = (Position2(float(index), 0.0),)
        else:
            components = (Position2(float(index), 0.0), Health(index))
        tags = [ACTIVE] if index < selected_count else []
        if operation == "remove-tag" and index < selected_count:
            tags.append(SELECTED)
        handle = world.add_entity(*cast(tuple[Any, ...], components), tags=tags)
        if index < selected_count:
            selected_handles.append(handle)

    @ecs.system_plan
    def mutate(entity: ecs.Query[ecs.Tag[ACTIVE], Position2]) -> None:  # type: ignore[valid-type]
        target = cast(Any, entity).entity
        if operation == "add-component":
            target.add_component(Health(7))
        elif operation == "remove-component":
            target.remove_component(Health)
        elif operation == "add-tag":
            target.add_tag(SELECTED)
        elif operation == "remove-tag":
            target.remove_tag(SELECTED)
        else:
            target.despawn()

    world.add_system(mutate)
    world.run_pre_draw_systems()
    alive = tuple(view.entity.index for view in world.iter_entities())
    health = tuple(view.entity.index for view in world.iter_entities(Health))
    selected = tuple(view.entity.index for view in world.iter_entities(tags=[SELECTED]))
    if operation == "add-component":
        assert_equal(health, tuple(range(selected_count)), "structural add-component rows")
    elif operation == "remove-component":
        assert_equal(
            health, tuple(range(selected_count, count)), "structural remove-component rows"
        )
    elif operation == "add-tag":
        assert_equal(selected, tuple(range(selected_count)), "structural add-tag rows")
    elif operation == "remove-tag":
        assert_equal(selected, (), "structural remove-tag rows")
    else:
        assert_equal(alive, tuple(range(selected_count, count)), "structural despawn rows")
    return _outcome(
        world,
        {
            "alive": alive,
            "health": health,
            "operation": operation,
            "selected": selected,
        },
        selected_count,
        component_types=(Position2, Health),
        tags=(ACTIVE, SELECTED),
        dead_entities=selected_handles if operation == "despawn" else (),
    )


def _resources_events(plan: WorkloadPlan) -> _Outcome:
    event_count = _positive_int(plan.parameters, "event_count")
    world = EcsWorld()
    world.set_resource(Counter(0))
    for sequence in range(event_count):
        world.emit_event(Pulse(sequence % 5 + 1, sequence, 0))

    @ecs.system_plan
    def consume(reader: ecs.EventReader[Pulse], counter: ecs.ResMut[Counter]) -> None:
        with ecs.for_each(reader) as event:
            counter[Counter].total.increase_by(event.amount)

    world.add_system(consume)
    world.run_pre_draw_systems()
    events = world.read_events(Pulse)
    expected_total = sum(sequence % 5 + 1 for sequence in range(event_count))
    assert_equal(world.get_resource(Counter).total, expected_total, "event reduction")
    event_trace = tuple((event.frame, event.sequence, event.amount) for event in events)
    assert_equal(
        tuple(event.sequence for event in events), tuple(range(event_count)), "event order"
    )
    assert_equal(tuple(event.frame for event in events), (0,) * event_count, "event frame")
    world.clear_events(Pulse)
    assert_equal(world.read_events(Pulse), (), "event cleanup")
    return _outcome(
        world,
        {"total": expected_total, "events": event_trace, "cleared": True},
        event_count,
        resource_types=(Counter,),
        event_types=(Pulse,),
    )


def _event_volume(plan: WorkloadPlan) -> _Outcome:
    event_count = _nonnegative_int(plan.parameters, "event_count", 1_000_000)
    reader_count = _enum_int(plan.parameters, "reader_count", {1, 2, 4})
    world = EcsWorld()
    world.set_resource(Counter(0))
    for sequence in range(event_count):
        world.emit_event(Pulse(sequence % 5 + 1, sequence, 0))

    @ecs.system_plan
    def consume(reader: ecs.EventReader[Pulse], counter: ecs.ResMut[Counter]) -> None:
        with ecs.for_each(reader) as event:
            counter[Counter].total.increase_by(event.amount)

    for index in range(reader_count):
        world.add_system(consume, name=f"event_reader_{index}")
    world.run_pre_draw_systems()
    events = world.read_events(Pulse)
    expected_once = sum(sequence % 5 + 1 for sequence in range(event_count))
    assert_equal(world.get_resource(Counter).total, expected_once * reader_count, "event readers")
    assert_equal(
        tuple(event.sequence for event in events), tuple(range(event_count)), "event order"
    )
    world.clear_events(Pulse)
    assert_equal(world.read_events(Pulse), (), "event volume cleanup")
    return _outcome(
        world,
        {
            "event_count": event_count,
            "reader_count": reader_count,
            "total": expected_once * reader_count,
        },
        max(1, event_count * reader_count),
        resource_types=(Counter,),
        event_types=(Pulse,),
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
    return _outcome(world, rows, count * 2, component_types=(Position2,))


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
    return _outcome(world, rows, count, component_types=(Position2,))


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
    return _outcome(
        world,
        {"points": points, "counts": counts, "update": update},
        count * frames,
        component_types=((Position3, Health) if dimensions == 3 else (Position2, Health)),
    )


def _spatial_distribution(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 10_000)
    frames = _positive_int(plan.parameters, "frames", 1_000)
    dimensions = _enum_int(plan.parameters, "dimensions", {2, 3})
    distribution = _enum_string(
        plan.parameters, "distribution", {"clustered", "diagonal", "same-cell", "uniform"}
    )
    algorithm_name = _enum_string(
        plan.parameters, "algorithm", {"hash-grid", "hilbert", "octree", "quadtree"}
    )
    movement_percent = _enum_int(plan.parameters, "movement_percent", {0, 1, 10, 100})
    sharing_systems = _enum_int(plan.parameters, "sharing_systems", {1, 4, 8})
    radius = _positive_float(plan.parameters, "radius")
    update = _enum_string(
        plan.parameters,
        "update_policy",
        {"auto", "incremental"},
    )
    if (algorithm_name == "quadtree" and dimensions != 2) or (
        algorithm_name == "octree" and dimensions != 3
    ):
        raise EcsWorkloadError("quadtree requires 2D and octree requires 3D")
    algorithm_kind = f"spatial-{algorithm_name}"
    algorithm = _spatial_algorithm(algorithm_kind, update, dimensions)
    points = spatial_points(count, dimensions, distribution)
    world = EcsWorld()
    handles = []
    for point in points:
        position: object = Position3(*point) if dimensions == 3 else Position2(*point)
        handles.append(world.add_entity(position, Health(0)))

    if dimensions == 3:

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

    for index in range(sharing_systems):
        world.add_system(neighbors, name=f"shared_spatial_{index}")
    moving = count * movement_percent // 100
    for frame in range(frames):
        if frame and moving:
            for index in range(moving):
                point = points[index]
                moved = (point[0] + frame * 0.125, *point[1:])
                value: object = Position3(*moved) if dimensions == 3 else Position2(*moved)
                world.set_component(handles[index], value)
        world.run_pre_draw_systems()
    if dimensions == 3:
        final_points = tuple(
            (float(x), float(y), float(z))
            for x, y, z in entity_rows(world, Position3, "x", "y", "z")
        )
    else:
        final_points = tuple(
            (float(x), float(y)) for x, y in entity_rows(world, Position2, "x", "y")
        )
    counts = tuple(value for (value,) in entity_rows(world, Health, "value"))
    assert_equal(
        counts,
        _expected_neighbor_counts(final_points, radius),
        "spatial distribution brute-force parity",
    )
    return _outcome(
        world,
        {
            "algorithm": algorithm_name,
            "counts": counts,
            "distribution": distribution,
            "movement_percent": movement_percent,
            "points": final_points,
            "sharing_systems": sharing_systems,
            "update": update,
        },
        count * frames * sharing_systems,
        component_types=((Position3, Health) if dimensions == 3 else (Position2, Health)),
    )


def _integrated(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count")
    frames = _positive_int(plan.parameters, "frames", 1_000)
    width = _positive_int(plan.parameters, "width", 4_096)
    height = _positive_int(plan.parameters, "height", 4_096)
    fixtures = generated_rows(count)
    simulation = plan.case_kind == "simulation-render"
    density = _enum_int(plan.parameters, "density", {1, 2}) if plan.case_kind == "hidpi-fill" else 1

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
            self.pixel_density(density)
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
    physical_width = width * density
    physical_height = height * density
    assert_equal(len(pixels), physical_width * physical_height * 4, "integrated pixel byte count")
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
    frame = frame_digest(pixels, physical_width, physical_height)
    world_state = world_state_digest(
        context.ecs,
        {"positions": positions, "frames": frames},
        component_types=((Position2, Velocity2) if simulation else (Position2,)),
    )
    diagnostics = context.ecs_diagnostics()
    combined_digest = correctness_digest(
        {"world_state_digest": world_state.digest(), "frame_digest": frame.digest()}
    )
    return _Outcome(
        diagnostics,
        {
            "correctness_digest": combined_digest,
            "world_state_digest": world_state.digest(),
            "frame_digest": frame.digest(),
            "pixel_digest": frame.pixel_sha256,
            "density": density,
            "frames": frames,
            "logical_size": (width, height),
            "physical_size": (physical_width, physical_height),
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
    assert_equal(reset["ecs_query_cache_hits"], 0, "reset query cache hits")
    assert_equal(reset["ecs_query_cache_misses"], 0, "reset query cache misses")
    assert_equal(reset["ecs_query_cache_refreshes"], 0, "reset query cache refreshes")
    assert_equal(reset["ecs_query_cache_invalidations"], 0, "reset query cache invalidations")
    assert_equal(reset["ecs_rust_compiled_plans"], 1, "reset retained compiled plan")
    world.run_pre_draw_systems()
    after = world.diagnostics()
    assert_equal(after["ecs_physical_system_runs"], 1, "post-reset system runs")
    assert_equal(after["ecs_query_cache_hits"], 0, "post-reset query cache hits")
    assert_equal(after["ecs_query_cache_misses"], 0, "post-reset query cache misses")
    assert_equal(after["ecs_query_cache_refreshes"], 0, "post-reset query cache refreshes")
    assert_equal(after["ecs_query_cache_invalidations"], 0, "post-reset query cache invalidations")
    assert_equal(after["ecs_rust_compiled_plans"], 1, "post-reset retained compiled plan")
    return _outcome(
        world,
        {"before": before, "after": after},
        2,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


def _diagnostics_volume(plan: WorkloadPlan) -> _Outcome:
    count = _positive_int(plan.parameters, "entity_count", 100_000)
    snapshots = _positive_int(plan.parameters, "snapshots", 10_000)
    reset_every = _positive_int(plan.parameters, "reset_every", snapshots)
    if reset_every > snapshots:
        raise EcsWorkloadError("reset_every cannot exceed snapshots")
    world = _spawn_world(count, full=True)
    world.add_system(_advance_definition())
    trace: list[tuple[int, int, int]] = []
    for snapshot_index in range(snapshots):
        world.run_pre_draw_systems()
        diagnostics = world.diagnostics()
        trace.append(
            (
                int(diagnostics["ecs_physical_system_runs"]),
                int(diagnostics["ecs_physical_rows_scanned"]),
                int(diagnostics["ecs_rust_compiled_plans"]),
            )
        )
        if (snapshot_index + 1) % reset_every == 0 and snapshot_index + 1 < snapshots:
            world.reset_diagnostics()
    return _outcome(
        world,
        {"reset_every": reset_every, "snapshots": tuple(trace)},
        snapshots,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE,),
    )


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

    nonstrict_world = EcsWorld()
    nonstrict_world.configure(strict=False, warn_on_ambiguity=False)
    nonstrict_world.add_entity(Position2(0.0, 0.0))
    nonstrict_world.add_system(conflict)
    nonstrict_world.run_pre_draw_systems()
    nonstrict_value = entity_rows(nonstrict_world, Position2, "x")[0][0]
    assert_equal(nonstrict_value, 2.0, "non-strict deterministic last-write-wins")
    assert_path_counters(
        nonstrict_world.diagnostics(),
        (CounterExpectation("ecs_physical_duplicate_writes", minimum=1),),
    )
    try:
        ecs.spatial.HashGrid(cell_size=0.0)
    except ValueError as error:
        failures.append((type(error).__name__, str(error)))

    cycle_world = EcsWorld()
    cycle_world.order(["cycle_a", "cycle_b"])
    try:
        cycle_world.order(["cycle_b", "cycle_a"])
    except SystemPlanError as error:
        failures.append((type(error).__name__, str(error)))

    overflow_world = EcsWorld()
    invalid_storage = replace(all_storage_record(0, 0), u8=256)
    try:
        overflow_world.add_entity(invalid_storage)
    except (ComponentSchemaError, OverflowError, ValueError) as error:
        failures.append((type(error).__name__, str(error)))
    expected_failure_types = (
        "StaleEntityError",
        "SystemPlanError",
        "ValueError",
        "SystemPlanError",
    )
    assert_equal(tuple(name for name, _ in failures[:4]), expected_failure_types, "failure types")
    assert_equal(len(failures), 5, "failure matrix size")
    assert all(message.strip() for _, message in failures)
    require_counter_minimums(strict_world.diagnostics(), {"ecs_strict_mode_errors": 1})
    return _outcome(
        strict_world,
        {
            "failures": failures,
            "retired": (stale.index, stale.generation),
            "non_strict_last_write": nonstrict_value,
        },
        6,
        component_types=(Position2,),
    )


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
        world.emit_event(Pulse(1, frame, frame))
        world.run_pre_draw_systems()
        world.clear_events(Pulse)
    diagnostics = world.diagnostics()
    assert_equal(diagnostics["ecs_entities_alive"], count, "longevity live entities")
    assert_equal(diagnostics["ecs_rust_compiled_plans"], 1, "longevity compiled plan bound")
    assert_equal(world.read_events(Pulse), (), "longevity event cleanup")
    positions = entity_rows(world, Position2, "x", "y")
    return _outcome(
        world,
        {"positions": positions, "frames": frames, "events_cleared": True},
        count * frames,
        component_types=(Position2, Velocity2, Health, Bounds2, StorageRecord),
        tags=(ACTIVE, SELECTED),
        event_types=(Pulse,),
    )


def _exact(name: str, value: int) -> CounterExpectation:
    return CounterExpectation(name, exact=value)


def _minimum(name: str, value: int) -> CounterExpectation:
    return CounterExpectation(name, minimum=value)


def _assert_runtime_path(plan: WorkloadPlan, diagnostics: Mapping[str, object]) -> None:
    """Assert the exact cataloged executor/scheduler/spatial/canvas route."""

    assert_diagnostic_values(diagnostics, {"ecs_rust_core": "available"})
    case = plan.case_kind
    parameters = plan.parameters
    expectations: list[CounterExpectation] = []
    if case == "schema-storage":
        expectations.append(_exact("ecs_component_schemas_total", 4))
    elif case == "schema-registration":
        schemas = _enum_int(parameters, "schema_count", {1, 16, 64, 256})
        expectations.extend(
            (
                _exact("ecs_component_schemas_total", schemas),
                _exact("ecs_rust_component_schemas_total", schemas),
            )
        )
    elif case in {
        "storage-semantics",
        "spawn-archetypes",
        "spawn-shape",
        "query-order",
        "query-selectivity",
        "batch-transport",
        "transport-family",
    }:
        expectations.append(_exact("ecs_entities_alive", _positive_int(parameters, "entity_count")))
    elif case == "sparse-id-pressure":
        expectations.append(_exact("ecs_entities_alive", _positive_int(parameters, "live_count")))
    elif case == "structural-churn":
        iterations = _positive_int(parameters, "iterations")
        churn = _positive_int(parameters, "churn_count")
        expectations.extend(
            (
                _exact("ecs_entities_alive", _positive_int(parameters, "entity_count")),
                _exact("ecs_entity_generation_reuses", iterations * churn),
            )
        )
    elif case in {"query-filter-plan", "query-join-shape"}:
        expectations.append(_exact("ecs_physical_system_runs", 1))
    elif case == "cardinality":
        expectations.append(_exact("ecs_entities_alive", 0))
    elif case == "cardinality-scale":
        expectations.append(
            _exact("ecs_entities_alive", _nonnegative_int(parameters, "match_count"))
        )
    elif case == "plan-build-compile":
        systems = _positive_int(parameters, "system_count")
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", systems),
                _exact("ecs_rust_compiled_plans", systems),
            )
        )
    elif case == "plan-shape":
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", 1),
                _exact("ecs_rust_compiled_plans", 1),
            )
        )
    elif case == "plan-system-scale":
        systems = _enum_int(parameters, "system_count", {1, 100, 1_000})
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", systems),
                _exact("ecs_rust_compiled_plans", systems),
            )
        )
    elif case == "plan-cache-release":
        frames = _positive_int(parameters, "frames")
        cycles = _positive_int(parameters, "cycles")
        runs = frames * cycles
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", cycles),
                _exact("ecs_physical_system_runs", runs),
                _exact("ecs_steady_physical_plan_reuses", runs),
                _exact("ecs_query_cache_hits", 1),
                _exact("ecs_query_cache_misses", 7),
                _exact("ecs_query_cache_refreshes", 0),
                _exact("ecs_query_cache_invalidations", 0),
                _exact("ecs_rust_compiled_plans", 0),
            )
        )
    elif case == "plan-steady-reuse":
        frames = _positive_int(parameters, "frames")
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", 1),
                _exact("ecs_physical_system_runs", frames),
                _exact("ecs_steady_physical_plan_reuses", frames),
            )
        )
    elif case == "plan-schema-invalidation":
        expectations.extend(
            (
                _exact("ecs_physical_plan_compiles", 2),
                _exact("ecs_rust_compiled_plans", 1),
            )
        )
    elif case == "plan-hostile":
        expectations.append(_exact("ecs_entities_alive", 0))
    elif case == "group-order":
        expectations.append(
            _exact("ecs_physical_system_runs", _positive_int(parameters, "frames") * 3)
        )
    elif case == "parallel-snapshot":
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", 1),
                _exact("ecs_physical_rows_scanned", _positive_int(parameters, "entity_count")),
            )
        )
    elif case == "schedule-scale":
        frames = _positive_int(parameters, "frames")
        systems = _enum_int(parameters, "system_count", {8, 64, 512})
        expectations.extend(
            (
                _exact("ecs_schedule_rebuilds", systems + 1),
                _exact("ecs_system_frame_runs", frames),
                _exact("ecs_physical_plan_compiles", systems),
                _exact("ecs_physical_system_runs", frames * systems),
                _exact("ecs_rust_compiled_plans", systems),
            )
        )
    elif case == "simulated-multisystem":
        runs = _positive_int(parameters, "frames") * _positive_int(parameters, "system_count")
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", runs),
                _exact(
                    "ecs_physical_rows_scanned",
                    runs * _positive_int(parameters, "entity_count"),
                ),
            )
        )
    elif case == "change-structural":
        expectations.extend(
            (_exact("ecs_physical_system_runs", 2), _minimum("ecs_structural_commands_applied", 1))
        )
    elif case == "structural-shape":
        count = _positive_int(parameters, "entity_count")
        percent = _enum_int(parameters, "mutation_percent", {1, 10, 100})
        selected = max(1, count * percent // 100)
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", 1),
                _exact("ecs_staged_commands_applied", 0),
                _minimum("ecs_structural_commands_applied", selected),
            )
        )
    elif case == "resources-events":
        count = _positive_int(parameters, "event_count")
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", 1),
                _exact("ecs_events_emitted", count),
                _exact("ecs_event_records_read", count * 2),
            )
        )
    elif case == "event-volume":
        count = _nonnegative_int(parameters, "event_count")
        readers = _enum_int(parameters, "reader_count", {1, 2, 4})
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", readers),
                _exact("ecs_events_emitted", count),
                _exact("ecs_event_records_read", count * (readers + 1)),
                _exact("ecs_event_records_total", 0),
                _exact("ecs_python_event_mirror_entries", 0),
            )
        )
    elif case == "python-system-udf":
        count = _positive_int(parameters, "entity_count")
        expectations.extend(
            (
                _exact("ecs_python_system_calls", 1),
                _exact("ecs_python_system_entities_materialized", count),
                _exact("ecs_udf_calls", 1),
                _exact("ecs_rust_compiled_plans", 0),
            )
        )
    elif case == "udf-plan":
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", 1),
                _exact("ecs_physical_rows_scanned", _positive_int(parameters, "entity_count")),
            )
        )
    elif case.startswith("spatial-") and case != "spatial-distribution":
        frames = _positive_int(parameters, "frames")
        algorithm_counter = {
            "spatial-hash-grid": "ecs_spatial_algorithm_hash_grid",
            "spatial-quadtree": "ecs_spatial_algorithm_quadtree",
            "spatial-octree": "ecs_spatial_algorithm_octree",
            "spatial-hilbert": "ecs_spatial_algorithm_hilbert_curve",
        }[case]
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", frames * 2),
                _exact(algorithm_counter, frames),
                _exact("ecs_spatial_indexes_built", frames),
                _exact("ecs_spatial_index_full_rebuilds", frames),
                _exact("ecs_spatial_index_incremental_updates", 0),
                _minimum("ecs_spatial_candidate_rows", 1),
                _minimum("ecs_spatial_exact_rows", 1),
            )
        )
        for other in (
            "ecs_spatial_algorithm_hash_grid",
            "ecs_spatial_algorithm_quadtree",
            "ecs_spatial_algorithm_octree",
            "ecs_spatial_algorithm_hilbert_curve",
        ):
            if other != algorithm_counter:
                expectations.append(_exact(other, 0))
    elif case == "spatial-distribution":
        frames = _positive_int(parameters, "frames")
        systems = _enum_int(parameters, "sharing_systems", {1, 4, 8})
        algorithm = _enum_string(
            parameters, "algorithm", {"hash-grid", "hilbert", "octree", "quadtree"}
        )
        algorithm_counter = {
            "hash-grid": "ecs_spatial_algorithm_hash_grid",
            "hilbert": "ecs_spatial_algorithm_hilbert_curve",
            "octree": "ecs_spatial_algorithm_octree",
            "quadtree": "ecs_spatial_algorithm_quadtree",
        }[algorithm]
        movement = _enum_int(parameters, "movement_percent", {0, 1, 10, 100})
        incremental = algorithm == "hash-grid" and movement > 0
        rebuilds = 1 if movement == 0 or incremental else frames
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", frames * systems),
                _exact(algorithm_counter, frames * systems),
                _exact("ecs_spatial_indexes_built", rebuilds),
                _exact("ecs_spatial_index_full_rebuilds", rebuilds),
                _exact("ecs_spatial_index_incremental_updates", frames - 1 if incremental else 0),
                _minimum("ecs_spatial_index_reuses", frames * max(0, systems - 1)),
            )
        )
    elif case in {"compact-fill", "hidpi-fill", "simulation-render"}:
        frames = _positive_int(parameters, "frames")
        count = _positive_int(parameters, "entity_count")
        systems = 2 if case == "simulation-render" else 1
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", frames * systems),
                _exact("ecs_canvas_commands", frames * 2),
                _exact("ecs_canvas_direct_fill_primitives", count * frames),
                _exact("ecs_python_system_calls", frames),
                _exact("ecs_python_system_entities_materialized", 0),
            )
        )
    elif case == "diagnostics-reset":
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", 1),
                _exact("ecs_query_cache_hits", 1),
                _exact("ecs_query_cache_misses", 6),
                _exact("ecs_query_cache_refreshes", 0),
                _exact("ecs_query_cache_invalidations", 0),
                _exact("ecs_rust_compiled_plans", 1),
            )
        )
    elif case == "diagnostics-volume":
        snapshots = _positive_int(parameters, "snapshots")
        reset_every = _positive_int(parameters, "reset_every")
        final_runs = (snapshots - 1) % reset_every + 1
        expectations.extend(
            (
                _exact("ecs_physical_system_runs", final_runs),
                _exact("ecs_rust_compiled_plans", 1),
                _exact("ecs_diagnostic_messages_dropped", 0),
            )
        )
    elif case == "failure-contracts":
        expectations.extend(
            (
                _exact("ecs_strict_mode_errors", 1),
                _minimum("ecs_physical_duplicate_writes", 1),
            )
        )
    elif case == "bounded-longevity":
        frames = _positive_int(parameters, "frames")
        expectations.extend(
            (
                _exact("ecs_entities_alive", _positive_int(parameters, "entity_count")),
                _exact("ecs_physical_system_runs", frames),
                _exact("ecs_events_emitted", frames),
                _exact("ecs_rust_compiled_plans", 1),
            )
        )
    else:  # pragma: no cover - build_workload owns the closed case set
        raise EcsWorkloadError(f"no path assertion contract for ECS case {case!r}")
    assert_path_counters(diagnostics, expectations)


_HANDLERS: Mapping[str, Callable[[WorkloadPlan], _Outcome]] = {
    "schema-storage": _schema_storage,
    "schema-registration": _schema_registration,
    "storage-semantics": _storage_semantics,
    "spawn-archetypes": _spawn_archetypes,
    "spawn-shape": _spawn_shape,
    "structural-churn": _structural_churn,
    "sparse-id-pressure": _sparse_id_pressure,
    "query-order": _query_order,
    "query-selectivity": _query_selectivity,
    "query-filter-plan": _query_filter_plan,
    "query-join-shape": _query_join_shape,
    "batch-transport": _batch_transport,
    "transport-family": _transport_family,
    "cardinality": _cardinality,
    "cardinality-scale": _cardinality_scale,
    "plan-build-compile": _plan_build_compile,
    "plan-shape": _plan_shape,
    "plan-system-scale": _plan_system_scale,
    "plan-cache-release": _plan_cache_release,
    "plan-steady-reuse": _plan_steady_reuse,
    "plan-schema-invalidation": _plan_schema_invalidation,
    "plan-hostile": _plan_hostile,
    "group-order": _group_order,
    "parallel-snapshot": _parallel_snapshot,
    "schedule-scale": _schedule_scale,
    "simulated-multisystem": _simulated_multisystem,
    "change-structural": _change_structural,
    "structural-shape": _structural_shape,
    "resources-events": _resources_events,
    "event-volume": _event_volume,
    "python-system-udf": _python_system_udf,
    "udf-plan": _udf_plan,
    "spatial-hash-grid": _spatial,
    "spatial-quadtree": _spatial,
    "spatial-octree": _spatial,
    "spatial-hilbert": _spatial,
    "spatial-distribution": _spatial_distribution,
    "compact-fill": _integrated,
    "hidpi-fill": _integrated,
    "simulation-render": _integrated,
    "diagnostics-reset": _diagnostics_reset,
    "diagnostics-volume": _diagnostics_volume,
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
    _assert_runtime_path(plan, outcome.diagnostics)
    summary = {
        **dict(outcome.summary),
        "work_units": outcome.actual_work_units,
        "case_kind": plan.case_kind,
        "execution_route": plan.execution_class.value,
        "runtime_path": list(_PATH_PROFILE_PATHS[plan.path_profile]),
        "path_profile": plan.path_profile,
        "metric_profile": plan.metric_profile,
        "oracle_profile": plan.oracle_profile,
        "release_provenance_profile": _RELEASE_PROVENANCE_PROFILE,
        "measured_parameters": {
            name: value for name, value in plan.parameters.items() if name not in _COMMON_PARAMETERS
        },
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
