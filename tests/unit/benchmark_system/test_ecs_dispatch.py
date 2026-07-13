from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from benchmarks.governance import ExecutionClass
from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.ecs.oracles import (
    CounterExpectation,
    assert_path_counters,
    world_state_digest,
)
from benchmarks.suites.ecs.workloads import (
    EcsOracleError,
    EcsWorkloadError,
    ExecutionRouteError,
    build_workload,
)
from benchmarks.suites.registry import SuiteExecution, dispatch

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"
_CARDINALITY_DIGEST = "sha256:9ef0055cfd09ac889e760622f93280c8648d0ee5e1d940c42a11cf539ed053c5"
_SIMULATED_MULTISYSTEM_DIGEST = (
    "sha256:01281fb751ddcb36153a344aa40acd35f898fc4acb5a9924b56ea27da8670c17"
)
_LAYER_CAPABILITIES = {
    "R": {
        "available": False,
        "detail": "Direct release gummy_ecs Rust harness is not implemented in this catalog.",
    },
    "P": {
        "available": False,
        "detail": "Public Python/PyO3 bridge route is not implemented in this catalog.",
    },
    "H": {
        "available": True,
        "detail": "Bounded headless sketch lifecycle is implemented and required by this case.",
    },
    "I": {
        "available": False,
        "detail": "Native interactive SDL3 presentation route is not implemented in this catalog.",
    },
}


def test_every_ecs_catalog_case_dispatches_through_the_static_registry() -> None:
    catalog = load_catalog(CATALOG_PATH)

    for workload in catalog.workloads:
        result = dispatch(
            workload.suite_id,
            workload.id,
            workload.parameters,
            workload.execution_class,
        )
        assert isinstance(result, SuiteExecution)
        assert result.summary["case_kind"] == workload.parameters["case_kind"]
        assert result.summary["work_units"] == workload.parameters["work_units"]
        assert result.summary["execution_route"] == workload.execution_class.value
        assert result.summary["execution_layer"] == workload.parameters["execution_layer"]
        digest = result.summary["correctness_digest"]
        assert digest == workload.parameters["expected_correctness_digest"]
        diagnostics = result.diagnostics["ecs"]
        assert isinstance(diagnostics, Mapping)
        required = workload.parameters["required_counters"]
        assert isinstance(required, list)
        assert set(required) <= set(diagnostics)
        if workload.id == "integrated-headless-frame":
            assert isinstance(result.diagnostics["renderer"], Mapping)


def test_every_headless_correctness_digest_is_repeatable() -> None:
    catalog = load_catalog(CATALOG_PATH)
    for workload in catalog.workloads:
        first = dispatch("ecs", workload.id, workload.parameters, workload.execution_class)
        second = dispatch("ecs", workload.id, workload.parameters, workload.execution_class)
        expected_digest = workload.parameters["expected_correctness_digest"]
        assert first.summary["correctness_digest"] == expected_digest
        assert second.summary["correctness_digest"] == expected_digest
        assert first.summary["execution_layer"] == second.summary["execution_layer"]
        assert first.summary["work_units"] == second.summary["work_units"]


def test_ecs_builder_rejects_unknown_routes_cases_and_parameters() -> None:
    base = {
        "case_kind": "cardinality",
        "execution_layer": "H",
        "execution_layer_capabilities": _LAYER_CAPABILITIES,
        "expected_correctness_digest": _CARDINALITY_DIGEST,
        "work_units": 3,
        "required_counters": ["ecs_entities_alive"],
    }

    with pytest.raises(EcsWorkloadError, match="unknown ECS workload"):
        build_workload("missing", base, ExecutionClass.HEADLESS)
    with pytest.raises(EcsWorkloadError, match="case_kind"):
        build_workload("query-view-transport", {**base, "case_kind": "unknown"}, "headless")
    with pytest.raises(EcsWorkloadError, match="unexecuted or unsupported"):
        build_workload("query-view-transport", {**base, "unused": 1}, "headless")
    with pytest.raises(EcsWorkloadError, match="declare exactly R, P, H, and I"):
        build_workload(
            "query-view-transport",
            {**base, "execution_layer_capabilities": {"H": _LAYER_CAPABILITIES["H"]}},
            "headless",
        )
    with pytest.raises(ExecutionRouteError, match="unknown execution_layer"):
        build_workload("query-view-transport", {**base, "execution_layer": "unknown"}, "headless")
    with pytest.raises(ExecutionRouteError, match="requires execution_class='headless'"):
        build_workload("query-view-transport", base, ExecutionClass.SIMULATED_REALTIME)
    with pytest.raises(ExecutionRouteError, match="declared unavailable") as error:
        build_workload("query-view-transport", {**base, "execution_layer": "R"}, "trial")
    assert "Direct release gummy_ecs Rust harness" in str(error.value)
    assert "No fallback route is available" in str(error.value)
    with pytest.raises(EcsWorkloadError, match="expected_correctness_digest"):
        build_workload(
            "query-view-transport", {**base, "expected_correctness_digest": "bad"}, "headless"
        )
    with pytest.raises(ExecutionRouteError, match="requires execution_class='headless'"):
        build_workload(
            "scheduler-executor",
            {
                "case_kind": "simulated-multisystem",
                "execution_layer": "H",
                "execution_layer_capabilities": _LAYER_CAPABILITIES,
                "expected_correctness_digest": _SIMULATED_MULTISYSTEM_DIGEST,
                "entity_count": 4,
                "frames": 2,
                "system_count": 2,
                "work_units": 16,
                "required_counters": ["ecs_physical_system_runs"],
            },
            ExecutionClass.SIMULATED_REALTIME,
        )


