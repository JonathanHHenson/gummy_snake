"""Pixel buffer, blend mode, erase, and save_canvas demo.

This example defaults to the deterministic headless backend because pixel update and
Pillow blend/compositing are the most complete path for image-processing sketches.

Run/export:
    uv run python examples/pixels_blend_export.py

Equivalent explicit command:
    uv run python examples/pixels_blend_export.py --backend headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5_py as p5

ASSET_DIR = Path("examples/assets")
OUTPUT = Path("examples/output/pixels_blend_export.png")
EXPORT_CANVAS = False
SHIP: p5.Image | None = None
SHIELD: p5.Image | None = None
FIRE: p5.Image | None = None
UFO: p5.Image | None = None
POWERUP: p5.Image | None = None


def setup() -> None:
    global FIRE, POWERUP, SHIELD, SHIP, UFO
    p5.create_canvas(760, 440)
    p5.frame_rate(1)
    p5.image_mode(p5.CENTER)
    SHIP = p5.load_image(ASSET_DIR / "playerShip3_green.png")
    UFO = p5.load_image(ASSET_DIR / "ufoBlue.png")
    SHIELD = p5.load_image(ASSET_DIR / "Effects/shield3.png")
    FIRE = p5.load_image(ASSET_DIR / "Effects/fire17.png")
    POWERUP = p5.load_image(ASSET_DIR / "Power-ups/powerupBlue_shield.png")


def build_pixel_starfield() -> None:
    p5.load_pixels()
    pixels = p5.pixels()
    width = p5.width()
    height = p5.height()
    density = p5.pixel_density()
    physical_width = max(1, int(round(width * density)))
    physical_height = max(1, int(round(height * density)))

    for y in range(physical_height):
        logical_y = y / density
        glow = int(32 + 40 * (logical_y / max(1, height - 1)))
        for x in range(physical_width):
            offset = (y * physical_width + x) * 4
            pixels[offset : offset + 4] = [6, 10 + glow // 3, glow, 255]

    star_size = max(1, int(round(density)))
    for index in range(220):
        logical_x = (index * 131 + 17) % width
        logical_y = (index * 79 + index * index) % height
        brightness = 150 + (index % 4) * 26
        color = [brightness, min(255, brightness + 18), 255, 255]
        start_x = min(physical_width - 1, max(0, int(round(logical_x * density))))
        start_y = min(physical_height - 1, max(0, int(round(logical_y * density))))
        for y in range(start_y, min(physical_height, start_y + star_size)):
            for x in range(start_x, min(physical_width, start_x + star_size)):
                offset = (y * physical_width + x) * 4
                pixels[offset : offset + 4] = color

    p5.update_pixels()


def draw() -> None:
    if any(image is None for image in (SHIP, SHIELD, FIRE, UFO, POWERUP)):
        return
    assert SHIP is not None
    assert SHIELD is not None
    assert FIRE is not None
    assert UFO is not None
    assert POWERUP is not None

    build_pixel_starfield()
    draw_scene_layers(SHIP, SHIELD, FIRE, UFO, POWERUP)
    draw_pixel_buffer_callout()
    draw_export_card()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT), overwrite=True)


def draw_scene_layers(
    ship: p5.Image,
    shield: p5.Image,
    fire: p5.Image,
    ufo: p5.Image,
    powerup: p5.Image,
) -> None:
    p5.no_stroke()

    p5.blend_mode(p5.SCREEN)
    p5.image(shield, 380, 210, 250, 250)

    p5.blend_mode(p5.ADD)
    p5.image(fire, 302, 287, 78, 104)
    p5.image(fire, 458, 287, 78, 104)

    p5.blend_mode(p5.BLEND)
    p5.image(ship, 380, 242, 142, 104)
    p5.image(ufo, 180, 130, 120, 82)
    p5.image(powerup, 594, 142, 70, 70)

    # `blend()` composites an image region directly onto the canvas. Here the
    # shield texture is copied in SCREEN mode to create a second glow without
    # changing the current drawing style.
    p5.blend(shield, 0, 0, shield.width, shield.height, 252, 82, 256, 256, p5.SCREEN)

    # `erase()` uses alpha compositing. The transparent punch-out is visible in
    # the saved PNG and helps demonstrate that export preserves alpha.
    p5.erase()
    p5.fill(255)
    p5.circle(686, 246, 76)
    p5.no_erase()

    p5.fill(255, 255, 255, 215)
    p5.text_size(16)
    p5.text("SCREEN shield + ADD thrusters + erase() alpha window", 36, 48)
    p5.text_size(13)
    p5.text("transparent erase() hole", 610, 300)


def draw_pixel_buffer_callout() -> None:
    rows = p5.pixel_array()
    sample_x = min(len(rows[0]) - 1, int(round(20 * p5.pixel_density())))
    sample_y = min(len(rows) - 1, int(round(20 * p5.pixel_density())))
    sample = rows[sample_y][sample_x]
    p5.no_stroke()
    p5.fill(255, 255, 255, 28)
    p5.rect(28, 326, 308, 78)
    p5.fill(255, 255, 255, 220)
    p5.text_size(14)
    p5.text("Starfield was written with load_pixels(), pixels(), update_pixels().", 42, 356)
    p5.text(f"logical pixel (20, 20) = RGBA{sample}", 42, 382)


def draw_export_card() -> None:
    p5.fill(255, 255, 255, 30)
    p5.rect(430, 326, 300, 78)
    p5.fill(255, 255, 255, 220)
    p5.text_size(14)
    p5.text("save_canvas() writes:", 448, 356)
    p5.text("examples/output/pixels_blend_export.png", 448, 382)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.HEADLESS, choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=1)
    args = parser.parse_args()
    global EXPORT_CANVAS
    EXPORT_CANVAS = args.backend in {p5.HEADLESS, p5.PILLOW}
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
