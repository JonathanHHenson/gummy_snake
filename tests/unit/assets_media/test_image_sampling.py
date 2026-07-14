from collections.abc import Sequence
from typing import cast

import gummysnake as gs


def _rgba_at(pixels: Sequence[int], width: int, x: int, y: int) -> tuple[int, int, int, int]:
    offset = (y * width + x) * 4
    return cast(tuple[int, int, int, int], tuple(pixels[offset : offset + 4]))


def test_nearest_image_sampling_preserves_hard_edges_when_scaled():
    sprite = gs.create_image(2, 1)
    sprite.set(0, 0, (255, 0, 0, 255))
    sprite.set(1, 0, (0, 255, 0, 255))

    def setup():
        gs.create_canvas(4, 2)
        gs.clear()
        gs.no_smooth()

    def draw():
        gs.image(sprite, 0, 0, 4, 2)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()

    assert _rgba_at(pixels, 4, 0, 0) == (255, 0, 0, 255)
    assert _rgba_at(pixels, 4, 1, 0) == (255, 0, 0, 255)
    assert _rgba_at(pixels, 4, 2, 0) == (0, 255, 0, 255)
    assert _rgba_at(pixels, 4, 3, 0) == (0, 255, 0, 255)


def test_linear_image_sampling_interpolates_when_scaled():
    sprite = gs.create_image(2, 1)
    sprite.set(0, 0, (0, 0, 0, 255))
    sprite.set(1, 0, (255, 255, 255, 255))

    def setup():
        gs.create_canvas(4, 1)
        gs.clear()
        gs.smooth()

    def draw():
        gs.image(sprite, 0, 0, 4, 1)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()

    assert _rgba_at(pixels, 4, 0, 0) == (0, 0, 0, 255)
    assert _rgba_at(pixels, 4, 1, 0) == (64, 64, 64, 255)
    assert _rgba_at(pixels, 4, 2, 0) == (191, 191, 191, 255)
    assert _rgba_at(pixels, 4, 3, 0) == (255, 255, 255, 255)
    assert context.renderer_performance_counters()["image_atlas_resident_bytes"] > 0
