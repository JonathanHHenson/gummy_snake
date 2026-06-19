"""Text style, metrics, bounds, and accessibility descriptions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/04_text/typography_accessibility.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(720, 360)
    p5.describe("Typography example with measured text bounds and descriptive metadata.")
    p5.describe_element("title", "The words p5-py typography are drawn in large text.")


def draw() -> None:
    p5.background(248, 245, 238)
    p5.fill(26, 32, 44)
    p5.text_size(42)
    p5.text_style(p5.BOLD)
    p5.text("p5-py typography", 42, 86)

    p5.text_style(p5.NORMAL)
    p5.text_size(18)
    line = "measure, align, wrap, describe"
    p5.text(line, 44, 146)
    bounds = p5.text_bounds(line, 44, 146)

    p5.no_fill()
    p5.stroke(219, 91, 71)
    p5.rect(bounds["x"], bounds["y"], bounds["width"], bounds["height"])

    p5.no_stroke()
    p5.fill(36, 126, 180)
    p5.text_size(15)
    p5.text(f"text_width: {p5.text_width(line):.1f}", 44, 210)
    p5.text(f"ascent/descent: {p5.text_ascent():.1f}/{p5.text_descent():.1f}", 44, 235)
    p5.text(f"text_output entries: {len(p5.text_output())}", 44, 260)
    p5.text(f"grid_output entries: {len(p5.grid_output())}", 44, 285)

    p5.text_align(p5.CENTER, p5.CENTER)
    p5.fill(238)
    p5.rect(485, 120, 170, 82)
    p5.fill(28, 32, 42)
    p5.text("CENTER", 570, 161)
    p5.text_align(p5.LEFT, p5.BASELINE)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
