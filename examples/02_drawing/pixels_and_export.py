"""Canvas pixels, get/set/copy/filter, image buffers, and save_canvas."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/pixels_and_export.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
STAMP = gs.create_image(28, 28)


def setup() -> None:
    gs.create_canvas(420, 420, pixel_density=1)
    for y in range(STAMP.height):
        for x in range(STAMP.width):
            alpha = 255 if (x - 14) ** 2 + (y - 14) ** 2 < 13**2 else 0
            STAMP.set(x, y, (250, 84, 74, alpha))


def draw() -> None:
    gs.background(18, 24, 34)
    for y in range(0, gs.height(), 28):
        for x in range(0, gs.width(), 28):
            shade = int(40 + 90 * gs.noise(x * 0.025, y * 0.025, gs.frame_count() * 0.01))
            gs.set(x, y, (shade, 120, 180, 255))

    for i in range(10):
        gs.image(STAMP, 40 + i * 34, 70 + (i % 3) * 58)

    gs.copy(40, 70, 120, 120, 235, 70, 120, 120)
    gs.filter(gs.POSTERIZE, 4)

    sample = gs.get(40, 70)
    gs.no_stroke()
    gs.fill(sample)
    gs.rect(48, 300, 80, 64)
    gs.fill(238)
    gs.text_size(15)
    gs.text("sampled pixel swatch", 148, 338)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
