from __future__ import annotations

import ast
from pathlib import Path

from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.ecs.fixtures import FIXTURE_MANIFEST, fixture_digest, spatial_points
from benchmarks.suites.ecs.workloads import ECS_METRIC_REQUIREMENTS, FIXTURE_SEED

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "benchmarks" / "ecs_v1.toml"

_UNIMPLEMENTED_LAYERS = frozenset({"R", "I"})


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
EXPECTED_CASES |= {
    ("storage-entity-archetype", case, "headless", "micro")
    for case in (
        "schema-registration-1x1",
        "schema-registration-16x4",
        "schema-registration-64x16",
        "schema-registration-256x16",
        "all-storage-list-0-8",
        "all-storage-list-4-8",
        "all-storage-list-32-8",
        "all-storage-list-256-8",
    )
}
EXPECTED_CASES |= {
    ("storage-entity-archetype", case, "headless", "bulk-headless")
    for case in (
        "spawn-1000-c1-f1-t0",
        "spawn-1000-c4-f4-t2",
        "spawn-1000-c8-f16-t8",
        "spawn-10000-c1-f1-t0",
        "sparse-id-10000-live-100",
    )
}
EXPECTED_CASES |= {
    ("query-view-transport", f"query-selectivity-{percent}-of-1000", "headless", "bulk-headless")
    for percent in (0, 1, 50, 100)
}
EXPECTED_CASES |= {
    ("query-view-transport", case, "headless", "bulk-headless")
    for case in (
        "transport-scalar-1f-128",
        "transport-scalar-2f-128",
        "transport-scalar-8f-128",
        "transport-scalar-16f-128",
        "transport-vector-16f-128",
        "transport-list-16f-128",
        "transport-categorical-16f-128",
        "cardinality-10000",
    )
}
EXPECTED_CASES |= {
    ("query-view-transport", case, "headless", "micro")
    for case in (
        "required-excluded-filter-100",
        "cardinality-0",
        "cardinality-1",
        "cardinality-2",
    )
}
EXPECTED_CASES |= {
    ("query-view-transport", f"join-q{queries}-s{selectivity}-400", "headless", "micro")
    for queries in (2, 3, 4)
    for selectivity in (0, 1, 50)
}
EXPECTED_CASES |= {
    ("plan-compile-cache", case, "headless", "micro")
    for case in (
        "plan-a10-d1-q1-r0",
        "plan-a100-d16-q8-r50",
        "plan-a1000-d128-q8-r90",
        "plan-a10000-d1-q1-r90",
        "plan-a10-d1-q64-r0",
        "equivalent-systems-1",
        "equivalent-systems-100",
        "steady-reuse-16",
        "schema-invalidation-two-runs",
        "hostile-plan-schema-failures",
    )
}
EXPECTED_CASES |= {
    ("scheduler-executor", case, "headless", "bulk-headless")
    for case in ("schedule-s8-g1-e16-f2", "schedule-s64-g8-e16-f2")
}
EXPECTED_CASES |= {
    ("mutation-boundaries", case, "headless", "bulk-headless")
    for case in (
        "structural-add-component-128-p10",
        "structural-remove-component-128-p10",
        "structural-add-tag-128-p10",
        "structural-remove-tag-128-p10",
        "structural-despawn-128-p10",
        "structural-remove-component-128-p100",
        "events-0-readers-1",
        "events-1000-readers-1",
        "events-10000-readers-4",
        "explicit-python-system-udf-1000",
    )
}
EXPECTED_CASES |= {
    ("spatial-algorithms", case, "headless", "bulk-headless")
    for case in (
        "spatial-hash-grid-2d-uniform-n128-m10-s1",
        "spatial-quadtree-2d-uniform-n128-m10-s1",
        "spatial-octree-3d-uniform-n128-m10-s1",
        "spatial-hilbert-2d-uniform-n128-m10-s1",
        "spatial-hash-grid-2d-clustered-n128-m0-s1",
        "spatial-hash-grid-2d-diagonal-n128-m0-s1",
        "spatial-hash-grid-2d-same-cell-n128-m0-s1",
        "spatial-hash-grid-2d-clustered-n128-m10-s4",
        "spatial-hash-grid-2d-uniform-n512-m10-s1",
    )
}
EXPECTED_CASES |= {
    ("integrated-headless-frame", case, "headless", profile)
    for case, profile in (
        ("compact-fill-1000x3", "frame-headless"),
        ("hidpi-fill-256x3-d2", "frame-headless"),
        ("simulation-render-1000x8", "frame-headless"),
        ("simulation-render-64x600", "simulated-realtime"),
    )
}
EXPECTED_CASES |= {
    ("diagnostics-failures-longevity", case, "headless", profile)
    for case, profile in (
        ("diagnostics-volume-1000x16-reset8", "micro"),
        ("bounded-longevity-256x128", "simulated-realtime"),
    )
}

