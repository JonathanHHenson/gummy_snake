from __future__ import annotations

import pytest

from p5 import constants as c
from p5.backends.canvas_renderer import CanvasRenderer
from p5.backends.pillow import PillowRenderer
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.rust.canvas import is_canvas_available, require_canvas_extension

pytestmark = pytest.mark.skipif(
    not is_canvas_available(),
    reason="p5.rust._canvas extension is not built; run the explicit p5_canvas maturin command",
)


def _different_channel_count(left: list[int], right: list[int], *, tolerance: int = 20) -> int:
    assert len(left) == len(right)
    return sum(abs(a - b) > tolerance for a, b in zip(left, right, strict=True))


def _assert_pixels_close_to_pillow(canvas: CanvasRenderer, pillow: PillowRenderer) -> None:
    differing = _different_channel_count(canvas.load_pixels(), pillow.load_pixels())
    # The first p5_canvas renderer is a deterministic software rasterizer but not
    # a byte-for-byte clone of Pillow's scan conversion/line joins. Keep the
    # tolerance small enough to catch major regressions while allowing edge-pixel
    # differences around primitive boundaries.
    assert differing / len(pillow.load_pixels()) < 0.08


def test_canvas_renderer_matches_pillow_for_core_primitives() -> None:
    canvas = CanvasRenderer(require_canvas_extension())
    pillow = PillowRenderer()
    canvas.resize(32, 32)
    pillow.resize(32, 32)

    style = StyleState(fill_color=Color(255, 0, 0, 255), stroke_color=Color(0, 0, 0, 255))
    style.stroke_weight = 2
    transform = Matrix2D.identity()

    for renderer in (canvas, pillow):
        renderer.background(Color(255, 255, 255, 255))
        renderer.point(4, 4, style, transform)
        renderer.line(0, 0, 31, 31, style, transform)
        renderer.polygon([(4, 24), (12, 12), (20, 24)], style, transform, close=True)
        renderer.ellipse(16, 4, 10, 8, style, transform)
        renderer.arc(20, 18, 10, 10, 0, 3.14, c.CHORD, style, transform)

    _assert_pixels_close_to_pillow(canvas, pillow)


def test_canvas_renderer_matches_pillow_for_pixel_density_and_transform() -> None:
    canvas = CanvasRenderer(require_canvas_extension())
    pillow = PillowRenderer()
    canvas.resize(16, 16, pixel_density=2)
    pillow.resize(16, 16, pixel_density=2)

    style = StyleState(fill_color=Color(0, 0, 255, 255), stroke_color=None)
    transform = Matrix2D.translation(2, 3).multiply(Matrix2D.rotation(0.2))

    for renderer in (canvas, pillow):
        renderer.clear()
        renderer.polygon([(2, 2), (8, 2), (8, 8), (2, 8)], style, transform, close=True)

    assert canvas.physical_width == pillow.physical_width == 32
    assert canvas.physical_height == pillow.physical_height == 32
    _assert_pixels_close_to_pillow(canvas, pillow)


def test_canvas_renderer_background_clear_and_invalid_arguments() -> None:
    canvas = CanvasRenderer(require_canvas_extension())
    canvas.resize(2, 1)

    canvas.background(Color(10, 20, 30, 255))
    assert canvas.load_pixels() == [10, 20, 30, 255, 10, 20, 30, 255]

    canvas.clear()
    assert canvas.load_pixels() == [0] * 8

    with pytest.raises(ValueError):
        # The Rust extension validates its own constructor arguments before the
        # Python backend maps them for user-facing calls.
        require_canvas_extension().Canvas(0, 1, 1.0, "headless", c.P2D)
