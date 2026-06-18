"""Pixel-buffer round trip and export demo for the Rust canvas backend.

Run interactively:
    uv run python examples/new_rust_backend/canvas_pixels_export.py

Run a bounded offscreen/export pass instead:
    uv run python examples/new_rust_backend/canvas_pixels_export.py --frames 1

The background is written directly through load_pixels()/update_pixels(), then
Rust-rendered primitives are composited on top and exported as PNG.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_pixels_export.png")
EXPORT_CANVAS = True
OUTPUT = DEFAULT_OUTPUT
STARFIELD_PIXELS: bytes = b""


def setup() -> None:
    p5.create_canvas(640, 360, pixel_density=1.5)
    p5.frame_rate(1)


def build_pixel_background() -> bytes:
    pixels = p5.load_pixels()
    width = p5.width()
    height = p5.height()
    density = p5.pixel_density()
    physical_width = max(1, round(width * density))
    physical_height = max(1, round(height * density))

    for y in range(physical_height):
        logical_y = y / density
        shade = int(24 + 70 * logical_y / max(1, height - 1))
        for x in range(physical_width):
            logical_x = x / density
            offset = (y * physical_width + x) * 4
            pixels[offset : offset + 4] = [8, 14 + shade // 4, shade, 255]

            if (int(logical_x * 13) + int(logical_y * 17)) % 211 == 0:
                pixels[offset : offset + 4] = [210, 226, 255, 255]

    p5.update_pixels(pixels)
    return bytes(pixels)


def draw() -> None:
    p5.update_pixels(build_pixel_background())
    draw_nebula_shapes()
    draw_pixel_density_markers()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def draw_nebula_shapes() -> None:
    p5.no_stroke()

    p5.fill(105, 64, 220, 110)
    p5.circle(210, 165, 180)

    p5.fill(64, 190, 255, 95)
    p5.ellipse(320, 165, 260, 110)

    p5.fill(255, 126, 95, 120)
    p5.triangle(430, 94, 530, 250, 315, 248)

    p5.stroke(255, 245, 190, 230)
    p5.stroke_weight(3)
    p5.no_fill()
    p5.arc(320, 180, 310, 170, 0.25, 5.5, p5.OPEN)


def draw_pixel_density_markers() -> None:
    p5.stroke_weight(2)
    for index in range(16):
        p5.stroke(255, 255, 255, 90 + index * 8)
        p5.line(36 + index * 18, 306, 48 + index * 18, 330)

    p5.no_stroke()
    p5.fill(255, 255, 255, 180)
    p5.rect(34, 38, 190, 18)
    p5.fill(255, 200, 90, 220)
    p5.rect(34, 62, 260, 18)
    p5.fill(120, 220, 255, 220)
    p5.rect(34, 86, 140, 18)


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
