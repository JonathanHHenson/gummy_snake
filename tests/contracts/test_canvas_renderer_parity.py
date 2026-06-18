from __future__ import annotations

import math

import pytest

from p5 import constants as c
from p5.assets.image import Image
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


def test_canvas_renderer_draws_images_and_blend_regions() -> None:
    from PIL import Image as PILImage

    canvas = CanvasRenderer(require_canvas_extension())
    pillow = PillowRenderer()
    canvas.resize(8, 4)
    pillow.resize(8, 4)
    source = PILImage.new("RGBA", (2, 1), (0, 255, 0, 255))
    source.putpixel((0, 0), (255, 0, 0, 255))
    image = Image(source)
    style = StyleState(fill_color=None, stroke_color=None, image_sampling=c.NEAREST)
    transform = Matrix2D.identity()

    for renderer, blend_source in ((canvas, image), (pillow, image.pillow)):
        renderer.background(Color(10, 20, 30, 255))
        renderer.draw_image(image, 0, 0, 4, 2, style, transform)
        renderer.blend_region(blend_source, (0, 0, 1, 1), (6, 0, 1, 1), c.ADD)

    assert canvas.load_pixels() == pillow.load_pixels()


def test_canvas_renderer_draws_transformed_images() -> None:
    from PIL import Image as PILImage

    canvas = CanvasRenderer(require_canvas_extension())
    pillow = PillowRenderer()
    canvas.resize(20, 20)
    pillow.resize(20, 20)
    image = Image(PILImage.new("RGBA", (4, 2), (255, 0, 0, 255)))
    style = StyleState(fill_color=None, stroke_color=None, image_sampling=c.NEAREST)
    transform = Matrix2D.translation(10, 10).multiply(Matrix2D.rotation(math.pi / 2))

    for renderer in (canvas, pillow):
        renderer.clear()
        renderer.draw_image(image, -2, -1, 4, 2, style, transform)

    assert canvas.load_pixels() == pillow.load_pixels()


def test_canvas_renderer_supports_blend_modes_and_erase() -> None:
    canvas = CanvasRenderer(require_canvas_extension())
    canvas.resize(4, 1)
    transform = Matrix2D.identity()
    base_style = StyleState(fill_color=Color(100, 100, 100, 255), stroke_color=None)
    multiply_style = StyleState(
        fill_color=Color(128, 255, 255, 255),
        stroke_color=None,
        blend_mode=c.MULTIPLY,
    )
    erase_style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None, erasing=True)

    canvas.polygon([(0, 0), (4, 0), (4, 1), (0, 1)], base_style, transform, close=True)
    canvas.polygon([(0, 0), (1, 0), (1, 1), (0, 1)], multiply_style, transform, close=True)
    canvas.polygon([(3, 0), (4, 0), (4, 1), (3, 1)], erase_style, transform, close=True)

    pixels = canvas.load_pixels()
    assert pixels[0:4] == [50, 100, 100, 255]
    assert pixels[12:16] == [100, 100, 100, 0]


def test_canvas_renderer_text_uses_native_rust_metrics_and_draw_command() -> None:
    canvas = CanvasRenderer(require_canvas_extension())
    canvas.resize(48, 24)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)

    assert canvas.text_width("Hi", style) > 0
    assert canvas.text_width("Hi\nHello", style) >= canvas.text_width("Hi", style)
    assert canvas.text_ascent(style) > 0
    assert canvas.text_descent(style) >= 0
    canvas.clear()
    canvas.text("Hi", 2, 14, style, Matrix2D.identity())

    pixels = canvas.load_pixels()
    assert any(alpha > 0 for alpha in pixels[3::4])
    assert any(r > 0 and g > 0 and b > 0 for r, g, b, _ in zip(*[iter(pixels)] * 4, strict=True))
