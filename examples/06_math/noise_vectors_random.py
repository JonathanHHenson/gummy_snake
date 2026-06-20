"""Vectors, noise, random seeds, mapping, interpolation, and constraints."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/06_math/noise_vectors_random.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(720, 420)
    gs.random_seed(7)
    gs.noise_seed(7)
    gs.noise_detail(4, 0.5)


def draw() -> None:
    gs.background(246, 244, 238)
    gs.stroke_weight(2)
    origin = gs.create_vector(gs.width() / 2, gs.height() / 2)
    draw_fast = gs.fast()

    for y in range(44, draw_fast.height - 30, 34):
        for x in range(44, draw_fast.width - 30, 34):
            n = gs.noise(x * 0.012, y * 0.012, gs.frame_count() * 0.01)
            angle = gs.map(n, 0, 1, -math.pi, math.pi)
            length = gs.constrain(8 + n * 28, 10, 34)
            v = gs.create_vector(math.cos(angle), math.sin(angle)) * length
            distance = gs.dist(x, y, origin.x, origin.y)
            alpha = gs.map(distance, 0, 390, 230, 70)
            gs.stroke(38, 106, 166, alpha)
            draw_fast.line(x, y, x + v.x, y + v.y)

    gs.no_stroke()
    gs.fill(213, 80, 68)
    for i in range(20):
        x = 34 + i * 34
        y = 350 + gs.random_gaussian(0, 22)
        draw_fast.circle(x, y, 7)

    gs.fill(30, 34, 44)
    gs.text_size(15)
    gs.text("noise field + vector math + seeded gaussian samples", 28, 30)
    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
