from __future__ import annotations

from pathlib import Path

import pytest

import gummysnake as gs
from benchmarks.coverage import assert_checked_manifest, load_checked_manifest, load_manifest
from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.canvas.fixtures import (
    BINARY_FIXTURE_QUALIFICATIONS,
    CHECKERBOARD,
    FIXTURE_BYTES,
    FIXTURE_FAMILIES,
    FIXTURE_MANIFEST,
    MEDIA_FRAME_BGR,
    MEDIA_FRAME_BGRA,
    MEDIA_FRAME_GRAY,
    MINIMAL_OBJ_FIXTURE,
    PRIMITIVE_PATH_FIXTURE,
    SPRITE_CACHE_RESET,
    SPRITE_SHEET,
    TEXT_CORPUS,
    TEXT_CORPUS_FIXTURE,
    MediaFrameFixture,
    validate_manifest,
)
from benchmarks.suites.canvas.oracles import (
    CanvasOracleError,
    assert_media_frame_rgba,
    assert_obj_fixture_topology,
    assert_png_export,
    assert_text_corpus,
)
from benchmarks.suites.canvas.workloads import dispatch as dispatch_canvas
from gummysnake.rust.canvas import require_canvas_runtime

ROOT = Path(__file__).resolve().parents[3]


def test_canvas_fixtures_have_a_complete_deterministic_manifest() -> None:
    validate_manifest()
    assert {entry.name for entry in FIXTURE_MANIFEST} == set(FIXTURE_BYTES)
    family_names = [name for names in FIXTURE_FAMILIES.values() for name in names]
    assert len(family_names) == len(set(family_names))
    assert set(family_names) == set(FIXTURE_BYTES)
    assert PRIMITIVE_PATH_FIXTURE.records
    assert all(entry.byte_length > 0 and len(entry.sha256) == 64 for entry in FIXTURE_MANIFEST)


def test_canvas_binary_fixture_qualification_is_explicit_and_does_not_use_examples() -> None:
    qualifications = {item.family: item for item in BINARY_FIXTURE_QUALIFICATIONS}

    assert set(qualifications) == {"font", "codec"}
    assert all(
        item.status == "not-bundled-no-reviewed-repository-fixture"
        for item in qualifications.values()
    )
    assert all("example" not in item.reason.lower() for item in qualifications.values())


def test_canvas_fixture_manifest_rejects_changed_bytes() -> None:
    changed = dict(FIXTURE_BYTES)
    original = changed["media-frame-bgr-6"]
    changed["media-frame-bgr-6"] = bytes([original[0] ^ 0xFF, *original[1:]])

    with pytest.raises(ValueError, match="fixture hash mismatch for media-frame-bgr-6"):
        validate_manifest(payloads=changed)


@pytest.mark.parametrize("fixture", (MEDIA_FRAME_BGR, MEDIA_FRAME_BGRA, MEDIA_FRAME_GRAY))
def test_media_frame_fixtures_match_the_native_canvas_conversion(
    fixture: MediaFrameFixture,
) -> None:
    runtime = require_canvas_runtime()

    actual = runtime.media_frame_to_rgba(
        fixture.width, fixture.height, fixture.channels, fixture.pixels
    )

    assert_media_frame_rgba(fixture, actual)
    with pytest.raises(CanvasOracleError, match="native RGBA conversion"):
        assert_media_frame_rgba(fixture, bytes(len(fixture.expected_rgba.pixels)))


def test_generated_media_frame_workload_exercises_the_public_rust_conversion_path() -> None:
    run = dispatch_canvas(
        "assets-media-models",
        {
            "frames": 1,
            "width": 16,
            "height": 12,
            "density": 1.0,
            "frame_rate": 60,
            "case_kind": "media-frame-conversion",
            "conversion_count": 9,
            "conversion_width": 6,
            "conversion_height": 4,
            "channels": 3,
            "dispatch_route": "global",
            "required_counters": [],
        },
        "headless",
    )

    assert run.draw_callbacks == 1
    assert run.draw_records == 9


def test_native_png_export_has_exact_codec_dimensions_and_rgba(tmp_path: Path) -> None:
    output = tmp_path / "checkerboard.png"
    image = gs.Image(CHECKERBOARD.width, CHECKERBOARD.height, CHECKERBOARD.pixels)

    image.save(output)

    result = assert_png_export(
        output.read_bytes(),
        width=CHECKERBOARD.width,
        height=CHECKERBOARD.height,
        expected_rgba=CHECKERBOARD.pixels,
    )
    assert result.rgba_sha256 == (
        "sha256:a814e5420f755241e10a600f2f923fa59603152d80b244449aa0b607492bdd3a"
    )
    with pytest.raises(CanvasOracleError, match="not a PNG"):
        assert_png_export(
            b"GIF89a" + output.read_bytes()[6:],
            width=CHECKERBOARD.width,
            height=CHECKERBOARD.height,
        )


def test_obj_fixture_manifest_and_real_native_load_preserve_reviewed_topology(
    tmp_path: Path,
) -> None:
    obj_path = tmp_path / "minimal-triangle.obj"
    obj_path.write_bytes(MINIMAL_OBJ_FIXTURE.payload)

    model = gs.load_model(obj_path)

    assert_obj_fixture_topology(model, MINIMAL_OBJ_FIXTURE)


def test_text_fixture_manifest_preserves_exact_unicode_inputs() -> None:
    assert_text_corpus(TEXT_CORPUS_FIXTURE, TEXT_CORPUS)

    changed = dict(TEXT_CORPUS)
    changed["rtl"] = ("changed",)
    with pytest.raises(CanvasOracleError, match="text corpus"):
        assert_text_corpus(TEXT_CORPUS_FIXTURE, changed)