MATRIX_CASE_KINDS = {
    "schema-registration",
    "storage-semantics",
    "spawn-shape",
    "sparse-id-pressure",
    "query-selectivity",
    "query-filter-plan",
    "query-join-shape",
    "transport-family",
    "cardinality-scale",
    "plan-shape",
    "plan-system-scale",
    "plan-steady-reuse",
    "plan-schema-invalidation",
    "plan-hostile",
}

EXPECTED_MATRIX_DIGESTS = {
    "sha256:b0436d233c567a3d1c1791b1b93200558d8ac4c6d58d53b1a16b13353c27190f",
    "sha256:6d5046117aee027a20b1c939312148dc7b65affe6fa63e4b8a15a47f5bf2a235",
    "sha256:6cef817eaebf6c3bd4fc3711aac3df017066398562e086c7066b0099a5879e65",
    "sha256:f95e34ed00aab71e4146471d1c428a72aa2a6c11178303bfa9b0b95eeba8734a",
    "sha256:94fc234b3779cb072f20afce71a69594a01eef946bc2e343e1714024a6a4d599",
    "sha256:647bd76147c3fab07517a1e9e6f542cc15fd64c6ca4a3a840f040d5051670967",
    "sha256:dac528238a8b0fdc93b1b2870aec4ef98b02c850705993028b898c50bc8a7fb0",
    "sha256:69dd0b6bf788a5a0996b3b161c9e98be03cafeaff4edbbf303ef09c85368a610",
    "sha256:020d0ca244d646d21bc4038e99e18ad571f605543dffa43e45efe2c0f53973d1",
    "sha256:e3eac7feef19fee5c6fbf913e13f3e555c56cdb8ccadf631b115c7704f322e0e",
    "sha256:1445e74d72262a295eec7fdc2924a009c54b014323e294c433a3e08b9f35f0c5",
    "sha256:db70ef96593964d6d787bd69ae54f605918366d67ce8ca311711bc1fe3e4bbc3",
    "sha256:80060a4c4a051035244e976b43e5c4e2e290189ed165dfeaf8a82c30a03a7cf8",
    "sha256:ede62ba038004f5a7ea66a39e05d4ee04a6f1558f7ef4a018ef96f6704c2c6ef",
    "sha256:d68b297e59be31483c22ef596b689f722fae662010cf74f6e7e0255308508087",
    "sha256:d68652a03d3fe1774d9a950e75ed53d909607dc1a1467804f2b23b1ce51c34ac",
    "sha256:e550c3d457291cbf40f68b9f7f84677496c7cba4ab59a2496806e48b6f836a32",
    "sha256:cba4ccd40ee42ca227d4627975bdfc4492168cdbfe32e62382fe1945ed96c361",
    "sha256:5b90e3e6bb97d74f60e2eaf0a8ee7af298748eccb61d7fd47919aa258b37cecf",
    "sha256:877e686cba92222c6a3a701f8421b31113c7321880f27749b5a3627f79727080",
    "sha256:3b9b9ddcf6a5b5d3df5d53123280884566ae98ac2c80240e47c2c9d171ede766",
    "sha256:92797d05e850aeb0e8c80c936169ccaaf2f0e9c58891130bb9e07376c5771184",
    "sha256:06a61f88e3e47557415db4ba634f4b68bd174a6a50bd1175b287286e2fa6a2fe",
    "sha256:e4bc86034d22b40cb7a490bce4f3562b381d8efa2ece13dca5085f66ac0c0e1d",
    "sha256:2929212973c18b40ed3a54a00676940985d27cbf8a20c0ab6abf93c7596586a4",
    "sha256:e2543186290fd77080f1cf1808ebfd0b5c5aeba46fc097a04d393f733042f478",
    "sha256:847a39360c7731940e99792c455ac798c9e9814079a75c28863fc1114a91595d",
    "sha256:c1b56dc673934f6e0bc0d6f5562aa181ac8c859568d19fb0aee684f6529c051b",
    "sha256:4740e80ef97cc2c41be5f2b5839685d6fba6dc9b306af07040b450844ccde04f",
    "sha256:c82bca9c4e9ae5bbd57057c06735c0f0736e1cad2e60587cd3b4db78d934d569",
    "sha256:8b16508c560406935fd9497ef88d8aaaffe57f3b21742b935f98745111d6dedc",
    "sha256:8225881df441ffd60393c34610c9ebc48da0a2b9e8c00b802ede2e8f74cf27ea",
    "sha256:3049e897407602277c9fc8caa1a2ae9a26e82cc7435a314c2b268d4743dc59c8",
    "sha256:8b0e719b00b6a5d34e97537a0b2a0deffbe27b1763563face8123e0473681c09",
    "sha256:741009bfb68129bead7a36ac032792649f867a7a2709eec6e77da08ce63304a8",
    "sha256:b32f4469cc43141fe109b8455f08950d08b9d2a19dfe234ebf01384d3c7b6c23",
    "sha256:200e3f0bba3bd12101b73f91e01059c5931bae945fc802971fc1e242313657cc",
    "sha256:c486aa31a8867e7b21129990d62e3d5be6075f58ded975953cb9cfe86b10e9cb",
    "sha256:1aa736a1f69976e90a6649f87f2a84d192773f5dde4440ded93967dd497e7d5e",
    "sha256:13a41216902b039c531e8eedc77792cac4b42fbae8e1cb9e6b2b6bb3e3084824",
    "sha256:e80bf4c08bb6fb95f573ad78a6cfc25e7f6629808e4a7e046a44576fe14395cb",
    "sha256:2eff2ae9a9243f27dd724df4ae4184a2b6c29edbaeb74b4bfd68be9a314f68d0",
    "sha256:68c5127320195fcd4b6cc726dfc7911ae58bac1d6a86c1d75ad0b34d98deac30",
    "sha256:df4dde1fbc282ba172a95595b4a3fc4274815ce7aa942c6770702b15eac12f60",
    "sha256:7a7d6a0c7be09e970a80d18fb16c9c3531b5de32ecd79b37c3c902cbba6c3a42",
    "sha256:8e9e8bb2476bb67b335a810fd123e943156d896eb9211e5526b31535896d1bd3",
    "sha256:05cce6b2caf03d03edde1f93cee1d9b325bd792d7aa9d2e62b9a0999318cfbeb",
    "sha256:fce74564b4e55f01ab7574be75f6c5c9c602eaf1114662e74b26a4a44ade261f",
}


