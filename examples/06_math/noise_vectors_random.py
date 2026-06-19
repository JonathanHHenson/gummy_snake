"""Vectors, noise, random seeds, mapping, interpolation, and constraints."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/06_math/noise_vectors_random.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.random_seed(7)
    p5.noise_seed(7)
    p5.noise_detail(4, 0.5)


def draw() -> None:
    p5.background(246, 244, 238)
    p5.stroke_weight(2)
    origin = p5.create_vector(p5.width() / 2, p5.height() / 2)

    for y in range(44, p5.height() - 30, 34):
        for x in range(44, p5.width() - 30, 34):
            n = p5.noise(x * 0.012, y * 0.012, p5.frame_count() * 0.01)
            angle = p5.map(n, 0, 1, -math.pi, math.pi)
            length = p5.constrain(8 + n * 28, 10, 34)
            v = p5.create_vector(math.cos(angle), math.sin(angle)) * length
            distance = p5.dist(x, y, origin.x, origin.y)
            alpha = p5.map(distance, 0, 390, 230, 70)
            p5.stroke(38, 106, 166, alpha)
            p5.line(x, y, x + v.x, y + v.y)

    p5.no_stroke()
    p5.fill(213, 80, 68)
    for i in range(20):
        x = 34 + i * 34
        y = 350 + p5.random_gaussian(0, 22)
        p5.circle(x, y, 7)

    p5.fill(30, 34, 44)
    p5.text_size(15)
    p5.text("noise field + vector math + seeded gaussian samples", 28, 30)
    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
