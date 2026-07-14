from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from benchmarks.governance import ExecutionClass
from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.ecs.oracles import (
    CounterExpectation,
    EcsOracleError,
    PixelRule,
    ReleaseProvenanceContract,
    assert_path_counters,
    assert_pixels,
    frame_digest,
    world_state_digest,
)
from benchmarks.suites.ecs.workloads import (
    EcsWorkloadError,
    ExecutionRouteError,
    build_workload,
)
from benchmarks.suites.registry import SuiteExecution, dispatch

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"
_CARDINALITY_DIGEST = "sha256:32464902926e6826a572e97f2753334c20fa44d9c2cb3703edad48cbd0188bce"
_SIMULATED_MULTISYSTEM_DIGEST = (
    "sha256:dea818018bd0613eadec4f22929e6257d45e5ca3a19e9899c300f869d66292fc"
)
_CATALOG_CONTRACT = {
    "fixture_seed": 290_001,
    "path_profile": "public-bridge-storage",
    "metric_profile": "ecs-core",
    "oracle_profile": "full-world-v1",
    "release_provenance_profile": "isolated-release-wheel-v1",
}
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
_COMMON_PARAMETER_NAMES = {
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
_EXPECTED_PATHS = {
    "public-bridge-storage": ["public-python-api", "pyo3-canvas-ecs-bridge", "rust-ecs"],
    "public-bridge-plan": [
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
    ],
    "public-bridge-python-boundary": [
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs",
        "explicit-python-system-udf-boundary",
    ],
    "public-bridge-spatial": [
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
        "rust-spatial-index",
    ],
    "bounded-headless-frame": [
        "bounded-headless-sketch",
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-physical-plan",
        "rust-canvas-offscreen",
        "public-pixel-readback",
    ],
    "public-bridge-failure": [
        "public-python-api",
        "pyo3-canvas-ecs-bridge",
        "rust-ecs-fail-closed",
    ],
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
        assert result.summary["path_profile"] == workload.parameters["path_profile"]
        assert result.summary["metric_profile"] == workload.parameters["metric_profile"]
        assert result.summary["oracle_profile"] == workload.parameters["oracle_profile"]
        assert (
            result.summary["runtime_path"]
            == _EXPECTED_PATHS[str(workload.parameters["path_profile"])]
        )
        assert result.summary["measured_parameters"] == {
            name: value
            for name, value in workload.parameters.items()
            if name not in _COMMON_PARAMETER_NAMES
        }

        digest = result.summary["correctness_digest"]
        assert digest == workload.parameters["expected_correctness_digest"]
        diagnostics = result.diagnostics["ecs"]
        assert isinstance(diagnostics, Mapping)
        required = workload.parameters["required_counters"]
        assert isinstance(required, list)
        assert set(required) <= set(diagnostics)
        if workload.id == "integrated-headless-frame":
            assert isinstance(result.diagnostics["renderer"], Mapping)
            assert str(result.summary["frame_digest"]).startswith("sha256:")
            assert str(result.summary["pixel_digest"]).startswith("sha256:")


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


def test_plan_cache_release_keeps_query_cache_world_owned_and_releases_every_plan() -> None:
    catalog = load_catalog(CATALOG_PATH)
    workload = next(
        item for item in catalog.workloads if item.parameters["case_kind"] == "plan-cache-release"
    )

    result = dispatch("ecs", workload.id, workload.parameters, workload.execution_class)

    diagnostics = result.diagnostics["ecs"]
    assert isinstance(diagnostics, Mapping)
    assert diagnostics["ecs_physical_plan_compiles"] == 4
    assert diagnostics["ecs_physical_system_runs"] == 16
    assert diagnostics["ecs_steady_physical_plan_reuses"] == 16
    assert diagnostics["ecs_query_cache_hits"] == 20
    assert diagnostics["ecs_query_cache_misses"] == 7
    assert diagnostics["ecs_query_cache_refreshes"] == 0
    assert diagnostics["ecs_query_cache_invalidations"] == 0
    assert diagnostics["ecs_rust_compiled_plans"] == 0


def test_remaining_epic_290_cases_freeze_scheduler_spatial_hidpi_and_lifecycle_paths() -> None:
    catalog = load_catalog(CATALOG_PATH)
    by_case = {workload.case_id: workload for workload in catalog.workloads}

    schedule = dispatch(
        "ecs",
        by_case["schedule-s64-g8-e16-f2"].id,
        by_case["schedule-s64-g8-e16-f2"].parameters,
        by_case["schedule-s64-g8-e16-f2"].execution_class,
    )
    schedule_diagnostics = schedule.diagnostics["ecs"]
    assert isinstance(schedule_diagnostics, Mapping)
    assert schedule_diagnostics["ecs_schedule_rebuilds"] == 65
    assert schedule_diagnostics["ecs_physical_system_runs"] == 128

    structural = dispatch(
        "ecs",
        by_case["structural-despawn-128-p10"].id,
        by_case["structural-despawn-128-p10"].parameters,
        by_case["structural-despawn-128-p10"].execution_class,
    )
    structural_diagnostics = structural.diagnostics["ecs"]
    assert isinstance(structural_diagnostics, Mapping)
    assert structural_diagnostics["ecs_entities_alive"] == 116
    assert structural_diagnostics["ecs_staged_commands_applied"] == 0

    spatial = dispatch(
        "ecs",
        by_case["spatial-hash-grid-2d-clustered-n128-m10-s4"].id,
        by_case["spatial-hash-grid-2d-clustered-n128-m10-s4"].parameters,
        by_case["spatial-hash-grid-2d-clustered-n128-m10-s4"].execution_class,
    )
    spatial_diagnostics = spatial.diagnostics["ecs"]
    assert isinstance(spatial_diagnostics, Mapping)
    assert spatial_diagnostics["ecs_spatial_indexes_built"] == 1
    assert spatial_diagnostics["ecs_spatial_index_incremental_updates"] == 1
    workers = spatial_diagnostics["ecs_spatial_parallel_workers"]
    assert isinstance(workers, int) and workers >= 1

    hidpi = dispatch(
        "ecs",
        by_case["hidpi-fill-256x3-d2"].id,
        by_case["hidpi-fill-256x3-d2"].parameters,
        by_case["hidpi-fill-256x3-d2"].execution_class,
    )
    assert hidpi.summary["logical_size"] == (160, 120)
    assert hidpi.summary["physical_size"] == (320, 240)
    assert hidpi.summary["pixel_bytes"] == 320 * 240 * 4


def test_integrated_interactive_identity_fails_closed_without_a_qualified_route() -> None:
    catalog = load_catalog(CATALOG_PATH)
    workload = next(item for item in catalog.workloads if item.case_id == "compact-fill-1000x3")
    parameters = dict(workload.parameters)
    parameters["execution_layer"] = "I"

    with pytest.raises(ExecutionRouteError, match="declared unavailable") as error:
        build_workload(workload.id, parameters, ExecutionClass.NATIVE_INTERACTIVE)

    assert "Native interactive SDL3 presentation route" in str(error.value)
    assert "No fallback route is available" in str(error.value)


def test_ecs_builder_rejects_unknown_routes_cases_and_parameters() -> None:
    base = {
        **_CATALOG_CONTRACT,
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
        build_workload("query-view-transport", {**base, "execution_layer": "R"}, "headless")
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
                **_CATALOG_CONTRACT,
                "case_kind": "simulated-multisystem",
                "path_profile": "public-bridge-plan",
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
        ("R", ExecutionClass.HEADLESS, "Direct release gummy_ecs Rust harness"),
        ("I", ExecutionClass.NATIVE_INTERACTIVE, "Native interactive SDL3 presentation route"),
    ),
)
def test_ecs_builder_fails_closed_for_each_unavailable_execution_layer(
    layer: str, route: ExecutionClass, detail: str
) -> None:
    parameters = {
        **_CATALOG_CONTRACT,
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
        def iter_entities(self, *components: object, tags: object = ()) -> tuple[object, ...]:
            del components, tags
            return ()

        def diagnostics(self) -> Mapping[str, object]:
            return diagnostics

    first = world_state_digest(_World(), {"entities": ((0, 1), (1, 2)), "events": ()})
    second = world_state_digest(_World(), {"events": (), "entities": ((0, 1), (1, 2))})
    assert first.digest() == second.digest()
    assert first.alive_entities == 2
    assert first.structural_revision == 4
    assert first.change_epoch is None


def test_ecs_frame_oracles_support_explicit_exact_and_tolerant_rules() -> None:
    expected = bytes((10, 20, 30, 255))
    close = bytes((11, 20, 29, 255))

    exact = frame_digest(expected, 1, 1)
    assert exact.pixel_bytes == 4
    assert exact.pixel_sha256.startswith("sha256:")
    assert_pixels(expected, expected)
    assert_pixels(close, expected, PixelRule(max_channel_delta=1, max_different_channels=2))
    with pytest.raises(EcsOracleError, match="pixel rule mismatch"):
        assert_pixels(close, expected)
    with pytest.raises(EcsOracleError, match="expected 8 RGBA bytes"):
        frame_digest(expected, 2, 1)


def test_ecs_release_provenance_is_mandatory_for_local_records() -> None:
    valid = {
        "source_commit": "a" * 40,
        "source_digest": "sha256:" + "b" * 64,
        "tree_digest": "sha256:" + "c" * 64,
        "profile": "release",
        "features": ["extension-module"],
        "canvas_crate_version": "0.1.0",
        "ecs_crate_version": "0.1.0",
    }
    contract = ReleaseProvenanceContract()
    assert contract.validate(valid)["profile"] == "release"

    with pytest.raises(EcsOracleError, match="hexadecimal source commit"):
        contract.validate({**valid, "source_commit": "unrecorded"})
    with pytest.raises(EcsOracleError, match="profile='release'"):
        contract.validate({**valid, "profile": "debug"})
    with pytest.raises(EcsOracleError, match="missing feature"):
        contract.validate({**valid, "features": []})


def test_dispatch_rejects_declared_work_that_does_not_match_completed_work() -> None:
    with pytest.raises(EcsOracleError, match="declared work_units=4"):
        dispatch(
            "ecs",
            "query-view-transport",
            {
                **_CATALOG_CONTRACT,
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
                **_CATALOG_CONTRACT,
                "case_kind": "cardinality",
                "execution_layer": "H",
                "execution_layer_capabilities": _LAYER_CAPABILITIES,
                "expected_correctness_digest": "sha256:" + "0" * 64,
                "work_units": 3,
                "required_counters": ["ecs_entities_alive"],
            },
            ExecutionClass.HEADLESS,
        )
