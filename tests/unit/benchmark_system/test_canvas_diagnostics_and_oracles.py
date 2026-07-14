from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from benchmarks.suites.canvas.diagnostics import (
    CANVAS_DIAGNOSTICS_SCHEMA_VERSION,
    DiagnosticsError,
    EvidenceStatus,
    capture_canvas_diagnostics,
    capture_renderer_diagnostics,
    reset_canvas_diagnostics,
)
from benchmarks.suites.canvas.fixtures import SPRITE_CACHE_RESET, sprite_image
from benchmarks.suites.canvas.oracles import (
    CanvasOracleError,
    PixelSentinel,
    ResourceLifecycleExpectation,
    assert_canvas_state,
    assert_capability_failure,
    assert_effect_changed,
    assert_hidpi_dimensions,
    assert_numeric_samples_close,
    assert_ordered_layers,
    assert_presented_frames,
    assert_replay_updated,
    assert_resource_lifecycle_balanced,
    assert_resource_reset_preserves_warm_cache,
    assert_rgba_digest,
    assert_rgba_sentinels,
    assert_text_bounds_close,
    rgba_at,
    rgba_sha256,
)


@dataclass
class _DiagnosticsContext:
    counters: dict[str, object]
    api_counters: dict[str, object] = field(
        default_factory=lambda: {"pixel_readback": 1, "texture_upload": 1}
    )
    pacing: dict[str, object] = field(
        default_factory=lambda: {
            "enabled": True,
            "frames": 1,
            "event_polls": 2,
            "event_poll_duration_ms_total": 0.5,
            "max_event_poll_duration_ms": 0.3,
            "mean_event_poll_duration_ms": 0.25,
            "last_event_poll_duration_ms": None,
        }
    )

    def performance_diagnostics(self) -> dict[str, object]:
        return {
            "enabled": True,
            "counters": self.api_counters,
            "messages": [],
            "renderer": self.counters,
        }

    def renderer_performance_counters(self) -> dict[str, object]:
        return self.counters

    def frame_pacing_diagnostics(self) -> dict[str, object]:
        return self.pacing

    def reset_performance_diagnostics(self) -> None:
        self.api_counters = {}

    def reset_renderer_performance_counters(self) -> None:
        value = self.counters.get("texture_resident_bytes", 0)
        assert isinstance(value, int) and not isinstance(value, bool)
        retained = value
        self.counters = {
            "texture_resident_bytes": retained,
            "texture_peak_bytes": retained,
            "texture_uploads": 0,
        }

    def reset_frame_pacing_diagnostics(self) -> None:
        self.pacing = {
            "enabled": True,
            "frames": 0,
            "event_polls": 0,
            "event_poll_duration_ms_total": 0.0,
            "max_event_poll_duration_ms": 0.0,
            "mean_event_poll_duration_ms": 0.0,
            "last_event_poll_duration_ms": None,
        }


@dataclass
class _DimensionsContext:
    width: int
    height: int
    density: float
    frame_count: int = 0

    def pixel_density(self) -> float:
        return self.density


def test_canvas_diagnostics_adapter_uses_only_available_public_counters() -> None:
    context = _DiagnosticsContext({"gpu_region_effect_passes": 2, "native": {"cpu_fallbacks": 0}})

    snapshot = capture_renderer_diagnostics(
        context, required=("gpu_region_effect_passes", "native.cpu_fallbacks")
    )

    assert snapshot.counter("gpu_region_effect_passes") == 2
    assert snapshot.counter("native.cpu_fallbacks") == 0
    record = snapshot.as_record()
    assert record["schema_version"] == CANVAS_DIAGNOSTICS_SCHEMA_VERSION
    assert record["source"] == "renderer_performance_counters"
    assert record["counters"] == {
        "gpu_region_effect_passes": 2,
        "native": {"cpu_fallbacks": 0},
    }
    assert record["qualification"] == {
        "execution_class": "unspecified",
        "api_performance_diagnostics_enabled": False,
        "physical_desktop_requested": False,
        "physical_desktop_qualified": False,
        "physical_present_feedback_qualified": False,
        "physical_scanout_qualified": False,
        "present_counter_semantics": "completed-runtime-present-call-not-physical-scanout",
    }
    with pytest.raises(DiagnosticsError, match="required renderer counter unavailable"):
        capture_renderer_diagnostics(context, required=("gpu_draw_calls",))
    with pytest.raises(DiagnosticsError, match="unsupported value type"):
        capture_renderer_diagnostics(_DiagnosticsContext({"private": object()}))
    with pytest.raises(DiagnosticsError, match="not boolean"):
        capture_renderer_diagnostics(_DiagnosticsContext({"private": True}))


