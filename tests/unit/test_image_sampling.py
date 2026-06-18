from typing import cast

import p5


def _rgba_at(pixels: list[int], width: int, x: int, y: int) -> tuple[int, int, int, int]:
    offset = (y * width + x) * 4
    return cast(tuple[int, int, int, int], tuple(pixels[offset : offset + 4]))


def test_nearest_image_sampling_preserves_hard_edges_when_scaled():
    sprite = p5.create_image(2, 1)
    sprite.set(0, 0, (255, 0, 0, 255))
    sprite.set(1, 0, (0, 255, 0, 255))

    def setup():
        p5.create_canvas(4, 2)
        p5.clear()
        p5.no_smooth()

    def draw():
        p5.image(sprite, 0, 0, 4, 2)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()

    assert _rgba_at(pixels, 4, 0, 0) == (255, 0, 0, 255)
    assert _rgba_at(pixels, 4, 1, 0) == (255, 0, 0, 255)
    assert _rgba_at(pixels, 4, 2, 0) == (0, 255, 0, 255)
    assert _rgba_at(pixels, 4, 3, 0) == (0, 255, 0, 255)
