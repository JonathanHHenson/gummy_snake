"""Load image assets, use image modes, smoothing, and sprite transforms."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/03_assets/images_and_sprites.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
SHIP: gs.Image | None = None
UFO: gs.Image | None = None
METEOR: gs.Image | None = None
SHIELD: gs.Image | None = None


@gs.preload
async def preload() -> None:
    global SHIP, UFO, METEOR, SHIELD
    SHIP = await gs.load_image_async(ASSETS / "playerShip1_blue.png")
    UFO = await gs.load_image_async(ASSETS / "ufoBlue.png")
    METEOR = await gs.load_image_async(ASSETS / "Meteors/meteorGrey_big1.png")
    SHIELD = await gs.load_image_async(ASSETS / "Effects/shield3.png")


@gs.setup
def setup() -> None:
    gs.create_canvas(760, 420)
    gs.image_mode(gs.CENTER)
    gs.no_smooth()


@gs.draw
def draw() -> None:
    assert SHIP is not None and UFO is not None and METEOR is not None and SHIELD is not None
    gs.background(9, 13, 28)
    for i in range(70):
        gs.stroke(140 + i % 80, 160, 210, 160)
        gs.point((i * 97) % 760, (i * 53) % 420)

    gs.no_stroke()
    with gs.transform(
        translate=gs.Vector(190, 210),
        rotate=-0.28 + math.sin(gs.current.frame_count * 0.04) * 0.08,
    ):
        gs.image(SHIELD, 0, 0, 142, 142)
        gs.image(SHIP, 0, 0, 104, 78)

    gs.image(UFO, 520, 134, 130, 94)
    gs.image(METEOR, 545, 285, 128, 128)
    gs.fill(238)
    gs.text_size(16)
    gs.text(f"ship asset: {SHIP.width}x{SHIP.height}", 32, 36)
    gs.text("image_mode(CENTER), no_smooth(), transformed draw", 32, 392)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
