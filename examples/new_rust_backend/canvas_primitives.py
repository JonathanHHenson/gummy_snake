"""Core 2D primitive demo for the experimental Rust canvas backend.

Run with the Rust canvas backend:
    uv run python examples/new_rust_backend/canvas_primitives.py --frames 1

Compare against Pillow/headless:
    uv run python examples/new_rust_backend/canvas_primitives.py --backend headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/new_rust_backend/canvas_primitives.png")
EXPORT_CANVAS = False


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.frame_rate(1)


def draw() -> None:
    p5.background(246, 244, 238)

    draw_reference_grid()
    draw_filled_shapes()
    draw_stroked_primitives()
    draw_arcs()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def draw_reference_grid() -> None:
    p5.stroke(220, 216, 208)
    p5.stroke_weight(1)
    for x in range(0, p5.width() + 1, 40):
        p5.line(x, 0, x, p5.height())
    for y in range(0, p5.height() + 1, 40):
        p5.line(0, y, p5.width(), y)


def draw_filled_shapes() -> None:
    p5.stroke(35, 35, 35)
    p5.stroke_weight(3)

    p5.fill(244, 91, 105)
    p5.rect(60, 70, 130, 90)

    p5.fill(255, 196, 61)
    p5.circle(285, 115, 112)

    p5.fill(75, 192, 192)
    p5.triangle(420, 170, 500, 60, 580, 170)

    p5.fill(106, 76, 147, 190)
    p5.quad(76, 245, 218, 230, 248, 342, 48, 360)


def draw_stroked_primitives() -> None:
    p5.no_fill()
    p5.stroke(34, 88, 255)
    p5.stroke_weight(7)
    p5.line(300, 245, 520, 345)

    p5.stroke(20, 145, 110)
    p5.stroke_weight(10)
    for index in range(12):
        p5.point(600 + index * 8, 245 + (index % 3) * 18)

    p5.stroke(30)
    p5.stroke_weight(2)
    p5.fill(255, 255, 255, 170)
    p5.ellipse(615, 330, 128, 64)


def draw_arcs() -> None:
    p5.stroke(35)
    p5.stroke_weight(4)

    p5.fill(255, 160, 64, 210)
    p5.arc(250, 255, 95, 95, 0.0, 4.8, p5.PIE)

    p5.fill(90, 190, 255, 180)
    p5.arc(370, 255, 95, 95, 0.4, 5.6, p5.CHORD)

    p5.no_fill()
    p5.stroke(230, 70, 120)
    p5.stroke_weight(6)
    p5.arc(490, 255, 95, 95, 0.2, 5.3, p5.OPEN)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.CANVAS, choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=1)
    args = parser.parse_args()

    global EXPORT_CANVAS
    EXPORT_CANVAS = args.backend in {p5.CANVAS, p5.HEADLESS, p5.PILLOW}
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
