"""Push/pop transforms, angle modes, shape modes, and matrix resets."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/transforms_and_modes.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


@gs.setup
def setup() -> None:
    gs.create_canvas(720, 420)
    gs.angle_mode(gs.DEGREES)
    gs.rect_mode(gs.CENTER)
    gs.ellipse_mode(gs.CENTER)


@gs.draw
def draw() -> None:
    gs.background(236, 239, 232)

    with gs.style(stroke=(34, 36, 42), stroke_weight=2):
        for row in range(3):
            for col in range(6):
                with gs.transform(
                    translate=(80 + col * 112, 85 + row * 112),
                    rotate=gs.current.frame_count * 2 + row * 18 + col * 9,
                    scale=(1 + row * 0.12, 1 + col * 0.02),
                ):
                    gs.fill(230 - row * 34, 105 + col * 18, 88 + row * 44, 210)
                    gs.rect(0, 0, 54, 54)
                    gs.no_fill()
                    gs.circle(0, 0, 76)

    with gs.style(fill=(24, 28, 38), stroke=None):
        gs.text_size(15)
        gs.text(
            "Each tile uses isolated transform() contexts; text is drawn outside them.",
            24,
            394,
        )

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
