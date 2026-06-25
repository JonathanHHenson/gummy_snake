from pathlib import Path
from typing import cast

import pytest

import gummysnake as gs
from gummysnake.core.color import Color
from gummysnake.exceptions import ArgumentValidationError


def test_pixels_round_trip_and_pixel_array_include_physical_density():
    def setup():
        gs.create_canvas(2, 1, pixel_density=2)
        gs.background(0, 0, 0, 255)

    context = gs.run(setup=setup, headless=True, max_frames=0)

    pixels = context.load_pixels()
    assert len(pixels) == 4 * 2 * 1 * 2 * 2
    pixels[0:4] = [255, 0, 0, 255]
    context.update_pixels()

    assert context.load_pixels()[0:4] == [255, 0, 0, 255]
    assert context.pixel_array()[0][0] == (255, 0, 0, 255)


def test_update_pixels_accepts_bytes_buffer():
    def setup():
        gs.create_canvas(2, 1)

    context = gs.run(setup=setup, headless=True, max_frames=0)

    context.update_pixels(bytes([255, 0, 0, 255, 0, 0, 255, 255]))

    assert context.load_pixels() == [255, 0, 0, 255, 0, 0, 255, 255]


def test_load_pixel_bytes_and_update_pixels_accept_memoryview():
    def setup():
        gs.create_canvas(2, 1)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    payload = bytes([10, 20, 30, 255, 40, 50, 60, 255])

    context.update_pixels(memoryview(payload))

    context.pixels = []
    assert context.load_pixel_bytes() == payload
    assert context.pixels == []
    assert gs.run(setup=setup, headless=True, max_frames=0).load_pixel_bytes() == bytes(8)


def test_canvas_get_set_copy_and_filter_helpers():
    def setup():
        gs.create_canvas(3, 2)
        gs.background(0, 0, 0, 255)
        gs.set(1, 0, gs.Color(10, 20, 30, 255))
        assert gs.get(1, 0) == gs.Color(10, 20, 30, 255)
        region = gs.get(1, 0, 1, 1)
        assert isinstance(region, gs.Image)
        gs.copy(1, 0, 1, 1, 2, 1, 1, 1)
        assert gs.get(2, 1) == gs.Color(10, 20, 30, 255)
        gs.filter(gs.INVERT)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    assert context.get(2, 1) == gs.Color(245, 235, 225, 255)


def test_canvas_region_apis_use_physical_hidpi_regions():
    def setup():
        gs.create_canvas(2, 2, pixel_density=2)
        gs.background(0, 0, 0, 255)
        gs.set(1, 1, gs.Color(12, 34, 56, 255))

    context = gs.run(setup=setup, headless=True, max_frames=0)

    assert context.get(1, 1) == gs.Color(12, 34, 56, 255)
    region = context.get(1, 1, 1, 1)
    assert isinstance(region, gs.Image)
    assert (region.width, region.height) == (2, 2)
    assert region.to_rgba_bytes() == bytes(
        [12, 34, 56, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255]
    )


def test_gpu_queued_text_preserves_pixels_from_update_pixels():
    def setup():
        gs.create_canvas(8, 8)
        gs.text_size(8)

    def draw():
        gs.update_pixels(bytes([10, 20, 30, 255] * 64))
        gs.fill(255)
        gs.text("x", 1, 7)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context.load_pixels()[0:4] == [10, 20, 30, 255]


def test_save_canvas_adds_default_extension_and_validates_overwrite(tmp_path):
    def setup():
        gs.create_canvas(3, 2)
        gs.background(10, 20, 30)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    output = context.save_canvas(tmp_path / "canvas")

    assert output.suffix == ".png"
    image = gs.load_image(output)
    assert (image.width, image.height) == (3, 2)
    pixel = image.get(0, 0)
    assert isinstance(pixel, Color)
    assert pixel.to_tuple() == (10, 20, 30, 255)

    with pytest.raises(ArgumentValidationError, match="Refusing to overwrite"):
        context.save_canvas(output, overwrite=False)


def test_save_gif_uses_canvas_runtime_and_preserves_public_contract(tmp_path):
    def setup():
        gs.create_canvas(2, 1)
        gs.background(10, 20, 30)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    output = context.save_gif(tmp_path / "anim", count=3, duration=1.2)

    assert output == tmp_path / "anim.gif"
    assert output.read_bytes().startswith(b"GIF")

    with pytest.raises(ArgumentValidationError, match="count must be positive"):
        context.save_gif(tmp_path / "bad.gif", count=0)
    with pytest.raises(ArgumentValidationError, match="Refusing to overwrite"):
        context.save_gif(output, overwrite=False)


def test_save_frames_exports_numbered_sequence_and_callback(tmp_path):
    callback_results = []

    def setup():
        gs.create_canvas(2, 1)
        gs.background(10, 20, 30)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    results = context.save_frames(
        tmp_path / "frame",
        count=2,
        callback=callback_results.append,
    )

    assert [result["frame"] for result in results] == [0, 1]
    paths = [cast(Path, result["path"]) for result in results]
    assert [path.name for path in paths] == [
        "frame_0000.png",
        "frame_0001.png",
    ]
    assert all(path.exists() for path in paths)
    assert callback_results == [results]


def test_blend_mode_multiply_and_erase_affect_subsequent_drawing():
    def setup():
        gs.create_canvas(4, 1)
        gs.no_stroke()
        gs.background(100, 100, 100, 255)
        gs.blend_mode(gs.MULTIPLY)
        gs.fill(128, 255, 255, 255)
        gs.rect(0, 0, 1, 1)
        gs.blend_mode(gs.BLEND)
        gs.erase()
        gs.fill(255, 255, 255, 255)
        gs.rect(3, 0, 1, 1)
        gs.no_erase()

    context = gs.run(setup=setup, headless=True, max_frames=0)
    pixels = context.load_pixels()

    assert pixels[0:4] == [50, 100, 100, 255]
    assert pixels[12:16] == [100, 100, 100, 0]


def test_blend_region_can_copy_canvas_region_with_add_mode():
    def setup():
        gs.create_canvas(4, 1)
        gs.no_stroke()
        gs.background(10, 20, 30, 255)
        gs.fill(10, 0, 0, 255)
        gs.rect(0, 0, 1, 1)
        gs.blend(0, 0, 1, 1, 3, 0, 1, 1, gs.ADD)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    pixels = context.load_pixels()

    assert pixels[12:16] == [20, 20, 30, 255]


def test_blend_region_scales_destination_for_physical_density():
    source = gs.create_image(2, 2)
    for y in range(2):
        for x in range(2):
            source.set(x, y, (255, 0, 0, 255))

    def setup():
        gs.create_canvas(4, 4, pixel_density=2)
        gs.background(0, 0, 0, 255)
        gs.blend(source, 0, 0, 2, 2, 1, 1, 1, 1, gs.BLEND)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    pixels = context.load_pixels()

    def pixel_at(x: int, y: int) -> list[int]:
        offset = (y * context.state.canvas.physical_width + x) * 4
        return pixels[offset : offset + 4]

    assert pixel_at(1, 1) == [0, 0, 0, 255]
    assert pixel_at(2, 2) == [255, 0, 0, 255]
    assert pixel_at(3, 3) == [255, 0, 0, 255]
