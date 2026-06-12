import pytest
from PIL import Image as PILImage

import p5_py as p5
from p5_py.backends.pillow import PillowRenderer
from p5_py.core.color import Color
from p5_py.exceptions import ArgumentValidationError


def test_pixels_round_trip_and_pixel_array_include_physical_density():
    def setup():
        p5.create_canvas(2, 1, pixel_density=2)
        p5.background(0, 0, 0, 255)

    context = p5.run(setup=setup, backend="headless", max_frames=0)

    pixels = context.load_pixels()
    assert len(pixels) == 4 * 2 * 1 * 2 * 2
    pixels[0:4] = [255, 0, 0, 255]
    context.update_pixels()

    assert context.load_pixels()[0:4] == [255, 0, 0, 255]
    assert context.pixel_array()[0][0] == (255, 0, 0, 255)


def test_save_canvas_adds_default_extension_and_validates_overwrite(tmp_path):
    def setup():
        p5.create_canvas(3, 2)
        p5.background(10, 20, 30)

    context = p5.run(setup=setup, backend="headless", max_frames=0)
    output = context.save_canvas(tmp_path / "canvas")

    assert output.suffix == ".png"
    with PILImage.open(output) as image:
        assert image.size == (3, 2)
        assert image.getpixel((0, 0)) == (10, 20, 30, 255)

    with pytest.raises(ArgumentValidationError, match="Refusing to overwrite"):
        context.save_canvas(output, overwrite=False)


def test_blend_mode_multiply_and_erase_affect_subsequent_drawing():
    def setup():
        p5.create_canvas(4, 1)
        p5.no_stroke()
        p5.background(100, 100, 100, 255)
        p5.blend_mode(p5.MULTIPLY)
        p5.fill(128, 255, 255, 255)
        p5.rect(0, 0, 1, 1)
        p5.blend_mode(p5.BLEND)
        p5.erase()
        p5.fill(255, 255, 255, 255)
        p5.rect(3, 0, 1, 1)
        p5.no_erase()

    context = p5.run(setup=setup, backend="headless", max_frames=0)
    pixels = context.load_pixels()

    assert pixels[0:4] == [50, 100, 100, 255]
    assert pixels[12:16] == [100, 100, 100, 0]


def test_blend_region_can_copy_canvas_region_with_add_mode():
    def setup():
        p5.create_canvas(4, 1)
        p5.no_stroke()
        p5.background(10, 20, 30, 255)
        p5.fill(10, 0, 0, 255)
        p5.rect(0, 0, 1, 1)
        p5.blend(0, 0, 1, 1, 3, 0, 1, 1, p5.ADD)

    context = p5.run(setup=setup, backend="headless", max_frames=0)
    pixels = context.load_pixels()

    assert pixels[12:16] == [20, 20, 30, 255]


def test_blend_region_scales_destination_for_physical_density():
    renderer = PillowRenderer(4, 4, pixel_density=2)
    source = PILImage.new("RGBA", (2, 2), (255, 0, 0, 255))
    renderer.background(Color(0, 0, 0, 255))

    renderer.blend_region(source, (0, 0, 2, 2), (1, 1, 1, 1), p5.BLEND)
    pixels = renderer.load_pixels()

    def pixel_at(x: int, y: int) -> list[int]:
        offset = (y * renderer.physical_width + x) * 4
        return pixels[offset : offset + 4]

    assert pixel_at(1, 1) == [0, 0, 0, 255]
    assert pixel_at(2, 2) == [255, 0, 0, 255]
    assert pixel_at(3, 3) == [255, 0, 0, 255]