def test_canvas_v2_snapshot_records_complete_public_sources_and_explicit_gaps() -> None:
    context = _DiagnosticsContext(
        {
            "frames_presented": 3,
            "event_polls": 2,
            "pixel_readback_requested_bytes": 128,
            "pixel_readback_copied_bytes": 64,
            "gpu_region_effect_passes": 1,
            "image_cache_resident_bytes": 256,
            "image_cache_peak_bytes": 512,
            "image_cache_evictions": 1,
            "image_cache_evicted_bytes": 128,
            "texture_resident_bytes": 256,
            "texture_peak_bytes": 512,
            "texture_destructions": 1,
            "image_atlas_resident_bytes": 512,
            "image_atlas_peak_bytes": 1024,
            "image_atlas_destructions": 1,
            "text_cache_hits": 4,
            "text_cache_misses": 1,
            "text_cache_evictions": 0,
            "text_measurements": 1,
            "native": {
                "gpu_command_clone_count": 2,
                "gpu_command_clone_bytes": 96,
                "gpu_command_segment_allocation_count": 1,
                "pixel_bytes_created": 256,
            },
        }
    )

    snapshot = capture_canvas_diagnostics(
        context,
        required=("frames_presented", "native.gpu_command_clone_bytes"),
        execution_class="native-interactive",
        physical_desktop_requested=True,
    )
    record = cast(dict[str, Any], snapshot.as_record())
    coverage = {item["name"]: item for item in record["coverage"]}

    assert snapshot.counter("api.pixel_readback") == 1
    assert snapshot.counter("frame_pacing.event_polls") == 2
    assert record["api_performance_counters"] == context.api_counters
    assert record["frame_pacing"] == context.pacing
    assert record["counter_groups"]["media"] == {}
    assert record["counter_groups"]["command"]["renderer.native.gpu_command_clone_bytes"] == 96
    assert coverage["command_clone_work"]["status"] == EvidenceStatus.AVAILABLE.value
    assert coverage["path_bind_groups"]["status"] == EvidenceStatus.NOT_PUBLICLY_REPORTED.value
    assert coverage["media_copies_and_texture_identity"]["public_paths"] == []
    assert coverage["physical_present_feedback"]["status"] == (
        EvidenceStatus.PHYSICAL_QUALIFICATION_REQUIRED.value
    )
    assert record["qualification"]["api_performance_diagnostics_enabled"] is True
    assert record["qualification"]["physical_desktop_requested"] is True
    assert record["qualification"]["physical_desktop_qualified"] is False
    assert record["qualification"]["physical_scanout_qualified"] is False
    assert json.dumps(record, sort_keys=True, separators=(",", ":")) == json.dumps(
        snapshot.as_record(), sort_keys=True, separators=(",", ":")
    )


def test_canvas_diagnostic_reset_is_warm_and_cold_requests_fail_closed() -> None:
    context = _DiagnosticsContext(
        {
            "texture_resident_bytes": 256,
            "texture_peak_bytes": 512,
            "texture_uploads": 3,
        }
    )

    reset_canvas_diagnostics(context)

    assert context.counters == {
        "texture_resident_bytes": 256,
        "texture_peak_bytes": 256,
        "texture_uploads": 0,
    }
    assert context.api_counters == {}
    assert context.pacing["event_polls"] == 0
    assert context.pacing["last_event_poll_duration_ms"] is None
    with pytest.raises(DiagnosticsError, match="cold Canvas diagnostic reset is unsupported"):
        reset_canvas_diagnostics(context, cold=True)


def test_headless_sprite_cache_reset_preserves_warm_resources_and_fails_closed() -> None:
    import gummysnake as gs

    fixture = SPRITE_CACHE_RESET
    image = cast(Any, sprite_image())

    def setup() -> None:
        gs.create_canvas(16, 12, pixel_density=1.0)

    def draw() -> None:
        gs.image(image, 0, 0, fixture.source.width, fixture.source.height)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    before_reset = capture_renderer_diagnostics(
        context, required=(*fixture.required_counters, "cpu_fallbacks")
    )
    assert before_reset.counter("cpu_fallbacks") == 0
    assert before_reset.counter("texture_uploads") == 1
    assert before_reset.counter("texture_upload_bytes") == len(fixture.source.pixels)

    reset_canvas_diagnostics(context)
    after_reset = capture_renderer_diagnostics(context, required=fixture.required_counters)
    assert_resource_reset_preserves_warm_cache(before_reset.counters, after_reset.counters, fixture)

    missing_counter = dict(after_reset.counters)
    del missing_counter["texture_resident_bytes"]
    with pytest.raises(CanvasOracleError, match="texture_resident_bytes"):
        assert_resource_reset_preserves_warm_cache(before_reset.counters, missing_counter, fixture)
    stale_activity = dict(after_reset.counters)
    stale_activity["texture_uploads"] = 1
    with pytest.raises(CanvasOracleError, match="texture_uploads"):
        assert_resource_reset_preserves_warm_cache(before_reset.counters, stale_activity, fixture)


