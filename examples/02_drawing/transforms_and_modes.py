"""Push/pop transforms, angle modes, shape modes, and matrix resets."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/transforms_and_modes.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.angle_mode(p5.DEGREES)
    p5.rect_mode(p5.CENTER)
    p5.ellipse_mode(p5.CENTER)


def draw() -> None:
    p5.background(236, 239, 232)
    p5.stroke(34, 36, 42)
    p5.stroke_weight(2)

    for row in range(3):
        for col in range(6):
            with p5.pushed():
                p5.translate(80 + col * 112, 85 + row * 112)
                p5.rotate(p5.frame_count() * 2 + row * 18 + col * 9)
                p5.scale(1 + row * 0.12, 1 + col * 0.02)
                p5.fill(230 - row * 34, 105 + col * 18, 88 + row * 44, 210)
                p5.rect(0, 0, 54, 54)
                p5.no_fill()
                p5.circle(0, 0, 76)

    p5.reset_matrix()
    p5.no_stroke()
    p5.fill(24, 28, 38)
    p5.text_size(15)
    p5.text(
        "Each tile uses isolated push/pop transforms; text is drawn after reset_matrix().",
        24,
        394,
    )

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
