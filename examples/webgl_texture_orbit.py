"""Textured WEBGL-style box demo with optional orbit controls.

Headless/export:
    uv run python examples/webgl_texture_orbit.py --headless --frames 1

Interactive:
    uv run python examples/webgl_texture_orbit.py --interactive
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

OUTPUT = Path("examples/output/webgl_texture_orbit.png")
HEADLESS = None
EXPORT_CANVAS = False
TEXTURE = None


def make_checkerboard(size: int = 64, cell: int = 8):
    image = p5.create_image(size, size)
    for y in range(size):
        for x in range(size):
            even = ((x // cell) + (y // cell)) % 2 == 0
            color = p5.Color(242, 120, 116, 255) if even else p5.Color(104, 210, 255, 255)
            image.set(x, y, color)
    return image


def setup() -> None:
    global TEXTURE

    p5.create_canvas(720, 480, p5.WEBGL)
    p5.no_stroke()
    p5.camera(0, -36, 260, 0, 0, 0, 0, 1, 0)
    p5.perspective(math.pi / 3, 720 / 480, 0.1, 2000)
    p5.frame_rate(30)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TEXTURE = make_checkerboard()


def draw() -> None:
    p5.background(10, 14, 26)
    p5.ambient_light(90)
    p5.directional_light(255, 255, 255, -0.3, -0.6, -1.0)

    if HEADLESS is not False:
        orbit = p5.frame_count() * 0.06
        p5.camera(math.sin(orbit) * 180.0, -40.0, math.cos(orbit) * 220.0, 0, 0, 0, 0, 1, 0)
    else:
        p5.orbit_control()

    if TEXTURE is not None:
        p5.texture(TEXTURE)
    p5.box(140)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=1)
    args = parser.parse_args()

    global HEADLESS, EXPORT_CANVAS
    HEADLESS = args.headless
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