def test_ecs_catalog_freezes_exact_cases_routes_profiles_and_work() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert catalog.suite("ecs", 1) == catalog.workloads
    assert len(catalog.workloads) == 99
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
    assert {workload.parameters["execution_layer"] for workload in catalog.workloads} == {"P", "H"}
    assert {workload.version for workload in catalog.workloads} == {3, 4}
    for workload in catalog.workloads:
        layer_capabilities = workload.parameters["execution_layer_capabilities"]
        assert isinstance(layer_capabilities, dict)
        assert set(layer_capabilities) == {"R", "P", "H", "I"}
        execution_layer = workload.parameters["execution_layer"]
        assert isinstance(execution_layer, str)
        assert layer_capabilities[execution_layer]["available"] is True
        assert all(
            layer_capabilities[layer]["available"] is False for layer in _UNIMPLEMENTED_LAYERS
        )
        if execution_layer == "P":
            assert layer_capabilities["P"]["available"] is True
            assert layer_capabilities["H"]["available"] is False
        else:
            assert execution_layer == "H"
            assert layer_capabilities["H"]["available"] is True
            assert layer_capabilities["P"]["available"] is False
        assert workload.parameters["fixture_seed"] == FIXTURE_SEED == 290_001
        assert workload.parameters["path_profile"] in {
            "public-bridge-storage",
            "public-bridge-plan",
            "public-bridge-python-boundary",
            "public-bridge-spatial",
            "bounded-headless-frame",
            "public-bridge-failure",
        }
        assert workload.parameters["metric_profile"] in {
            "ecs-core",
            "ecs-bridge",
            "ecs-spatial",
            "ecs-frame",
            "ecs-longevity",
        }
        assert workload.parameters["oracle_profile"] in {
            "full-world-v1",
            "full-world-frame-v1",
            "failure-trace-v1",
        }
        assert workload.parameters["release_provenance_profile"] == "isolated-release-wheel-v1"
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
    matrix = [
        workload
        for workload in catalog.workloads
        if workload.parameters["case_kind"] in MATRIX_CASE_KINDS
    ]
    assert len(matrix) == 48
    assert {
        workload.parameters["expected_correctness_digest"] for workload in matrix
    } == EXPECTED_MATRIX_DIGESTS
    catalog.audit_definitions()


