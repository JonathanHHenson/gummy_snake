"""A first p5-py sketch with common 2D primitives."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/01_getting_started/basic_shapes.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(640, 420, pixel_density=2)
    p5.frame_rate(30)
    p5.describe("A canvas showing basic p5-py shape primitives.")


def draw() -> None:
    p5.background(248, 247, 242)
    p5.stroke(28, 34, 48)
    p5.stroke_weight(3)

    p5.fill(231, 76, 60)
    p5.rect(54, 58, 140, 92)

    p5.fill(247, 183, 49)
    p5.circle(310, 104, 112)

    p5.fill(40, 180, 155)
    p5.triangle(478, 164, 560, 52, 620, 164)

    p5.no_fill()
    p5.stroke(38, 92, 222)
    p5.stroke_weight(6)
    p5.line(70, 260, 214, 352)
    p5.arc(312, 305, 132, 116, 0.15, 5.3, p5.PIE)

    p5.no_stroke()
    p5.fill(95, 72, 178, 190)
    p5.quad(442, 250, 580, 232, 610, 348, 418, 362)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
