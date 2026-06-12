"""Custom shape and curve drawing demo.

Interactive:
    uv run python examples/custom_shape.py

Headless/export:
    uv run python examples/custom_shape.py --backend headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5_py as p5

OUTPUT = Path("examples/output/custom_shape.png")


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

    if p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="pyglet", choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
