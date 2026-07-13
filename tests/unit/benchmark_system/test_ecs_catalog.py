from __future__ import annotations

import ast
from pathlib import Path

from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.ecs.fixtures import FIXTURE_MANIFEST, fixture_digest

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"

EXECUTION_LAYER_CAPABILITIES = {
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

EXPECTED_CASES = {
    ("storage-entity-archetype", "schema-storage-families", "headless", "micro"),
    ("storage-entity-archetype", "spawn-mixed-archetypes-128", "headless", "bulk-headless"),
    (
        "storage-entity-archetype",
        "structural-generation-churn-96x4",
        "headless",
        "bulk-headless",
    ),
    ("query-view-transport", "ordered-filtered-views-192", "headless", "bulk-headless"),
    (
        "query-view-transport",
        "batch-four-field-transport-256",
        "headless",
        "bulk-headless",
    ),
    ("query-view-transport", "cardinality-zero-one-many", "headless", "micro"),
    ("plan-compile-cache", "logical-build-compile-eight", "headless", "micro"),
    ("plan-compile-cache", "cache-reuse-release-four-by-four", "headless", "micro"),
    ("scheduler-executor", "ordered-groups-eight-frames", "headless", "bulk-headless"),
    ("scheduler-executor", "parallel-snapshot-128x2", "headless", "bulk-headless"),
    (
        "scheduler-executor",
        "simulated-four-system-eight-frame",
        "headless",
        "simulated-realtime",
    ),
    (
        "mutation-boundaries",
        "changed-filter-structural-remove-96",
        "headless",
        "bulk-headless",
    ),
    (
        "mutation-boundaries",
        "resource-event-reduction-128",
        "headless",
        "bulk-headless",
    ),
    (
        "mutation-boundaries",
        "explicit-python-system-udf-128",
        "headless",
        "bulk-headless",
    ),
    ("mutation-boundaries", "udf-plan-inline-128", "headless", "bulk-headless"),
    ("spatial-algorithms", "hash-grid-auto-96x3", "headless", "bulk-headless"),
    (
        "spatial-algorithms",
        "quadtree-rebuild-frame-96x3",
        "headless",
        "bulk-headless",
    ),
    ("spatial-algorithms", "octree-incremental-96x3", "headless", "bulk-headless"),
    (
        "spatial-algorithms",
        "hilbert-rebuild-use-96x3",
        "headless",
        "bulk-headless",
    ),
    (
        "integrated-headless-frame",
        "compact-fill-64x3",
        "headless",
        "frame-headless",
    ),
    (
        "integrated-headless-frame",
        "simulation-render-128x4",
        "headless",
        "frame-headless",
    ),
    (
        "diagnostics-failures-longevity",
        "diagnostics-snapshot-reset",
        "headless",
        "micro",
    ),
    (
        "diagnostics-failures-longevity",
        "stale-strict-spatial-failures",
        "headless",
        "micro",
    ),
    (
        "diagnostics-failures-longevity",
        "bounded-longevity-48x32",
        "headless",
        "simulated-realtime",
    ),
}


def test_ecs_catalog_freezes_exact_cases_routes_profiles_and_work() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert catalog.suite("ecs", 1) == catalog.workloads
    assert len(catalog.workloads) == 24
    assert {
        (
            workload.id,
            workload.case_id,
            workload.execution_class.value,
            workload.sampling_profile,
        )
        for workload in catalog.workloads
    } == EXPECTED_CASES
    assert {workload.sampling_profile for workload in catalog.workloads} == {
        "micro",
        "bulk-headless",
        "frame-headless",
        "simulated-realtime",
    }
    assert {workload.execution_class.value for workload in catalog.workloads} == {"headless"}
    assert {workload.parameters["execution_layer"] for workload in catalog.workloads} == {"H"}
    assert {workload.version for workload in catalog.workloads} == {2}
    assert {
        layer
        for layer, capability in EXECUTION_LAYER_CAPABILITIES.items()
        if capability["available"]
    } == {"H"}
    for workload in catalog.workloads:
        assert workload.parameters["execution_layer_capabilities"] == EXECUTION_LAYER_CAPABILITIES
        execution_layer = workload.parameters["execution_layer"]
        assert isinstance(execution_layer, str)
        assert EXECUTION_LAYER_CAPABILITIES[execution_layer]["available"]
        assert isinstance(workload.parameters["expected_correctness_digest"], str)
        assert workload.parameters["expected_correctness_digest"].startswith("sha256:")
        assert len(workload.parameters["expected_correctness_digest"]) == 71
        assert isinstance(workload.parameters["work_units"], int)
        assert workload.parameters["work_units"] > 0
        assert workload.primary_metric.work_unit
        assert workload.parameters["required_counters"]
        assert not any(name.endswith("_matrix") for name in workload.parameters)
        assert all(source.startswith("suites/ecs/") for source in workload.source_files)
        assert workload.definition_digest.startswith("sha256:")
    catalog.audit_definitions()


def test_ecs_fixture_manifest_is_exact_and_generated_without_external_inputs() -> None:
    assert FIXTURE_MANIFEST == {
        3: "sha256:91471fe22e265c95ae3259eec579e2088b3bb17d1daf1dd3e8d13ab0e5aba379",
        32: "sha256:a912b5fa16563a3804a1783bd2275601550028e2059363ce6add1c5c82d7a45c",
        48: "sha256:a69cf1cf0cd61be8115ef2f5acd58922fcc1fc2c38193dae25dda96b16bd6bb0",
        64: "sha256:d58a22733fb1183815687e5c95011e2deaeefbb8ac4174e4dcd57e676060d7b9",
        96: "sha256:f180fafb669358a6c1bab4c34e2f57278aba12bd51604e8046f390c4cfc16a35",
        128: "sha256:48ac7fee99fae6affe7ed4a06833741349c9f324097e175572f4239a325df253",
        192: "sha256:f9e6755937c365fc61ab7a5006ed0bd2755945ebf1d911e1dac38f74847743b0",
        256: "sha256:59a7e8f4dc8ba96b91d52662fc30848cc9b08c6879a321aebec9a302c767ba19",
    }
    assert {count: fixture_digest(count) for count in FIXTURE_MANIFEST} == FIXTURE_MANIFEST


def test_ecs_package_init_is_documentation_only_not_a_barrel() -> None:
    path = ROOT / "benchmarks" / "suites" / "ecs" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    assert ast.get_docstring(tree)
    assert not any(isinstance(node, ast.Import | ast.ImportFrom) for node in ast.walk(tree))
