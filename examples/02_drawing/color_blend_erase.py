"""Color modes, palette interpolation, blend modes, and erase/no_erase."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/color_blend_erase.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.no_stroke()


def draw() -> None:
    p5.background(28, 32, 42)
    left = p5.color(38, 114, 210)
    right = p5.color(244, 170, 65)
    for i in range(18):
        c = p5.lerp_color(left, right, i / 17)
        p5.fill(c)
        p5.rect(32 + i * 28, 42, 28, 128)

    p5.blend_mode(p5.MULTIPLY)
    p5.fill(250, 90, 90, 220)
    p5.circle(310, 205, 150)
    p5.fill(70, 220, 170, 220)
    p5.circle(405, 205, 150)
    p5.fill(90, 130, 250, 220)
    p5.circle(358, 284, 150)
    p5.blend_mode(p5.BLEND)

    p5.fill(255, 255, 255, 235)
    p5.rect(530, 72, 140, 240)
    p5.erase()
    p5.circle(600, 152, 72)
    p5.rect(562, 230, 76, 46)
    p5.no_erase()

    p5.fill(244)
    p5.text_size(16)
    p5.text("MULTIPLY", 302, 386)
    p5.text("erase()", 574, 386)
    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
