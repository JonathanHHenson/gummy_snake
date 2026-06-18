"""Image and text coverage demo for the Rust canvas backend."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

ASSET_DIR = Path("examples/assets")
DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_assets_text.png")
EXPORT_CANVAS = True
OUTPUT = DEFAULT_OUTPUT

SHIP: p5.Image | None = None
METEOR: p5.Image | None = None
LASER: p5.Image | None = None


def setup() -> None:
    global SHIP, METEOR, LASER
    p5.create_canvas(640, 360)
    p5.frame_rate(60)
    p5.image_mode(p5.CENTER)
    SHIP = p5.load_image(ASSET_DIR / "playerShip1_blue.png")
    METEOR = p5.load_image(ASSET_DIR / "Meteors/meteorGrey_big1.png")
    LASER = p5.load_image(ASSET_DIR / "Lasers/laserBlue01.png")


def draw() -> None:
    p5.background(12, 18, 38)
    p5.no_stroke()
    for index in range(80):
        x = (index * 83 + p5.frame_count() * (1 + index % 3)) % p5.width()
        y = (index * 47 + index * index) % p5.height()
        p5.fill(210, 226, 255, 120 + (index % 4) * 28)
        p5.circle(x, y, 1 + index % 3)

    if METEOR is not None:
        for index in range(5):
            with p5.pushed():
                p5.translate(96 + index * 104, 130 + math.sin(index + p5.frame_count() * 0.02) * 18)
                p5.rotate(index * 0.7 + p5.frame_count() * 0.015)
                p5.image(METEOR, 0, 0, 62, 62)

    if SHIP is not None:
        with p5.pushed():
            p5.translate(320, 232)
            p5.rotate(math.sin(p5.frame_count() * 0.04) * 0.35)
            p5.image(SHIP, 0, 0, 96, 72)

    if LASER is not None:
        for index in range(6):
            with p5.pushed():
                p5.translate(180 + index * 58, 285 - index % 2 * 18)
                p5.rotate(math.pi / 2)
                p5.image(LASER, 0, 0, 10, 30)

    p5.fill(255, 255, 255, 235)
    p5.text_size(18)
    p5.text("canvas image + text path", 28, 34)
    p5.text_size(13)
    p5.text(f"frame {p5.frame_count()}  text width {p5.text_width('canvas'):.1f}", 28, 58)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global EXPORT_CANVAS, OUTPUT
    OUTPUT = args.output
    EXPORT_CANVAS = not args.no_save and args.frames is not None and args.frames > 0
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
