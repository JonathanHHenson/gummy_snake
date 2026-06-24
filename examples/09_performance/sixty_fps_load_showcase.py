"""A 60 FPS stress showcase with dense batched primitives and sprites."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
PRIMITIVE_LAYERS = 6
PRIMITIVES_PER_LAYER = 1_000
SPRITE_COUNT = 800
SPRITE_TYPES = 6
FPS_SMOOTHING = 0.12

OUTPUT = Path("examples/output/09_performance/sixty_fps_load_showcase.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

primitive_layers: list[list[tuple[float, float, float]]] = []
sprite_terms: list[tuple[int, float, float, float, float]] = []
sprites: list[gs.Image] = []
fps_last_time: float | None = None
fps_value = float(TARGET_FPS)

palette = [
    (74, 144, 226, 105),
    (91, 220, 168, 96),
    (249, 202, 92, 92),
    (236, 112, 99, 88),
    (164, 121, 255, 82),
    (235, 245, 255, 72),
]


def _make_sprite(seed: int, color: tuple[int, int, int]) -> gs.Image:
    image = gs.create_image(18, 18)
    rng = random.Random(seed)
    cx = 8.5
    cy = 8.5
    for y in range(image.height):
        for x in range(image.width):
            dx = x - cx
            dy = y - cy
            distance2 = dx * dx + dy * dy
            if distance2 > 72:
                image.set(x, y, (0, 0, 0, 0))
                continue
            edge = max(0.0, 1.0 - distance2 / 72)
            sparkle = 0.84 + rng.random() * 0.16
            alpha = int(255 * edge * sparkle)
            image.set(x, y, (*color, alpha))
    return image


def _update_fps() -> float:
    global fps_last_time, fps_value
    now = perf_counter()
    if fps_last_time is None:
        fps_last_time = now
        return fps_value
    elapsed = now - fps_last_time
    fps_last_time = now
    if elapsed <= 0.0:
        return fps_value
    instant_fps = 1.0 / elapsed
    fps_value += (instant_fps - fps_value) * FPS_SMOOTHING
    return fps_value


def _prepare_scene() -> None:
    global primitive_layers, sprite_terms, sprites
    rng = random.Random(41)
    primitive_layers = []
    for layer in range(PRIMITIVE_LAYERS):
        layer_items = []
        for _ in range(PRIMITIVES_PER_LAYER):
            x = rng.random() * WIDTH
            y = rng.random() * HEIGHT
            size = 1.6 + rng.random() * (2.8 + layer * 0.15)
            layer_items.append((x, y, size))
        primitive_layers.append(layer_items)

    sprite_terms = []
    for index in range(SPRITE_COUNT):
        sprite_index = index % SPRITE_TYPES
        x = rng.random() * WIDTH
        y = rng.random() * HEIGHT
        size = 8 + rng.random() * 13
        speed = 0.25 + (index % 17) * 0.035
        sprite_terms.append((sprite_index, x, y, size, speed))

    sprites = [
        _make_sprite(100 + index, palette[index % len(palette)][:3])
        for index in range(SPRITE_TYPES)
    ]


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.no_smooth()
    gs.image_mode(gs.CENTER)
    gs.describe("A 60 FPS locked load showcase with dense batched primitives and sprites.")
    _prepare_scene()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    draw_fast = gs.fast()
    gs.background(5, 8, 18)
    gs.no_stroke()

    for layer_index, layer_items in enumerate(primitive_layers):
        red, green, blue, alpha = palette[layer_index]
        gs.fill(red, green, blue, alpha)
        drift = (frame * (0.18 + layer_index * 0.055)) % WIDTH
        for x, y, size in layer_items:
            px = x + drift
            if px >= WIDTH:
                px -= WIDTH
            draw_fast.circle(px, y, size)

    for sprite_index, x, y, size, speed in sprite_terms:
        px = x + frame * speed
        px %= WIDTH
        draw_fast.image(sprites[sprite_index], px, y, size, size)

    gs.fill(3, 5, 12, 170)
    draw_fast.rect(0, 0, WIDTH, 52)
    draw_fast.rect(0, HEIGHT - 52, WIDTH, 52)
    gs.fill(238, 244, 255, 235)
    gs.text_size(15)
    gs.text(
        f"target {TARGET_FPS} FPS | {PRIMITIVE_LAYERS * PRIMITIVES_PER_LAYER:,} "
        f"primitive particles + {SPRITE_COUNT:,} sprites",
        24,
        32,
    )
    gs.text(
        f"fps {fps:5.1f} | batched public drawing paths",
        24,
        HEIGHT - 24,
    )
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
