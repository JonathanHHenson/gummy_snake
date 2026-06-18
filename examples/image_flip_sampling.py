"""Sprite flipping and image sampling demo.

Interactive:
    uv run python examples/image_flip_sampling.py --interactive

Headless/export:
    uv run python examples/image_flip_sampling.py --headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/image_flip_sampling.png")
EXPORT_CANVAS = False
SPRITE: p5.Image | None = None


def make_sprite() -> p5.Image:
    sprite = p5.create_image(8, 8)
    transparent = p5.Color(0, 0, 0, 0)
    navy = p5.Color(20, 28, 48, 255)
    cyan = p5.Color(86, 207, 225, 255)
    gold = p5.Color(255, 201, 79, 255)
    coral = p5.Color(255, 111, 97, 255)
    white = p5.Color(245, 247, 250, 255)

    pixels = [
        "........",
        "..nnnn..",
        ".nccccn.",
        ".nwyygc.",
        ".ncorrc.",
        ".nccccn.",
        "..nggn..",
        "........",
    ]
    palette = {
        ".": transparent,
        "n": navy,
        "c": cyan,
        "g": gold,
        "o": coral,
        "r": white,
        "w": white,
        "y": gold,
    }

    for y, row in enumerate(pixels):
        for x, key in enumerate(row):
            sprite.set(x, y, palette[key])
    return sprite


def setup() -> None:
    global SPRITE
    p5.create_canvas(760, 320)
    p5.no_stroke()
    p5.text_size(16)
    SPRITE = make_sprite()


def _draw_panel(x: float, title: str, sampling: str, *, flipped: bool) -> None:
    if SPRITE is None:
        return

    panel_y = 86
    card_w = 150
    card_h = 188
    center_x = x + card_w / 2

    p5.fill(255, 255, 255, 230)
    p5.rect(x, panel_y, card_w, card_h)

    p5.fill(33, 37, 41)
    p5.text(title, x, 44)
    p5.fill(90, 96, 105)
    p5.text(f"sampling={sampling}", x, 64)

    p5.image_sampling(sampling)
    p5.image_mode(p5.CENTER)

    p5.fill(226, 232, 240)
    p5.rect(x + 18, panel_y + 18, 114, 114)

    if flipped:
        with p5.pushed():
            p5.translate(center_x, panel_y + 75)
            p5.scale(-1, 1)
            p5.image(SPRITE, 0, 0, 96, 96)
    else:
        p5.image(SPRITE, center_x, panel_y + 75, 96, 96)

    p5.fill(90, 96, 105)
    p5.text("native 8x scale", x + 24, panel_y + 150)

    p5.fill(226, 232, 240)
    p5.rect(x + 46, panel_y + 158, 56, 56)
    if flipped:
        with p5.pushed():
            p5.translate(center_x, panel_y + 186)
            p5.scale(-1, 1)
            p5.image(SPRITE, 0, 0, 32, 32)
    else:
        p5.image(SPRITE, center_x, panel_y + 186, 32, 32)


def draw() -> None:
    p5.background(243, 244, 246)

    p5.fill(24, 24, 27)
    p5.text_size(26)
    p5.text("image() flip + sampling", 24, 34)
    p5.text_size(14)
    p5.fill(82, 82, 91)
    p5.text("Left: interpolated scaling. Right: crisp pixel-art scaling.", 24, 58)

    _draw_panel(24, "Original, linear", p5.LINEAR, flipped=False)
    _draw_panel(208, "Flipped, linear", p5.LINEAR, flipped=True)
    _draw_panel(392, "Original, nearest", p5.NEAREST, flipped=False)
    _draw_panel(576, "Flipped, nearest", p5.NEAREST, flipped=True)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()

    global EXPORT_CANVAS
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
