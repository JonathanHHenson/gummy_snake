"""Custom paths, vertices, arcs, Bezier curves, and splines."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/shapes_curves.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(720, 420)
    gs.frame_rate(30)
    gs.spline_properties(tightness=0.35)


def draw() -> None:
    gs.background(250, 248, 242)
    gs.no_fill()
    gs.stroke_weight(4)

    gs.stroke(34, 52, 92)
    gs.begin_shape()
    for i in range(8):
        angle = i * math.tau / 8
        radius = 74 if i % 2 == 0 else 34
        gs.vertex(130 + math.cos(angle) * radius, 150 + math.sin(angle) * radius)
    gs.end_shape(gs.CLOSE)

    gs.stroke(216, 82, 63)
    gs.bezier(275, 80, 410, 18, 355, 260, 500, 190)
    for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = gs.bezier_point(275, 410, 355, 500, t)
        y = gs.bezier_point(80, 18, 260, 190, t)
        gs.fill(216, 82, 63)
        gs.no_stroke()
        gs.circle(x, y, 8)
        gs.no_fill()
        gs.stroke(216, 82, 63)

    gs.stroke(30, 150, 130)
    gs.begin_shape()
    gs.vertex(72, 330)
    gs.quadratic_vertex(190, 248, 295, 330)
    gs.bezier_vertex(380, 396, 500, 260, 640, 330)
    gs.end_shape()

    gs.stroke(68, 95, 210)
    gs.spline(520, 72, 575, 130, 630, 82, 680, 150)
    gs.arc(610, 245, 136, 104, 0.3, 5.6, gs.OPEN)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