@pytest.mark.parametrize(
    ("layer", "route", "detail"),
    (
        ("R", ExecutionClass.TRIAL, "Direct release gummy_ecs Rust harness"),
        ("I", ExecutionClass.NATIVE_INTERACTIVE, "Native interactive SDL3 presentation route"),
    ),
)
def test_ecs_builder_fails_closed_for_each_unavailable_execution_layer(
    layer: str, route: ExecutionClass, detail: str
) -> None:
    parameters = {
        "case_kind": "cardinality",
        "execution_layer": layer,
        "execution_layer_capabilities": _LAYER_CAPABILITIES,
        "expected_correctness_digest": _CARDINALITY_DIGEST,
        "work_units": 3,
        "required_counters": ["ecs_entities_alive"],
    }

    with pytest.raises(ExecutionRouteError, match="declared unavailable") as error:
        build_workload("query-view-transport", parameters, route)

    assert detail in str(error.value)
    assert "No fallback route is available" in str(error.value)


def test_ecs_path_and_world_digest_oracles_are_explicit_and_fail_closed() -> None:
    diagnostics = {
        "ecs_entities_alive": 2,
        "ecs_rust_entities_alive": 2,
        "ecs_rust_structural_revision": 4,
        "ecs_rust_field_revision": 7,
        "ecs_change_journal_updates": 3,
    }

    assert_path_counters(
        diagnostics,
        (
            CounterExpectation("ecs_change_journal_updates", minimum=3),
            CounterExpectation("ecs_rust_entities_alive", exact=2),
        ),
    )
    with pytest.raises(EcsOracleError, match="expected exactly 0"):
        assert_path_counters(
            diagnostics, (CounterExpectation("ecs_change_journal_updates", exact=0),)
        )

    class _World:
        def diagnostics(self) -> dict[str, object]:
            return diagnostics

    first = world_state_digest(_World(), {"entities": ((0, 1), (1, 2)), "events": ()})
    second = world_state_digest(_World(), {"events": (), "entities": ((0, 1), (1, 2))})
    assert first.digest() == second.digest()
    assert first.alive_entities == 2
    assert first.structural_revision == 4


def test_dispatch_rejects_declared_work_that_does_not_match_completed_work() -> None:
    with pytest.raises(EcsOracleError, match="declared work_units=4"):
        dispatch(
            "ecs",
            "query-view-transport",
            {
                "case_kind": "cardinality",
                "execution_layer": "H",
                "execution_layer_capabilities": _LAYER_CAPABILITIES,
                "expected_correctness_digest": _CARDINALITY_DIGEST,
                "work_units": 4,
                "required_counters": ["ecs_entities_alive"],
            },
            ExecutionClass.HEADLESS,
        )

    with pytest.raises(EcsOracleError, match="correctness digest mismatch"):
        dispatch(
            "ecs",
            "query-view-transport",
            {
                "case_kind": "cardinality",
                "execution_layer": "H",
                "execution_layer_capabilities": _LAYER_CAPABILITIES,
                "expected_correctness_digest": "sha256:" + "0" * 64,
                "work_units": 3,
                "required_counters": ["ecs_entities_alive"],
            },
            ExecutionClass.HEADLESS,
        )
