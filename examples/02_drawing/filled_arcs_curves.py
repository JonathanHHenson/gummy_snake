"""Filled arcs and custom curved paths."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/filled_arcs_curves.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(720, 420)
    gs.frame_rate(30)
    gs.describe("Filled GPU-rendered arcs, quadratic curves, and Bezier paths.")


def draw() -> None:
    gs.background(250, 248, 242)
    gs.stroke_weight(4)

    with gs.style(fill=(247, 183, 49), stroke=(28, 34, 48)):
        gs.arc(150, 130, 160, 120, 0.2, 5.35, gs.PIE)

    with gs.style(fill=(80, 165, 235, 210), stroke=(34, 52, 92)):
        gs.arc(150, 292, 160, 116, math.radians(28), math.radians(318), gs.CHORD)

    with gs.style(fill=(40, 180, 155, 215), stroke=(20, 115, 96)):
        gs.begin_shape()
        gs.vertex(306, 98)
        gs.quadratic_vertex(386, 34, 462, 100)
        gs.quadratic_vertex(508, 158, 438, 208)
        gs.quadratic_vertex(362, 256, 298, 188)
        gs.quadratic_vertex(256, 142, 306, 98)
        gs.end_shape(gs.CLOSE)

    with gs.style(fill=(216, 82, 63, 210), stroke=(148, 46, 39)):
        gs.begin_shape()
        gs.vertex(510, 294)
        gs.bezier_vertex(548, 206, 668, 218, 646, 310)
        gs.bezier_vertex(630, 376, 536, 376, 486, 326)
        gs.quadratic_vertex(466, 306, 510, 294)
        gs.end_shape(gs.CLOSE)

    with gs.style(fill=(28, 32, 42), stroke=None):
        gs.text_size(16)
        gs.text("PIE fill", 118, 210)
        gs.text("CHORD fill", 108, 368)
        gs.text("quadratic fill", 338, 276)
        gs.text("Bezier fill", 552, 390)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
