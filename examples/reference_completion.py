"""Reference gap closure helper demo.

Run/export deterministically:
    uv run python examples/reference_completion.py --headless --frames 1

Run interactively with the native canvas:
    uv run python examples/reference_completion.py --interactive
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5
from p5.drawing.software3d import cone_model, cylinder_model, save_obj, save_stl

OUTPUT = Path("examples/output/reference_completion.png")
OBJ_OUTPUT = Path("examples/output/reference_completion_cylinder.obj")
STL_OUTPUT = Path("examples/output/reference_completion_cone.stl")
EXPORT_CANVAS = False


def setup() -> None:
    p5.create_canvas(520, 300)
    p5.frame_rate(1)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    save_obj(cylinder_model(28, 70, detail_x=16), OBJ_OUTPUT)
    save_stl(cone_model(32, 80, detail_x=16), STL_OUTPUT)
    p5.describe("Canvas showing splines, pixel helpers, and text metadata.")


def draw() -> None:
    p5.background(245, 244, 238)
    p5.no_fill()
    p5.stroke(32, 76, 116)
    p5.stroke_weight(3)
    p5.spline_property("tightness", 0.0)
    p5.spline(40, 220, 90, 120, 170, 160, 230, 80)

    p5.begin_shape()
    p5.vertex(280, 210)
    p5.spline_vertex(330, 110)
    p5.spline_vertex(410, 150)
    p5.spline_vertex(470, 90)
    p5.end_shape()

    p5.set(32, 32, p5.Color(230, 70, 55))
    p5.copy(32, 32, 1, 1, 48, 32, 28, 28)
    sample = p5.get(48, 32)

    p5.no_stroke()
    p5.fill(30)
    p5.text_size(18)
    p5.text_direction("ltr")
    p5.text_wrap("word")
    p5.text_weight(600)
    p5.text("Text bounds + local mesh export", 32, 54)
    bounds = p5.text_bounds("Text bounds + local mesh export", 32, 54)
    p5.fill(30, 30, 30, 90)
    p5.text(f"bounds={bounds['width']:.1f}x{bounds['height']:.1f}", 32, 82)
    p5.text(f"sample={sample}", 32, 106)
    p5.text(f"accessibility={len(p5.text_output())}", 32, 130)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=1)
    args = parser.parse_args()
    global EXPORT_CANVAS
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
