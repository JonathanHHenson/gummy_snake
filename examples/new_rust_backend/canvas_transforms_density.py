"""Transform and pixel-density demo for the experimental Rust canvas backend.

Run interactively:
    uv run python examples/new_rust_backend/canvas_transforms_density.py

Run a bounded offscreen/export pass instead:
    uv run python examples/new_rust_backend/canvas_transforms_density.py --frames 1

This sketch intentionally avoids text/images because those are not implemented
by the Rust canvas backend yet.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_transforms_density.png")
EXPORT_CANVAS = True
OUTPUT = DEFAULT_OUTPUT


def setup() -> None:
    p5.create_canvas(520, 520, pixel_density=2)
    p5.angle_mode(p5.DEGREES)
    p5.frame_rate(1)


def draw() -> None:
    p5.background(18, 22, 34)
    draw_density_probe()

    p5.push()
    p5.translate(p5.width() / 2, p5.height() / 2)
    draw_rotating_petals()
    draw_nested_squares()
    draw_orbit_points()
    p5.pop()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def draw_density_probe() -> None:
    # Single-logical-pixel marks should become denser when pixel_density=2.
    p5.stroke(255, 255, 255, 180)
    p5.stroke_weight(1)
    for index in range(18):
        p5.point(24 + index * 7, 24)

    p5.no_fill()
    p5.stroke(255, 255, 255, 80)
    p5.rect(18, 18, 132, 18)


def draw_rotating_petals() -> None:
    for index in range(18):
        p5.push()
        p5.rotate(index * 20)
        p5.translate(134, 0)
        p5.scale(1.0 + 0.018 * index, 0.72)
        p5.no_stroke()
        p5.fill(60 + index * 8, 145, 235, 120)
        p5.ellipse(-26, -24, 92, 48)
        p5.pop()


def draw_nested_squares() -> None:
    p5.rect_mode(p5.CENTER)
    for index in range(10):
        p5.push()
        p5.rotate(index * 9)
        size = 205 - index * 16
        p5.no_fill()
        p5.stroke(255, 210 - index * 10, 90 + index * 12, 210)
        p5.stroke_weight(2 + index * 0.35)
        p5.rect(0, 0, size, size)
        p5.pop()


def draw_orbit_points() -> None:
    p5.stroke_weight(5)
    for index in range(36):
        angle = index * math.tau / 36
        radius = 38 + (index % 6) * 10
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        p5.stroke(255, 80 + index * 3, 150, 230)
        p5.point(x, y)

    p5.no_stroke()
    p5.fill(255, 255, 255, 240)
    p5.circle(0, 0, 22)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.CANVAS, choices=p5.available_backends())
    parser.add_argument("--frames", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global EXPORT_CANVAS, OUTPUT
    OUTPUT = args.output
    EXPORT_CANVAS = not args.no_save and args.frames is not None and args.frames > 0
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
