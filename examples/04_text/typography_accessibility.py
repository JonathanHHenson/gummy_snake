"""Text style, metrics, bounds, and accessibility descriptions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/04_text/typography_accessibility.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    gs.create_canvas(720, 360)
    gs.describe("Typography example with measured text bounds and descriptive metadata.")
    gs.describe_element("title", "The words Gummy Snake typography are drawn in large text.")


def draw() -> None:
    gs.background(248, 245, 238)
    gs.fill(26, 32, 44)
    gs.text_size(42)
    gs.text_style(gs.BOLD)
    gs.text("Gummy Snake typography", 42, 86)

    gs.text_style(gs.NORMAL)
    gs.text_size(18)
    line = "measure, align, wrap, describe"
    gs.text(line, 44, 146)
    bounds = gs.text_bounds(line, 44, 146)

    gs.no_fill()
    gs.stroke(219, 91, 71)
    gs.rect(bounds["x"], bounds["y"], bounds["width"], bounds["height"])

    gs.no_stroke()
    gs.fill(36, 126, 180)
    gs.text_size(15)
    gs.text(f"text_width: {gs.text_width(line):.1f}", 44, 210)
    gs.text(f"ascent/descent: {gs.text_ascent():.1f}/{gs.text_descent():.1f}", 44, 235)
    gs.text(f"text_output entries: {len(gs.text_output())}", 44, 260)
    gs.text(f"grid_output entries: {len(gs.grid_output())}", 44, 285)

    gs.text_align(gs.TextAlign.CENTER, gs.TextAlign.CENTER)
    gs.fill(238)
    gs.rect(485, 120, 170, 82)
    gs.fill(28, 32, 42)
    gs.text("CENTER", 570, 161)
    gs.text_align(gs.LEFT, gs.BASELINE)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
