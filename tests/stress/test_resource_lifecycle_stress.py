from __future__ import annotations

import pytest

from p5.assets.image import Image
from p5.backends.canvas_renderer import CanvasRenderer
from p5.constants import BLEND, MULTIPLY
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.rust.canvas import require_canvas_extension

pytestmark = pytest.mark.stress


def _renderer() -> CanvasRenderer:
    return CanvasRenderer(require_canvas_extension())


def test_canvas_churns_images_pixels_and_resizes_without_inconsistent_state() -> None:
    renderer = _renderer()
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)
    transform = Matrix2D.identity()
    renderer.resize(24, 16, pixel_density=1)

    for frame in range(180):
        if frame and frame % 30 == 0:
            renderer.resize(24 + (frame % 3) * 4, 16 + (frame % 2) * 4, pixel_density=1)
        rgba = bytes([frame % 256, 64, 192, 255] * 16)
        image = Image(4, 4, rgba)
        renderer.background(Color(frame % 256, 20, 30, 255))
        renderer.draw_image(image, frame % max(1, renderer.width - 4), 0, 4, 4, style, transform)
        pixels = renderer.load_pixel_bytes()
        renderer.update_pixels(pixels)
        renderer.present()

    counters = renderer.performance_counters()
    assert renderer.width > 0
    assert renderer.physical_width > 0
    assert counters["image_cache_misses"] >= 100
    assert counters["pixel_readbacks"] >= 100
    assert counters["pixel_uploads"] >= 100
    renderer.close()


def test_dynamic_text_cache_is_bounded_during_long_running_sessions() -> None:
    renderer = _renderer()
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)
    style.text_size = 10
    transform = Matrix2D.identity()
    renderer.resize(64, 32, pixel_density=1)

    for frame in range(540):
        renderer.text(f"frame {frame}", 1, 12, style, transform)
        if frame % 9 == 0:
            renderer.text_width("stable", style)
            renderer.text_width("stable", style)
        renderer.end_frame()

    counters = renderer.performance_counters()
    native = counters.get("native")
    assert isinstance(native, dict)
    assert native["text_cache_misses"] >= 500
    assert native["text_cache_evictions"] > 0
    assert counters["text_cache_hits"] > 0
    renderer.close()


def test_repeated_runtime_close_and_recreate_lifecycle() -> None:
    for index in range(20):
        renderer = _renderer()
        renderer.resize(12 + index % 3, 10 + index % 4, pixel_density=1)
        renderer.background(Color(0, index, 64, 255))
        renderer.present()
        renderer.close()


def test_repeated_fallback_paths_report_diagnostics() -> None:
    renderer = _renderer()
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)
    transform = Matrix2D.identity()
    renderer.resize(16, 16, pixel_density=1)

    for frame in range(90):
        style.blend_mode = MULTIPLY if frame % 2 else BLEND
        renderer.rect(0, 0, 8, 8, style, transform)
        renderer.blend_region(None, (0, 0, 4, 4), (4, 4, 4, 4), BLEND)
        renderer.load_pixels()

    counters = renderer.performance_counters()
    assert counters["cpu_fallbacks"] >= 90
    assert counters["pixel_readbacks"] >= 90
    renderer.close()
