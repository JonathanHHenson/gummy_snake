"""Custom shape and curve drawing demo.

Interactive:
    uv run python examples/custom_shape.py

Headless/export:
    uv run python examples/custom_shape.py --headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/custom_shape.png")
EXPORT_CANVAS = False


def setup() -> None:
    p5.create_canvas(640, 420)


def draw() -> None:
    p5.background(252, 250, 245)

    p5.fill(96, 180, 155, 210)
    p5.stroke(30, 80, 75)
    p5.stroke_weight(4)
    p5.begin_shape()
    p5.vertex(90, 310)
    p5.vertex(150, 100)
    p5.quadratic_vertex(280, 40, 350, 170)
    p5.bezier_vertex(435, 330, 510, 80, 580, 300)
    p5.vertex(430, 350)
    p5.vertex(220, 330)
    p5.end_shape(p5.CLOSE)

    p5.no_fill()
    p5.stroke(231, 76, 60)
    p5.stroke_weight(5)
    p5.bezier(90, 80, 210, 200, 430, 10, 560, 140)

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
