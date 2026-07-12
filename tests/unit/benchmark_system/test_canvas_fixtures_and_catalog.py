from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.canvas.fixtures import FIXTURE_BYTES, FIXTURE_MANIFEST, validate_manifest

ROOT = Path(__file__).resolve().parents[3]


def test_canvas_fixtures_have_a_complete_deterministic_manifest() -> None:
    validate_manifest()
    assert {entry.name for entry in FIXTURE_MANIFEST} == set(FIXTURE_BYTES)
    assert all(entry.byte_length > 0 and len(entry.sha256) == 64 for entry in FIXTURE_MANIFEST)


def test_canvas_fixture_manifest_rejects_changed_bytes() -> None:
    changed = dict(FIXTURE_BYTES)
    changed["checkerboard-8"] = b"changed"

    with pytest.raises(ValueError, match="fixture length mismatch"):
        validate_manifest(payloads=changed)


def test_canvas_catalog_is_static_and_hashes_suite_sources() -> None:
    catalog = load_catalog(ROOT / "benchmarks" / "canvas_v1.toml")

    assert {
        (workload.id, workload.case_id, workload.execution_class.value)
        for workload in catalog.workloads
    } == {
        ("lifecycle-hidpi", "headless-continuous-clear-loop", "headless"),
        ("lifecycle-hidpi", "native-interactive-continuous-clear-loop", "native-interactive"),
        ("lifecycle-hidpi", "headless-explicit-redraw", "headless"),
        ("lifecycle-hidpi", "native-interactive-explicit-redraw", "native-interactive"),
        ("lifecycle-hidpi", "headless-no-loop-idle", "headless"),
        ("lifecycle-hidpi", "native-interactive-no-loop-idle", "native-interactive"),
        ("primitives-paths-order", "headless-uniform-primitives-1k", "headless"),
        (
            "primitives-paths-order",
            "native-interactive-uniform-primitives-1k",
            "native-interactive",
        ),
        ("primitives-paths-order", "headless-mixed-primitives-5k", "headless"),
        ("primitives-paths-order", "native-interactive-mixed-primitives-5k", "native-interactive"),
        ("primitives-paths-order", "headless-paths-1k-by-32", "headless"),
        ("primitives-paths-order", "native-interactive-paths-1k-by-32", "native-interactive"),
        ("primitives-paths-order", "headless-nested-clips-depth-4-by-32", "headless"),
        (
            "primitives-paths-order",
            "native-interactive-nested-clips-depth-4-by-32",
            "native-interactive",
        ),
        (
            "images-text-pixels-effects",
            "headless-sprite-uniqueness-mutation",
            "headless",
        ),
        (
            "images-text-pixels-effects",
            "native-interactive-sprite-uniqueness-mutation",
            "native-interactive",
        ),
        ("images-text-pixels-effects", "headless-text-reuse-script", "headless"),
        (
            "images-text-pixels-effects",
            "native-interactive-text-reuse-script",
            "native-interactive",
        ),
        ("images-text-pixels-effects", "headless-pixel-read-write-locality", "headless"),
        (
            "images-text-pixels-effects",
            "native-interactive-pixel-read-write-locality",
            "native-interactive",
        ),
        ("images-text-pixels-effects", "headless-ordered-effects", "headless"),
        (
            "images-text-pixels-effects",
            "native-interactive-ordered-effects",
            "native-interactive",
        ),
    }
    lifecycle_cases = [
        workload for workload in catalog.workloads if workload.id == "lifecycle-hidpi"
    ]
    assert {
        (workload.execution_class.value, workload.parameters["lifecycle_mode"])
        for workload in lifecycle_cases
    } == {
        ("headless", "continuous-clear-loop"),
        ("native-interactive", "continuous-clear-loop"),
        ("headless", "explicit-redraw"),
        ("native-interactive", "explicit-redraw"),
        ("headless", "no-loop-idle"),
        ("native-interactive", "no-loop-idle"),
    }
    assert all(
        workload.parameters["expected_draw_callbacks"] == workload.parameters["frames"]
        if workload.parameters["lifecycle_mode"] == "continuous-clear-loop"
        else workload.parameters["expected_draw_callbacks"] == 1
        for workload in lifecycle_cases
    )
    for workload in lifecycle_cases:
        if workload.execution_class.value != "native-interactive":
            continue
        required_counters = workload.parameters["required_counters"]
        assert isinstance(required_counters, list)
        assert "frames_presented" in required_counters
    primitive_cases = [
        workload for workload in catalog.workloads if workload.id == "primitives-paths-order"
    ]
    assert {
        (workload.execution_class.value, workload.parameters["case_kind"])
        for workload in primitive_cases
    } == {
        ("headless", "uniform-primitives"),
        ("native-interactive", "uniform-primitives"),
        ("headless", "mixed-primitives"),
        ("native-interactive", "mixed-primitives"),
        ("headless", "paths"),
        ("native-interactive", "paths"),
        ("headless", "nested-clips"),
        ("native-interactive", "nested-clips"),
    }
    for workload in primitive_cases:
        draw_count = workload.parameters["draw_count"]
        required_counters = workload.parameters["required_counters"]
        assert isinstance(draw_count, int) and draw_count > 0
        assert isinstance(required_counters, list) and required_counters
        if workload.execution_class.value == "native-interactive":
            assert workload.parameters["frames"] == 30
            assert workload.parameters["width"] == 1280
            assert workload.parameters["height"] == 720
            assert workload.parameters["density"] == "2.0"
            assert "frames_presented" in required_counters
    feature_cases = [
        workload for workload in catalog.workloads if workload.id == "images-text-pixels-effects"
    ]
    assert {
        (workload.execution_class.value, workload.parameters["case_kind"])
        for workload in feature_cases
    } == {
        ("headless", "sprite-uniqueness-mutation"),
        ("native-interactive", "sprite-uniqueness-mutation"),
        ("headless", "text-reuse-script"),
        ("native-interactive", "text-reuse-script"),
        ("headless", "pixel-read-write-locality"),
        ("native-interactive", "pixel-read-write-locality"),
        ("headless", "ordered-effects"),
        ("native-interactive", "ordered-effects"),
    }
    expected_counters = {
        "sprite-uniqueness-mutation": {"image_cache_misses", "image_cache_hits", "texture_uploads"},
        "text-reuse-script": {"text_cache_misses", "text_cache_hits"},
        "pixel-read-write-locality": {"pixel_readbacks", "pixel_uploads"},
        "ordered-effects": {"gpu_region_effect_passes"},
    }
    for workload in feature_cases:
        case_kind = workload.parameters["case_kind"]
        assert isinstance(case_kind, str)
        counters = workload.parameters["required_counters"]
        assert isinstance(counters, list)
        assert expected_counters[case_kind] <= set(counters)
        assert workload.primary_metric.work_unit == "draw-record"
        assert isinstance(workload.parameters["draw_count"], int)
        if workload.execution_class.value == "native-interactive":
            assert workload.parameters["frames"] == 30
            assert workload.parameters["width"] == 1280
            assert workload.parameters["height"] == 720
            assert workload.parameters["density"] == "2.0"
            assert "frames_presented" in counters
    assert all(
        source.startswith("suites/canvas/") or source == "suites/__init__.py"
        for source in catalog.workload_files()
    )
    assert all(workload.definition_digest.startswith("sha256:") for workload in catalog.workloads)
    assert all(
        not parameter.endswith("_matrix")
        for workload in catalog.workloads
        for parameter in workload.parameters
    )
