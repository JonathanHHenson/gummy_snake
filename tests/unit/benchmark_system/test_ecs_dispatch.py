from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from benchmarks.governance import ExecutionClass
from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.ecs.workloads import (
    EcsOracleError,
    EcsWorkloadError,
    ExecutionRouteError,
    build_workload,
)
from benchmarks.suites.registry import SuiteExecution, dispatch

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"


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
        digest = result.summary["correctness_digest"]
        assert isinstance(digest, str) and digest.startswith("sha256:") and len(digest) == 71
        diagnostics = result.diagnostics["ecs"]
        assert isinstance(diagnostics, Mapping)
        required = workload.parameters["required_counters"]
        assert isinstance(required, list)
        assert set(required) <= set(diagnostics)
        if workload.id == "integrated-headless-frame":
            assert isinstance(result.diagnostics["renderer"], Mapping)


def test_representative_correctness_digests_are_repeatable() -> None:
    catalog = load_catalog(CATALOG_PATH)
    selected = {
        "structural-generation-churn-96x4",
        "octree-incremental-96x3",
        "simulation-render-128x4",
        "bounded-longevity-48x32",
    }

    for workload in catalog.workloads:
        if workload.case_id not in selected:
            continue
        first = dispatch("ecs", workload.id, workload.parameters, workload.execution_class)
        second = dispatch("ecs", workload.id, workload.parameters, workload.execution_class)
        assert first.summary["correctness_digest"] == second.summary["correctness_digest"]
        assert first.summary["work_units"] == second.summary["work_units"]


def test_ecs_builder_rejects_unknown_routes_cases_and_parameters() -> None:
    base = {
        "case_kind": "cardinality",
        "work_units": 3,
        "required_counters": ["ecs_entities_alive"],
    }

    with pytest.raises(EcsWorkloadError, match="unknown ECS workload"):
        build_workload("missing", base, ExecutionClass.HEADLESS)
    with pytest.raises(EcsWorkloadError, match="case_kind"):
        build_workload("query-view-transport", {**base, "case_kind": "unknown"}, "headless")
    with pytest.raises(EcsWorkloadError, match="unexecuted or unsupported"):
        build_workload("query-view-transport", {**base, "unused": 1}, "headless")
    with pytest.raises(ExecutionRouteError, match="requires execution_class='headless'"):
        build_workload("query-view-transport", base, ExecutionClass.SIMULATED_REALTIME)
    with pytest.raises(ExecutionRouteError, match="requires execution_class='headless'"):
        build_workload(
            "scheduler-executor",
            {
                "case_kind": "simulated-multisystem",
                "entity_count": 4,
                "frames": 2,
                "system_count": 2,
                "work_units": 16,
                "required_counters": ["ecs_physical_system_runs"],
            },
            ExecutionClass.SIMULATED_REALTIME,
        )


def test_dispatch_rejects_declared_work_that_does_not_match_completed_work() -> None:
    with pytest.raises(EcsOracleError, match="declared work_units=4"):
        dispatch(
            "ecs",
            "query-view-transport",
            {
                "case_kind": "cardinality",
                "work_units": 4,
                "required_counters": ["ecs_entities_alive"],
            },
            ExecutionClass.HEADLESS,
        )
