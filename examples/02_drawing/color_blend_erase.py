"""Color modes, palette interpolation, blend modes, and erase/no_erase."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/color_blend_erase.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(720, 420)
    gs.no_stroke()


def draw() -> None:
    gs.background(28, 32, 42)
    left = gs.color(38, 114, 210)
    right = gs.color(244, 170, 65)
    for i in range(18):
        c = gs.lerp_color(left, right, i / 17)
        gs.fill(c)
        gs.rect(32 + i * 28, 42, 28, 128)

    gs.blend_mode(gs.MULTIPLY)
    gs.fill(250, 90, 90, 220)
    gs.circle(310, 205, 150)
    gs.fill(70, 220, 170, 220)
    gs.circle(405, 205, 150)
    gs.fill(90, 130, 250, 220)
    gs.circle(358, 284, 150)
    gs.blend_mode(gs.BLEND)

    gs.fill(255, 255, 255, 235)
    gs.rect(530, 72, 140, 240)
    gs.erase()
    gs.circle(600, 152, 72)
    gs.rect(562, 230, 76, 46)
    gs.no_erase()

    gs.fill(244)
    gs.text_size(16)
    gs.text("MULTIPLY", 302, 386)
    gs.text("erase()", 574, 386)
    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
