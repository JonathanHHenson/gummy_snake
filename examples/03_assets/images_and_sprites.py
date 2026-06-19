"""Load image assets, use image modes, smoothing, and sprite transforms."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/03_assets/images_and_sprites.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
SHIP: p5.Image | None = None
UFO: p5.Image | None = None
METEOR: p5.Image | None = None
SHIELD: p5.Image | None = None


def preload() -> None:
    global SHIP, UFO, METEOR, SHIELD
    SHIP = p5.load_image(ASSETS / "playerShip1_blue.png")
    UFO = p5.load_image(ASSETS / "ufoBlue.png")
    METEOR = p5.load_image(ASSETS / "Meteors/meteorGrey_big1.png")
    SHIELD = p5.load_image(ASSETS / "Effects/shield3.png")


def setup() -> None:
    p5.create_canvas(760, 420)
    p5.image_mode(p5.CENTER)
    p5.no_smooth()


def draw() -> None:
    assert SHIP is not None and UFO is not None and METEOR is not None and SHIELD is not None
    p5.background(9, 13, 28)
    for i in range(70):
        p5.stroke(140 + i % 80, 160, 210, 160)
        p5.point((i * 97) % 760, (i * 53) % 420)

    p5.no_stroke()
    with p5.pushed():
        p5.translate(190, 210)
        p5.rotate(-0.28 + math.sin(p5.frame_count() * 0.04) * 0.08)
        p5.image(SHIELD, 0, 0, 142, 142)
        p5.image(SHIP, 0, 0, 104, 78)

    p5.image(UFO, 520, 134, 130, 94)
    p5.image(METEOR, 545, 285, 128, 128)
    p5.fill(238)
    p5.text_size(16)
    p5.text(f"ship asset: {SHIP.width}x{SHIP.height}", 32, 36)
    p5.text("image_mode(CENTER), no_smooth(), transformed draw", 32, 392)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
