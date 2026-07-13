from __future__ import annotations

from dataclasses import dataclass

import pytest

from benchmarks.suites.canvas.diagnostics import (
    CANVAS_DIAGNOSTICS_SCHEMA_VERSION,
    DiagnosticsError,
    capture_renderer_diagnostics,
)
from benchmarks.suites.canvas.fixtures import SPRITE_CACHE_RESET, sprite_image
from benchmarks.suites.canvas.oracles import (
    CanvasOracleError,
    PixelSentinel,
    assert_capability_failure,
    assert_hidpi_dimensions,
    assert_ordered_layers,
    assert_presented_frames,
    assert_resource_reset_preserves_warm_cache,
    assert_rgba_sentinels,
    rgba_at,
)


@dataclass
class _DiagnosticsContext:
    counters: dict[str, object]

    def renderer_performance_counters(self) -> dict[str, object]:
        return self.counters


@dataclass
class _DimensionsContext:
    width: int
    height: int
    density: float

    def pixel_density(self) -> float:
        return self.density


def test_canvas_diagnostics_adapter_uses_only_available_public_counters() -> None:
    context = _DiagnosticsContext({"gpu_region_effect_passes": 2, "native": {"cpu_fallbacks": 0}})

    snapshot = capture_renderer_diagnostics(
        context, required=("gpu_region_effect_passes", "native.cpu_fallbacks")
    )

    assert snapshot.counter("gpu_region_effect_passes") == 2
    assert snapshot.counter("native.cpu_fallbacks") == 0
    assert snapshot.as_record() == {
        "schema_version": CANVAS_DIAGNOSTICS_SCHEMA_VERSION,
        "source": "renderer_performance_counters",
        "counters": {"gpu_region_effect_passes": 2, "native": {"cpu_fallbacks": 0}},
    }
    with pytest.raises(DiagnosticsError, match="required renderer counter unavailable"):
        capture_renderer_diagnostics(context, required=("gpu_draw_calls",))
    with pytest.raises(DiagnosticsError, match="unsupported value type"):
        capture_renderer_diagnostics(_DiagnosticsContext({"private": object()}))
    with pytest.raises(DiagnosticsError, match="not boolean"):
        capture_renderer_diagnostics(_DiagnosticsContext({"private": True}))


def test_headless_sprite_cache_reset_preserves_warm_resources_and_fails_closed() -> None:
    import gummysnake as gs

    fixture = SPRITE_CACHE_RESET
    image = sprite_image()

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

    context.reset_renderer_performance_counters()
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


def test_canvas_pixel_order_hidpi_and_capability_oracles_are_fail_closed() -> None:
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
    assert rgba_at(pixels, 2, 1, 0) == (0, 255, 0, 255)
    layers = (PixelSentinel(0, 0, (255, 0, 0, 255)), PixelSentinel(1, 1, (255, 255, 255, 255)))
    assert_rgba_sentinels(pixels, 2, layers)
    assert_ordered_layers(pixels, 2, layers)
    assert_hidpi_dimensions(
        _DimensionsContext(1, 1, 2.0), bytes(16), logical_width=1, logical_height=1, density=2.0
    )
    assert_presented_frames({"frames_presented": 2}, 2)
    with pytest.raises(CanvasOracleError, match="presented 1 frames"):
        assert_presented_frames({"frames_presented": 1}, 2)

    def missing_native_window() -> None:
        raise RuntimeError("native window capability unavailable")

    assert_capability_failure(missing_native_window, "native-window")
    with pytest.raises(CanvasOracleError, match="unexpectedly succeeded"):
        assert_capability_failure(lambda: None, "native-window")
