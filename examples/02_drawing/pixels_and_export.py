"""Canvas pixels, get/set/copy/filter, image buffers, and save_canvas."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/02_drawing/pixels_and_export.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
STAMP = p5.create_image(28, 28)


def setup() -> None:
    p5.create_canvas(420, 420, pixel_density=1)
    for y in range(STAMP.height):
        for x in range(STAMP.width):
            alpha = 255 if (x - 14) ** 2 + (y - 14) ** 2 < 13**2 else 0
            STAMP.set(x, y, (250, 84, 74, alpha))


def draw() -> None:
    p5.background(18, 24, 34)
    for y in range(0, p5.height(), 28):
        for x in range(0, p5.width(), 28):
            shade = int(40 + 90 * p5.noise(x * 0.025, y * 0.025, p5.frame_count() * 0.01))
            p5.set(x, y, (shade, 120, 180, 255))

    for i in range(10):
        p5.image(STAMP, 40 + i * 34, 70 + (i % 3) * 58)

    p5.copy(40, 70, 120, 120, 235, 70, 120, 120)
    p5.filter(p5.POSTERIZE, 4)

    sample = p5.get(40, 70)
    p5.no_stroke()
    p5.fill(sample)
    p5.rect(48, 300, 80, 64)
    p5.fill(238)
    p5.text_size(15)
    p5.text("sampled pixel swatch", 148, 338)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