def test_ecs_catalog_freezes_executable_matrix_axes_without_scale_aliases() -> None:
    catalog = load_catalog(CATALOG_PATH)
    by_kind: dict[str, list[dict[str, object]]] = {}
    for workload in catalog.workloads:
        parameters = dict(workload.parameters)
        by_kind.setdefault(str(parameters["case_kind"]), []).append(parameters)

    assert {(p["schema_count"], p["field_count"]) for p in by_kind["schema-registration"]} == {
        (1, 1),
        (16, 4),
        (64, 16),
        (256, 16),
    }
    assert {p["list_length"] for p in by_kind["storage-semantics"]} == {0, 4, 32, 256}
    assert {p["entity_count"] for p in by_kind["spawn-shape"]} == {1_000, 10_000}
    assert {p["component_count"] for p in by_kind["spawn-shape"]} == {1, 4, 8}
    assert {p["field_count"] for p in by_kind["spawn-shape"]} == {1, 4, 16}
    assert {p["tag_count"] for p in by_kind["spawn-shape"]} == {0, 2, 8}
    assert {p["selectivity_percent"] for p in by_kind["query-selectivity"]} == {0, 1, 50, 100}
    assert {p["match_count"] for p in by_kind["cardinality-scale"]} == {0, 1, 2, 10_000}
    assert {p["query_count"] for p in by_kind["query-join-shape"]} == {2, 3, 4}
    assert {p["selectivity_percent"] for p in by_kind["query-join-shape"]} == {0, 1, 50}
    assert {p["work_units"] for p in by_kind["query-join-shape"]} == {400}
    assert {p["field_count"] for p in by_kind["transport-family"]} == {1, 2, 8, 16}
    assert {p["storage_family"] for p in by_kind["transport-family"]} == {
        "scalar",
        "vector",
        "list",
        "categorical",
    }
    assert {p["action_count"] for p in by_kind["plan-shape"]} == {10, 100, 1_000, 10_000}
    assert {p["depth"] for p in by_kind["plan-shape"]} == {1, 16, 128}
    assert {p["query_count"] for p in by_kind["plan-shape"]} == {1, 8, 64}
    assert {p["repeated_subexpression_percent"] for p in by_kind["plan-shape"]} == {
        0,
        50,
        90,
    }
    assert {p["system_count"] for p in by_kind["plan-system-scale"]} == {1, 100}
    assert {
        (p["system_count"], p["group_count"], p["entity_count"], p["frames"])
        for p in by_kind["schedule-scale"]
    } == {(8, 1, 16, 2), (64, 8, 16, 2)}
    assert {p["operation"] for p in by_kind["structural-shape"]} == {
        "add-component",
        "remove-component",
        "add-tag",
        "remove-tag",
        "despawn",
    }
    assert {(p["event_count"], p["reader_count"]) for p in by_kind["event-volume"]} == {
        (0, 1),
        (1_000, 1),
        (10_000, 4),
    }
    assert {p["distribution"] for p in by_kind["spatial-distribution"]} == {
        "uniform",
        "clustered",
        "diagonal",
        "same-cell",
    }
    assert {p["algorithm"] for p in by_kind["spatial-distribution"]} == {
        "hash-grid",
        "quadtree",
        "octree",
        "hilbert",
    }
    assert {p["movement_percent"] for p in by_kind["spatial-distribution"]} == {0, 10}
    assert {p["sharing_systems"] for p in by_kind["spatial-distribution"]} == {1, 4}
    assert {p["frames"] for p in by_kind["simulation-render"]} == {4, 8, 600}
    assert all(
        "declared_scale" not in p and "smoke_scale" not in p
        for values in by_kind.values()
        for p in values
    )


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


