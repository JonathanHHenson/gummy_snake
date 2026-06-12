"""Basic 2D drawing primitives.

Interactive:
    uv run python examples/basic_shapes.py

Headless/export:
    uv run python examples/basic_shapes.py --backend headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5_py as p5

OUTPUT = Path("examples/output/basic_shapes.png")


def setup() -> None:
    p5.create_canvas(640, 420)
    p5.frame_rate(30)


def draw() -> None:
    p5.background(248, 246, 240)

    p5.stroke(30)
    p5.stroke_weight(3)

    p5.fill(244, 91, 105)
    p5.rect(60, 70, 140, 90)

    p5.fill(255, 196, 61)
    p5.circle(300, 115, 110)

    p5.fill(75, 192, 192)
    p5.triangle(470, 170, 550, 60, 610, 170)

    p5.no_fill()
    p5.stroke(45, 88, 255)
    p5.stroke_weight(6)
    p5.line(70, 260, 210, 350)
    p5.arc(300, 300, 120, 120, 0, 5.2, p5.PIE)

    p5.fill(120, 80, 200, 180)
    p5.no_stroke()
    p5.quad(445, 250, 585, 235, 610, 345, 420, 360)

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
