"""Frame timing, looping state, and simple animation."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/01_getting_started/timing_and_animation.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(640, 360)
    p5.frame_rate(60)


def draw() -> None:
    t = p5.frame_count() / 60
    p5.background(16, 20, 32)

    for i in range(9):
        x = 60 + i * 65
        y = 180 + math.sin(t * 2.5 + i * 0.7) * 82
        radius = 18 + 10 * p5.norm(y, 98, 262)
        p5.no_stroke()
        p5.fill(70 + i * 16, 190 - i * 8, 235, 220)
        p5.circle(x, y, radius * 2)

    p5.fill(245)
    p5.text_size(16)
    p5.text(f"frame_count={p5.frame_count()}  delta_time={p5.delta_time():.2f}ms", 24, 34)
    p5.text(f"target frame_rate={p5.get_target_frame_rate():.0f}", 24, 58)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