def test_ecs_spatial_distributions_are_exact_bounded_and_dimension_aware() -> None:
    for distribution in ("uniform", "clustered", "diagonal", "same-cell"):
        points2 = spatial_points(128, 2, distribution)
        points3 = spatial_points(128, 3, distribution)
        assert len(points2) == len(points3) == 128
        assert all(len(point) == 2 for point in points2)
        assert all(len(point) == 3 for point in points3)
        assert points2 == tuple(point[:2] for point in points3)
        assert all(0.0 <= coordinate <= 64.0 for point in points3 for coordinate in point)
    assert spatial_points(128, 3, "uniform") == spatial_points(128, 3, "uniform")


def test_ecs_metric_contract_is_complete_and_does_not_claim_blocked_collection() -> None:
    assert set(ECS_METRIC_REQUIREMENTS) == {
        "wall-time",
        "cpu-time",
        "throughput",
        "p50",
        "p95",
        "p99",
        "peak-rss",
        "ending-rss",
        "rss-slope",
        "bytes-per-row",
        "storage-scan-write-bandwidth",
        "archetype-transition-cache",
        "query-cache-phases",
        "bridge-calls",
        "bridge-objects",
        "python-transport-shapes",
        "compiled-cache-counters",
        "plan-phase-timers",
        "plan-memory-ownership",
        "rows-scanned-written",
        "world-clones",
        "scheduler-waves-conflicts-workers",
        "change-epoch-control",
        "event-queue-lifecycle",
        "spatial-candidates-exact",
        "spatial-update-cache-workers",
        "headless-frame-route",
        "native-interactive-qualification",
        "frame-render-present-phases",
    }
    assert ECS_METRIC_REQUIREMENTS["wall-time"]["status"] == "recorded"
    assert ECS_METRIC_REQUIREMENTS["throughput"]["status"] == "derivable"
    assert {
        name
        for name, contract in ECS_METRIC_REQUIREMENTS.items()
        if contract["status"] == "blocked"
    } == {
        "cpu-time",
        "p50",
        "p95",
        "p99",
        "peak-rss",
        "ending-rss",
        "rss-slope",
        "bytes-per-row",
        "storage-scan-write-bandwidth",
        "archetype-transition-cache",
        "query-cache-phases",
        "bridge-calls",
        "bridge-objects",
        "python-transport-shapes",
        "plan-phase-timers",
        "plan-memory-ownership",
        "world-clones",
        "scheduler-waves-conflicts-workers",
        "change-epoch-control",
        "native-interactive-qualification",
        "frame-render-present-phases",
    }


def test_ecs_suite_has_no_example_or_test_fixture_imports() -> None:
    suite = ROOT / "benchmarks" / "suites" / "ecs"
    for path in sorted(suite.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        )
        assert not any(name.startswith(("examples", "tests")) for name in imported)


def test_ecs_package_init_is_documentation_only_not_a_barrel() -> None:
    path = ROOT / "benchmarks" / "suites" / "ecs" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    assert ast.get_docstring(tree)
    assert not any(isinstance(node, ast.Import | ast.ImportFrom) for node in ast.walk(tree))