def test_canvas_output_state_and_tolerance_oracles_are_fail_closed() -> None:
    pixels = bytes(
        [
            255,
            0,
            0,
            255,
            0,
            255,
            0,
            255,
            0,
            0,
            255,
            255,
            255,
            255,
            255,
            255,
        ]
    )
    expected_digest = rgba_sha256(pixels)
    assert_rgba_digest(pixels, expected_digest)
    assert rgba_at(pixels, 2, 1, 0) == (0, 255, 0, 255)
    layers = (
        PixelSentinel(0, 0, (255, 0, 0, 255)),
        PixelSentinel(1, 1, (255, 255, 255, 255)),
    )
    assert_rgba_sentinels(pixels, 2, layers)
    assert_ordered_layers(pixels, 2, layers)
    context = _DimensionsContext(1, 1, 2.0, frame_count=2)
    assert_canvas_state(context, logical_width=1, logical_height=1, density=2.0, frame_count=2)
    assert_hidpi_dimensions(
        context,
        bytes(16),
        logical_width=1,
        logical_height=1,
        density=2.0,
    )
    assert_presented_frames({"frames_presented": 2}, 2)
    assert_text_bounds_close(
        (1.0, 2.0, 30.1, 12.0),
        (1.0, 2.0, 30.0, 12.0),
        absolute_tolerance=0.11,
    )
    assert_numeric_samples_close(
        (0.0, 1.01, -2.0),
        (0.0, 1.0, -2.0),
        absolute_tolerance=0.02,
        label="3D camera projection",
    )

    with pytest.raises(CanvasOracleError, match="RGBA digest expected"):
        assert_rgba_digest(bytes(len(pixels)), expected_digest)
    with pytest.raises(CanvasOracleError, match="presented 1 frames"):
        assert_presented_frames({"frames_presented": 1}, 2)
    with pytest.raises(CanvasOracleError, match="text bounds sample 2"):
        assert_text_bounds_close(
            (1.0, 2.0, 31.0, 12.0),
            (1.0, 2.0, 30.0, 12.0),
            absolute_tolerance=0.1,
        )


def test_effect_replay_resource_and_capability_oracles_detect_regressions() -> None:
    before = bytes((10, 20, 30, 255, 40, 50, 60, 255))
    after = bytes((245, 235, 225, 255, 40, 50, 60, 255))
    assert_effect_changed(before, after)
    assert_replay_updated(before, after, {"retained_batch_cache_hits": 1})

    lifecycle = ResourceLifecycleExpectation(
        "offscreen",
        resident_counter="resident",
        peak_counter="peak",
        allocation_counter="allocations",
        destruction_counter="destructions",
    )
    baseline = {"resident": 64, "peak": 64, "allocations": 3, "destructions": 3}
    released = {"resident": 64, "peak": 128, "allocations": 5, "destructions": 5}
    assert_resource_lifecycle_balanced(baseline, released, lifecycle)

    with pytest.raises(CanvasOracleError, match="effect changed 0 pixels"):
        assert_effect_changed(before, before)
    with pytest.raises(CanvasOracleError, match="stale unchanged"):
        assert_replay_updated(before, before, {"retained_batch_cache_hits": 1})
    with pytest.raises(CanvasOracleError, match="resident bytes leaked"):
        assert_resource_lifecycle_balanced(
            baseline,
            {"resident": 96, "peak": 128, "allocations": 5, "destructions": 5},
            lifecycle,
        )
    with pytest.raises(CanvasOracleError, match="destroyed 1"):
        assert_resource_lifecycle_balanced(
            baseline,
            {"resident": 64, "peak": 128, "allocations": 5, "destructions": 4},
            lifecycle,
        )

    def missing_native_window() -> None:
        raise RuntimeError("native window capability unavailable")

    assert_capability_failure(missing_native_window, "native-window")
    with pytest.raises(CanvasOracleError, match="unexpectedly succeeded"):
        assert_capability_failure(lambda: None, "native-window")
