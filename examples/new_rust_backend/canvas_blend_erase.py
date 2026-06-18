"""Blend-mode, blend-region, and erase demo for the Rust canvas backend."""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_blend_erase.png")
EXPORT_CANVAS = True
OUTPUT = DEFAULT_OUTPUT


def setup() -> None:
    p5.create_canvas(640, 360)
    p5.frame_rate(1)


def draw() -> None:
    p5.background(30, 34, 42)
    p5.no_stroke()

    modes = [p5.ADD, p5.DARKEST, p5.LIGHTEST, p5.DIFFERENCE, p5.EXCLUSION, p5.MULTIPLY, p5.SCREEN]
    labels = ["ADD", "DARKEST", "LIGHTEST", "DIFFERENCE", "EXCLUSION", "MULTIPLY", "SCREEN"]
    for index, mode in enumerate(modes):
        x = 40 + index % 4 * 150
        y = 62 + index // 4 * 132
        p5.blend_mode(p5.BLEND)
        p5.fill(80, 130, 255, 235)
        p5.rect(x, y, 78, 78)
        p5.blend_mode(mode)
        p5.fill(255, 160, 60, 220)
        p5.circle(x + 62, y + 42, 76)
        p5.blend_mode(p5.BLEND)
        p5.fill(255, 255, 255, 230)
        p5.text_size(12)
        p5.text(labels[index], x, y + 102)

    p5.fill(120, 230, 185, 240)
    p5.rect(450, 220, 120, 82)
    p5.erase()
    p5.circle(510, 261, 64)
    p5.no_erase()
    p5.fill(255, 255, 255, 230)
    p5.text_size(13)
    p5.text("erase()", 462, 326)

    p5.blend(40, 62, 78, 78, 502, 62, 78, 78, p5.ADD)
    p5.text("blend() copy + ADD", 474, 158)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global EXPORT_CANVAS, OUTPUT
    OUTPUT = args.output
    EXPORT_CANVAS = not args.no_save and args.frames is not None and args.frames > 0
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
