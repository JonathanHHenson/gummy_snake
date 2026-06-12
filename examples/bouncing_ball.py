"""A simple animated bouncing ball.

Interactive:
    uv run python examples/bouncing_ball.py

Headless smoke run:
    uv run python examples/bouncing_ball.py --backend headless --frames 5
"""

from __future__ import annotations

import argparse

import p5_py as p5

x = 80.0
y = 80.0
vx = 4.0
vy = 3.0
radius = 28.0


def setup() -> None:
    p5.create_canvas(640, 360)
    p5.frame_rate(60)


def draw() -> None:
    global vx, vy, x, y

    p5.background(18, 24, 38)

    x += vx
    y += vy

    if x < radius or x > p5.width() - radius:
        vx *= -1
    if y < radius or y > p5.height() - radius:
        vy *= -1

    p5.no_stroke()
    p5.fill(255, 203, 107)
    p5.circle(x, y, radius * 2)

    p5.stroke(255, 255, 255, 80)
    p5.stroke_weight(2)
    p5.line(0, p5.height() - 30, p5.width(), p5.height() - 30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="pyglet", choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
