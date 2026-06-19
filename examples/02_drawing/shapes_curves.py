"""Custom paths, vertices, arcs, Bezier curves, and splines."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/shapes_curves.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.frame_rate(30)
    p5.spline_properties(tightness=0.35)


def draw() -> None:
    p5.background(250, 248, 242)
    p5.no_fill()
    p5.stroke_weight(4)

    p5.stroke(34, 52, 92)
    p5.begin_shape()
    for i in range(8):
        angle = i * math.tau / 8
        radius = 74 if i % 2 == 0 else 34
        p5.vertex(130 + math.cos(angle) * radius, 150 + math.sin(angle) * radius)
    p5.end_shape(p5.CLOSE)

    p5.stroke(216, 82, 63)
    p5.bezier(275, 80, 410, 18, 355, 260, 500, 190)
    for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = p5.bezier_point(275, 410, 355, 500, t)
        y = p5.bezier_point(80, 18, 260, 190, t)
        p5.fill(216, 82, 63)
        p5.no_stroke()
        p5.circle(x, y, 8)
        p5.no_fill()
        p5.stroke(216, 82, 63)

    p5.stroke(30, 150, 130)
    p5.begin_shape()
    p5.vertex(72, 330)
    p5.quadratic_vertex(190, 248, 295, 330)
    p5.bezier_vertex(380, 396, 500, 260, 640, 330)
    p5.end_shape()

    p5.stroke(68, 95, 210)
    p5.spline(520, 72, 575, 130, 630, 82, 680, 150)
    p5.arc(610, 245, 136, 104, 0.3, 5.6, p5.OPEN)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
