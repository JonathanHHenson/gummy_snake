"""Transform stack demo using push/pop and rotation.

Interactive:
    uv run python examples/transforms.py

Headless/export:
    uv run python examples/transforms.py --headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/transforms.png")
EXPORT_CANVAS = False


def setup() -> None:
    p5.create_canvas(520, 520)
    p5.angle_mode(p5.DEGREES)
    p5.frame_rate(30)


def draw() -> None:
    p5.background(245)
    p5.translate(p5.width() / 2, p5.height() / 2)

    for index in range(12):
        p5.push()
        p5.rotate(index * 30 + p5.frame_count() * 2)
        p5.translate(130, 0)
        p5.scale(1 + index * 0.035)
        p5.no_stroke()
        p5.fill(50 + index * 12, 120, 220, 170)
        p5.rect_mode(p5.CENTER)
        p5.rect(0, 0, 72, 28)
        p5.pop()

    p5.no_stroke()
    p5.fill(35)
    p5.circle(0, 0, 28)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    global EXPORT_CANVAS
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