def test_sprite_cache_reset_fixture_uses_reviewed_sprite_bytes_and_public_counters() -> None:
    fixture = SPRITE_CACHE_RESET

    assert fixture.source is SPRITE_SHEET
    assert len(fixture.source.pixels) == fixture.source.width * fixture.source.height * 4
    assert fixture.required_counters == (
        "texture_resident_bytes",
        "texture_peak_bytes",
        "image_atlas_resident_bytes",
        "image_atlas_peak_bytes",
        "image_cache_evictions",
        "texture_uploads",
        "texture_upload_bytes",
        "texture_dirty_uploads",
        "texture_cache_evictions",
        "texture_destructions",
        "image_atlas_evictions",
        "image_atlas_destructions",
    )


def test_canvas_coverage_manifest_is_exactly_the_92_case_catalog_projection() -> None:
    catalog_path = ROOT / "benchmarks" / "canvas_v1.toml"
    manifest_path = ROOT / "benchmarks" / "coverage" / "canvas_v1.json"
    catalog = load_catalog(catalog_path)
    generated = load_manifest(catalog_path)
    checked = load_checked_manifest(manifest_path)

    assert_checked_manifest(catalog, checked)
    assert checked.to_dict() == generated.to_dict()
    assert len(checked.entries) == 92
    assert sum(entry.route == "headless" for entry in checked.entries) == 66
    assert sum(entry.route == "native-interactive" for entry in checked.entries) == 26


def test_canvas_catalog_is_static_and_hashes_complete_executable_matrices() -> None:
    catalog = load_catalog(ROOT / "benchmarks" / "canvas_v1.toml")

    assert len(catalog.workloads) == 92
    assert {workload.suite_version for workload in catalog.workloads} == {5}
    assert {workload.version for workload in catalog.workloads} == {2, 3}
    assert sum(workload.version == 3 for workload in catalog.workloads) == 1
    assert {workload.id for workload in catalog.workloads} == {
        "lifecycle-hidpi",
        "primitives-paths-order",
        "images-text-pixels-effects",
        "assets-media-models",
    }
    assert len({workload.case_id for workload in catalog.workloads}) == len(catalog.workloads)

    lifecycle = [workload for workload in catalog.workloads if workload.id == "lifecycle-hidpi"]
    assert {workload.parameters["lifecycle_mode"] for workload in lifecycle} == {
        "empty-loop",
        "continuous-clear-loop",
        "explicit-redraw",
        "no-loop-idle",
        "dynamic-frame-rate",
        "resize-density-churn",
    }
    assert {workload.parameters["frame_rate"] for workload in lifecycle} >= {30, 60, 120}
    assert any(workload.parameters["density"] == "1.5" for workload in lifecycle)
    assert any(
        workload.parameters["width"] == 3840 and workload.parameters["height"] == 2160
        for workload in lifecycle
    )

    primitives = [
        workload for workload in catalog.workloads if workload.id == "primitives-paths-order"
    ]
    assert {workload.parameters["case_kind"] for workload in primitives} == {
        "uniform-primitives",
        "mixed-primitives",
        "independent-lines",
        "polyline",
        "paths",
        "curves-contours",
        "nested-clips",
        "ordered-family-stream",
    }
    assert {workload.parameters.get("dispatch_route") for workload in primitives} >= {
        "global",
        "object",
        "fast",
    }
    draw_counts = [workload.parameters["draw_count"] for workload in primitives]
    assert all(isinstance(value, int) for value in draw_counts)
    assert max(value for value in draw_counts if isinstance(value, int)) == 100_000
    assert {workload.parameters.get("clip_depth") for workload in primitives} >= {1, 4, 16}

    features = [
        workload for workload in catalog.workloads if workload.id == "images-text-pixels-effects"
    ]
    assert {
        workload.parameters["effect_name"]
        for workload in features
        if workload.parameters.get("effect_family") == "filter"
    } == {
        "threshold",
        "gray",
        "invert",
        "blur",
        "posterize",
        "erode",
        "dilate",
    }
    assert {
        workload.parameters["effect_name"]
        for workload in features
        if workload.parameters.get("effect_family") == "blend"
    } == {
        "blend",
        "add",
        "darkest",
        "lightest",
        "difference",
        "exclusion",
        "multiply",
        "screen",
        "replace",
    }
    assert {workload.parameters.get("unique_images") for workload in features} >= {1, 8, 128}
    assert {workload.parameters.get("text_size") for workload in features} >= {12, 48, 128}
    assert {workload.parameters.get("write_kind") for workload in features} >= {
        "one-byte",
        "one-pixel",
        "row",
        "block",
        "full",
        "overwrite",
        "composite",
    }

    assets = [workload for workload in catalog.workloads if workload.id == "assets-media-models"]
    assert {workload.parameters["case_kind"] for workload in assets} == {
        "image-asset-operations",
        "png-export-roundtrip",
        "media-frame-conversion",
        "offscreen-resource-churn",
        "storage-compute-lifecycle",
        "model-import-export",
    }
    assert any(workload.parameters.get("conversion_count") == 300 for workload in assets)
    assert any(workload.parameters.get("triangle_count") == 10_000 for workload in assets)
    assert any(workload.parameters.get("instance_count") == 1_000 for workload in assets)

    for workload in catalog.workloads:
        counters = workload.parameters["required_counters"]
        assert isinstance(counters, list)
        if workload.execution_class.value == "native-interactive":
            assert "frames_presented" in counters
        assert workload.definition_digest.startswith("sha256:")
        assert all(not parameter.endswith("_matrix") for parameter in workload.parameters)
    assert all(
        source.startswith("suites/canvas/")
        or source in {"suites/__init__.py", "suites/registry.py"}
        for source in catalog.workload_files()
    )
