"""Benchmark common 2D image and primitive draw paths on the Pyglet backend.

Interactive default:
    uv run python examples/pyglet_image_benchmark.py

Specific variant:
    uv run python examples/pyglet_image_benchmark.py --variant rect_image_nosmooth

Run a fixed number of frames and print a summary:
    uv run python examples/pyglet_image_benchmark.py --frames 300

This benchmark is intended to help catch regressions in the native Pyglet
renderer image path, especially interactions between:

- native primitive drawing
- sprite/image rendering
- nearest-neighbor sampling via ``no_smooth()``
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import p5

CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 800
PLATFORM_RECT = (250, 650, 700, 40)
SPRITE_SIZE = 50
DEFAULT_FRAMES = 180
VARIANTS = (
    "rect_only",
    "image_linear",
    "image_nosmooth",
    "rect_image_linear",
    "rect_image_nosmooth",
)
ASSET = Path("examples/assets/herochar/herochar_idle_anim_strip_4.png")

SPRITE: p5.Image | None = None
VARIANT = "rect_image_nosmooth"
FRAME_TARGET = DEFAULT_FRAMES
START_TIME = 0.0


def cut_strip(image: p5.Image, num_sprites: int) -> list[p5.Image]:
    sprite_width = image.width // num_sprites
    return [image.get(i * sprite_width, 0, sprite_width, image.height) for i in range(num_sprites)]  # pyright: ignore[reportReturnType]


def setup() -> None:
    global SPRITE, START_TIME
    p5.create_canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
    p5.frame_rate(10_000)
    strip = p5.load_image(ASSET)
    SPRITE = cut_strip(strip, 4)[0]
    START_TIME = time.perf_counter()


def _draw_platform() -> None:
    with p5.pushed():
        p5.fill(90, 90, 90)
        p5.no_stroke()
        p5.rect(*PLATFORM_RECT)


def _draw_sprite(*, nearest: bool) -> None:
    if SPRITE is None:
        return
    with p5.pushed():
        if nearest:
            p5.no_smooth()
        p5.image_mode(p5.CENTER)
        p5.image(SPRITE, CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2, SPRITE_SIZE, SPRITE_SIZE)


def draw() -> None:
    p5.background(0)

    if "rect" in VARIANT:
        _draw_platform()

    if "image" in VARIANT:
        _draw_sprite(nearest="nosmooth" in VARIANT)

    if FRAME_TARGET is not None and p5.frame_count() >= FRAME_TARGET:
        elapsed = time.perf_counter() - START_TIME
        fps = p5.frame_count() / max(elapsed, 1e-9)
        print(f"variant={VARIANT} frames={p5.frame_count()} elapsed={elapsed:.6f}s fps={fps:.2f}")
        p5.no_loop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.PYGLET, choices=p5.available_backends())
    parser.add_argument("--variant", default="rect_image_nosmooth", choices=VARIANTS)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    args = parser.parse_args()

    global VARIANT, FRAME_TARGET
    VARIANT = args.variant
    FRAME_TARGET = args.frames
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
