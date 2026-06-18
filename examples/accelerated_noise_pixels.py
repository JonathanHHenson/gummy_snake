"""Optional Rust acceleration demo for noise and EXCLUSION pixel blending.

This sketch intentionally leans on two accelerated paths when the optional Rust
extension is installed:

- `p5.noise()` for the animated background field.
- Canvas `EXCLUSION` blend compositing for the glowing orbit overlays.

Interactive:
    uv run python examples/accelerated_noise_pixels.py --interactive

Headless/export:
    uv run python examples/accelerated_noise_pixels.py

Explicit Rust build step:
    uvx maturin develop --release
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5
from p5.rust import health_check, is_acceleration_available

OUTPUT = Path("examples/output/accelerated_noise_pixels.png")
EXPORT_CANVAS = False
ACCELERATION_LABEL = ""
BACKGROUND_PIXELS: bytes = b""


def setup() -> None:
    global ACCELERATION_LABEL
    p5.create_canvas(720, 420)
    p5.frame_rate(30)
    p5.noise_seed(23)
    p5.noise_detail(4, 0.52)
    p5.text_size(14)
    ACCELERATION_LABEL = health_check()
    print(f"Acceleration path: {ACCELERATION_LABEL}")


def draw() -> None:
    global BACKGROUND_PIXELS
    BACKGROUND_PIXELS = build_noise_pixels(p5.frame_count() * 0.045)
    p5.update_pixels(BACKGROUND_PIXELS)
    draw_exclusion_orbits()
    draw_overlay_text()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT), overwrite=True)


def build_noise_pixels(time: float) -> bytes:
    pixels = p5.load_pixels()
    width = p5.width()
    height = p5.height()
    density = p5.pixel_density()
    physical_width = max(1, int(round(width * density)))
    physical_height = max(1, int(round(height * density)))

    for y in range(physical_height):
        logical_y = y / density
        ridge = logical_y / max(1, height - 1)
        for x in range(physical_width):
            logical_x = x / density
            coarse = p5.noise(logical_x * 0.012, logical_y * 0.012, time)
            detail = p5.noise(logical_x * 0.028 + 40, logical_y * 0.028 - 30, time * 1.7)
            band = p5.noise(logical_x * 0.004, time * 0.55, logical_y * 0.01)

            red = int(18 + coarse * 70 + band * 30)
            green = int(32 + detail * 110 + ridge * 40)
            blue = int(70 + coarse * 120 + detail * 45)
            alpha = 255

            offset = (y * physical_width + x) * 4
            pixels[offset : offset + 4] = [red, green, blue, alpha]

    return bytes(pixels)


def draw_exclusion_orbits() -> None:
    p5.no_stroke()
    p5.blend_mode(p5.EXCLUSION)

    t = p5.frame_count() * 0.04
    for index in range(7):
        orbit = 32 + index * 24
        x = 360 + p5.cos(t + index * 19) * orbit * 2.1
        y = 208 + p5.sin(t * 1.4 + index * 27) * orbit
        radius = 46 + index * 12
        color_shift = 40 + index * 26
        p5.fill(255 - color_shift // 2, 120 + color_shift, 240 - color_shift // 3, 135)
        p5.circle(x, y, radius)

    p5.blend_mode(p5.BLEND)

    p5.no_fill()
    p5.stroke(255, 255, 255, 34)
    p5.stroke_weight(2)
    for index in range(4):
        p5.circle(360, 210, 120 + index * 48)


def draw_overlay_text() -> None:
    acceleration_active = "yes" if is_acceleration_available() else "no"
    p5.no_stroke()
    p5.fill(5, 12, 26, 180)
    p5.rect(22, 22, 330, 84)
    p5.fill(255, 255, 255, 230)
    p5.text("Accelerated noise + EXCLUSION blend demo", 36, 48)
    p5.text(f"acceleration: {ACCELERATION_LABEL}", 36, 70)
    p5.text(f"extension installed: {acceleration_active}", 36, 92)

    p5.fill(5, 12, 26, 168)
    p5.rect(426, 330, 270, 58)
    p5.fill(255, 255, 255, 220)
    p5.text("canvas export writes:", 442, 354)
    p5.text(str(OUTPUT), 442, 376)


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
