"""Frame timing, looping state, and simple animation."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/01_getting_started/timing_and_animation.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(640, 360)
    gs.frame_rate(60)


def draw() -> None:
    t = gs.frame_count() / 60
    gs.background(16, 20, 32)

    for i in range(9):
        x = 60 + i * 65
        y = 180 + math.sin(t * 2.5 + i * 0.7) * 82
        radius = 18 + 10 * gs.norm(y, 98, 262)
        gs.no_stroke()
        gs.fill(70 + i * 16, 190 - i * 8, 235, 220)
        gs.circle(x, y, radius * 2)

    gs.fill(245)
    gs.text_size(16)
    gs.text(f"frame_count={gs.frame_count()}  delta_time={gs.delta_time():.2f}ms", 24, 34)
    gs.text(f"target frame_rate={gs.get_target_frame_rate():.0f}", 24, 58)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
