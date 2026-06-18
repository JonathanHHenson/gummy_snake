"""Color modes, style settings, image modes, and image filters.

This example defaults to the canvas offscreen mode because image filter and image
compositing APIs are currently implemented by the deterministic canvas renderer.

Run/export:
    uv run python examples/color_style_filters.py

Equivalent explicit command:
    uv run python examples/color_style_filters.py --headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/color_style_filters.png")
EXPORT_CANVAS = False
FILTER_SOURCE: p5.Image | None = None


def setup() -> None:
    global FILTER_SOURCE
    p5.create_canvas(720, 420)
    p5.angle_mode(p5.DEGREES)
    p5.frame_rate(1)
    FILTER_SOURCE = build_filter_source()


def build_filter_source() -> p5.Image:
    image = p5.create_image(96, 96)
    p5.noise_seed(23)
    for y in range(image.height):
        for x in range(image.width):
            hue = int(p5.map_value(x, 0, image.width - 1, 0, 255))
            brightness = int(p5.map_value(y, 0, image.height - 1, 255, 80))
            shimmer = int(p5.noise(x * 0.08, y * 0.08) * 70)
            image.set(x, y, (hue, min(255, brightness + shimmer), 220, 255))
    return image


def draw() -> None:
    if FILTER_SOURCE is None:
        return

    p5.background(250, 248, 241)
    draw_color_mode_swatches()
    draw_stroke_styles()
    draw_image_modes_and_filters(FILTER_SOURCE)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def draw_color_mode_swatches() -> None:
    p5.no_stroke()
    p5.color_mode(p5.HSB, 360, 100, 100, 1)
    for index in range(9):
        p5.fill(index * 40, 72, 92, 1)
        p5.rect(36 + index * 42, 36, 38, 72)

    p5.color_mode(p5.RGB)
    start = p5.color(255, 94, 91)
    stop = p5.color(25, 130, 196)
    for index in range(9):
        p5.fill(p5.lerp_color(start, stop, index / 8))
        p5.rect(36 + index * 42, 124, 38, 72)

    p5.fill(32)
    p5.text_size(14)
    p5.text("HSB swatches", 36, 222)
    p5.text("RGB lerp_color gradient", 36, 242)


def draw_stroke_styles() -> None:
    p5.no_fill()
    p5.stroke_weight(16)
    p5.stroke(35, 45, 70)
    p5.stroke_cap(p5.ROUND)
    p5.line(470, 50, 650, 50)
    p5.stroke_cap(p5.SQUARE)
    p5.line(470, 92, 650, 92)
    p5.stroke_cap(p5.PROJECT)
    p5.line(470, 134, 650, 134)

    p5.stroke_weight(6)
    p5.stroke_join(p5.ROUND)
    p5.stroke(255, 94, 91)
    p5.rect(474, 178, 54, 42)
    p5.stroke_join(p5.BEVEL)
    p5.stroke(255, 202, 58)
    p5.rect(550, 178, 54, 42)
    p5.stroke_join(p5.MITER)
    p5.stroke(25, 130, 196)
    p5.rect(626, 178, 54, 42)

    p5.no_stroke()
    p5.fill(32)
    p5.text_size(14)
    p5.text("stroke_cap + stroke_join", 470, 246)


def draw_image_modes_and_filters(source: p5.Image) -> None:
    p5.image_mode(p5.CENTER)
    p5.image(source, 140, 330, 96, 96)

    filtered = source.copy()
    filtered.filter(p5.POSTERIZE, 3)
    p5.image(filtered, 280, 330, 96, 96)

    inverted = source.copy()
    inverted.filter(p5.INVERT)
    p5.image(inverted, 420, 330, 96, 96)

    gray = source.copy()
    gray.filter(p5.GRAY)
    p5.image(gray, 560, 330, 96, 96)

    p5.image_mode(p5.CORNER)
    p5.fill(32)
    p5.text_size(13)
    p5.text("CENTER image_mode", 88, 394)
    p5.text("POSTERIZE", 246, 394)
    p5.text("INVERT", 397, 394)
    p5.text("GRAY", 542, 394)


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
