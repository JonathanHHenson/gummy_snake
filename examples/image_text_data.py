"""Image, text, font metrics, and lightweight data helper demo.

Run/export deterministically with canvas offscreen:
    uv run python examples/image_text_data.py --headless --frames 1

Run interactively with native canvas image/text support:
    uv run python examples/image_text_data.py --interactive
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import p5

OUTPUT = Path("examples/output/image_text_data.png")
DATA_PATH = Path("examples/output/image_text_data.json")
STRINGS_PATH = Path("examples/output/image_text_data.txt")
EXPORT_CANVAS = False
GENERATED_IMAGE: p5.Image | None = None
PALETTE: dict[str, Any] = {}
LABELS: list[str] = []


def setup() -> None:
    global GENERATED_IMAGE, PALETTE, LABELS

    p5.create_canvas(720, 420)
    p5.frame_rate(1)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    PALETTE = {
        "title": "Image + text + data helpers",
        "colors": [
            [255, 94, 91],
            [255, 202, 58],
            [25, 130, 196],
            [106, 76, 147],
        ],
    }
    LABELS = ["load_json/save_json", "load_strings/save_strings", "Image pixels", "text metrics"]

    p5.save_json(PALETTE, DATA_PATH)
    p5.save_strings(LABELS, STRINGS_PATH)
    PALETTE = p5.load_json(DATA_PATH)
    LABELS = p5.load_strings(STRINGS_PATH)

    GENERATED_IMAGE = make_generated_image()


def make_generated_image() -> p5.Image:
    image = p5.create_image(220, 220)
    colors = PALETTE["colors"]
    for y in range(image.height):
        for x in range(image.width):
            distance = p5.dist(x, y, image.width / 2, image.height / 2)
            band = int(p5.constrain(distance / 42, 0, len(colors) - 1))
            r, g, b = colors[band]
            alpha = int(p5.map_value(distance, 0, 156, 255, 80, True))
            image.set(x, y, p5.Color(r, g, b, alpha))
    return image


def draw() -> None:
    if GENERATED_IMAGE is None:
        return

    p5.background(248, 246, 240)
    p5.no_stroke()

    p5.image(GENERATED_IMAGE, 44, 92)

    cropped = GENERATED_IMAGE.get(54, 54, 112, 112)
    assert isinstance(cropped, p5.Image)
    cropped.filter(p5.INVERT)
    p5.image(cropped, 292, 92, 168, 168)

    blurred = GENERATED_IMAGE.copy()
    blurred.resize(120, 120)
    blurred.filter(p5.BLUR, 3)
    p5.image(blurred, 500, 116, 144, 144)

    p5.fill(26, 32, 44)
    p5.text_size(28)
    p5.text(str(PALETTE["title"]), 44, 46)

    p5.text_size(15)
    p5.text_leading(24)
    for index, label in enumerate(LABELS):
        p5.fill(26, 32, 44, 220)
        p5.text(f"{index + 1}. {label}", 44, 336 + index * 20)

    sample = "Measured text width"
    width = p5.text_width(sample)
    p5.fill(255, 255, 255, 210)
    p5.rect(292, 318, width + 28, 42)
    p5.fill(26, 32, 44)
    p5.text(sample, 306, 344)

    p5.fill(26, 32, 44, 180)
    p5.text_size(13)
    p5.text(f"ascent={p5.text_ascent():.1f}, descent={p5.text_descent():.1f}", 500, 338)

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
