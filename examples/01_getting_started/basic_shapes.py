"""A first Gummy Snake sketch with common 2D primitives."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/01_getting_started/basic_shapes.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


@gs.setup
def setup() -> None:
    gs.create_canvas(640, 420, pixel_density=2)
    gs.frame_rate(30)
    gs.describe("A canvas showing basic Gummy Snake shape primitives.")


@gs.draw
def draw() -> None:
    gs.background(248, 247, 242)

    with gs.style(stroke=(28, 34, 48), stroke_weight=3):
        with gs.style(fill=(231, 76, 60)):
            gs.rect(54, 58, 140, 92)

        with gs.style(fill=(247, 183, 49)):
            gs.circle(310, 104, 112)

        with gs.style(fill=(40, 180, 155)):
            gs.triangle(gs.Vector(478, 164), gs.Vector(560, 52), gs.Vector(620, 164))

    with gs.style(fill=None, stroke=(38, 92, 222), stroke_weight=6):
        gs.line(gs.Vector(70, 260), gs.Vector(214, 352))
        gs.arc(312, 305, 132, 116, 0.15, 5.3, gs.PIE)

    with gs.style(fill=(95, 72, 178, 190), stroke=None):
        gs.quad(
            gs.Vector(442, 250),
            gs.Vector(580, 232),
            gs.Vector(610, 348),
            gs.Vector(418, 362),
        )

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
