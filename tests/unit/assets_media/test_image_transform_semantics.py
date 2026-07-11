import math
from collections.abc import Sequence

import gummysnake as gs


def _alpha_bbox(
    pixels: Sequence[int], width: int, *, threshold: int = 128
) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for index in range(0, len(pixels), 4):
        if pixels[index + 3] > threshold:
            pixel = index // 4
            xs.append(pixel % width)
            ys.append(pixel // width)
    return min(xs), min(ys), max(xs), max(ys)


def test_image_mode_center_rotation_uses_center_pivot_for_non_square_sprite():
    sprite = gs.create_image(4, 2)
    for y in range(2):
        for x in range(4):
            sprite.set(x, y, (255, 0, 0, 255))

    def setup():
        gs.create_canvas(20, 20)
        gs.clear()
        gs.image_mode(gs.CENTER)
        gs.translate(10, 10)
        gs.rotate(math.pi / 2)
        gs.image(sprite, 0, 0, 4, 2)

    context = gs.run(setup=setup, headless=True, max_frames=0)

    assert _alpha_bbox(context.load_pixels(), 20) == (9, 8, 10, 11)


def test_transformed_scaled_source_crop_uses_destination_rect_and_source_rect():
    sprite = gs.create_image(4, 2)
    for x in range(4):
        for y in range(2):
            sprite.set(x, y, (0, 255, 0, 255))
    for x in range(2):
        for y in range(2):
            sprite.set(x, y, (255, 0, 0, 255))

    def setup():
        gs.create_canvas(20, 20)
        gs.clear()
        gs.image_mode(gs.CENTER)
        gs.translate(10, 10)
        gs.rotate(math.pi / 2)
        gs.image(sprite, 0, 0, 4, 4, 0, 0, 2, 2)

    context = gs.run(setup=setup, headless=True, max_frames=0)
    pixels = context.load_pixels()
    opaque = [
        tuple(pixels[index : index + 4]) for index in range(0, len(pixels), 4) if pixels[index + 3]
    ]

    assert opaque
    assert all(red > green for red, green, _blue, _alpha in opaque)
    assert _alpha_bbox(pixels, 20) == (8, 8, 11, 11)


def test_image_mode_corners_honors_active_transform():
    sprite = gs.create_image(2, 2)
    for y in range(2):
        for x in range(2):
            sprite.set(x, y, (0, 0, 255, 255))

    def setup():
        gs.create_canvas(20, 20)
        gs.clear()
        gs.image_mode(gs.CORNERS)
        gs.translate(6, 5)
        gs.image(sprite, 0, 0, 4, 3)

    context = gs.run(setup=setup, headless=True, max_frames=0)

    assert _alpha_bbox(context.load_pixels(), 20) == (6, 5, 9, 7)
